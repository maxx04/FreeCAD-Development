# FCProject: reiner Python-Ersatz fuer das fruehere FCProjectCore.BOMManager (C++/pybind11,
# siehe src/BOMManager.cpp + src/Utils.cpp).
#
# Grund: FCProjectCore.so kann der FreeCAD Addon Manager beim Installieren "aus Git" nicht
# mitbauen - er klont nur die Python-Dateien des Repos. Damit FCProject als reines
# Python-Addon per Custom-Repository (Sandbox UND normale FreeCAD-App) installierbar ist,
# wird die BOM-Logik hier 1:1 nach Python portiert. src/BOMManager.cpp/src/Utils.cpp
# (+ include/*.h) bleiben unveraendert im Repo stehen (Referenz/History), werden aber von
# keinem Python-Modul mehr importiert.
#
# Oeffentliche Schnittstelle bewusst identisch zur alten FCProjectCore.BOMManager-Klasse
# gehalten (Konstruktor mit root_name, generate_structural_bom()/export_to_csv()/
# export_to_spreadsheet()) - BOMCommand.py musste dadurch nur die Import-Zeile aendern.
#
# Bewusste Abweichung vom C++-Original: der dortige Konstruktor loeste als Nebeneffekt schon
# selbst exportToCsv()+generateStructuralBom() aus (laut eigenem Kommentar dort ein
# Debug-Ueberbleibsel - BOMCommand.py ruft beide Exporte ohnehin explizit selbst auf, mit
# dem tatsaechlich gewuenschten target_dir). Hier passiert im Konstruktor nichts dergleichen.

import csv
from pathlib import Path

import FreeCAD as App


def _get_objects_from_link_list(obj, prop_name):
    """Portiert aus src/Utils.cpp: getObjectsFromLinkListProperty()."""
    value = getattr(obj, prop_name, None)
    if not value:
        return []
    return list(value)


def _is_pass_through_container(obj):
    """Portiert aus src/Utils.cpp: isPassThroughContainer() - reine Durchreich-Container
    (z.B. Pattern-Feature-Objekte) duerfen keine eigene BOM-Zeile erzeugen, auch wenn
    resolvePdmValue() sonst faelschlich eine ArticleID eines Kindes "erben" wuerde."""
    if obj is None:
        return False
    if hasattr(obj, "ArticleID"):
        return False
    type_name = obj.TypeId
    if type_name == "App::DocumentObjectGroupPython":
        return True
    if type_name == "App::FeaturePython" and hasattr(obj, "SourceElement") and hasattr(obj, "Count"):
        return True
    return False


def _get_clean_children(source_obj):
    """Portiert aus src/Utils.cpp: getCleanChildren()."""
    items = []
    if source_obj is None:
        return items

    origin = getattr(source_obj, "Origin", None)
    if origin is not None:
        items.append(origin)

    raw_group = _get_objects_from_link_list(source_obj, "Group")
    raw_features = _get_objects_from_link_list(source_obj, "Features")

    hidden_in_subfolders = set()
    for child in raw_group:
        if child is not None and child.TypeId in ("App::DocumentObjectGroup", "Assembly::JointGroup"):
            for sub in _get_objects_from_link_list(child, "Group"):
                if sub is not None:
                    hidden_in_subfolders.add(sub)

    for child in raw_group:
        if child is not None and child not in hidden_in_subfolders and child not in items:
            items.append(child)
    for child in raw_features:
        if child is not None and child not in items:
            items.append(child)
    return items


def _get_original_object(obj):
    """Portiert aus src/Utils.cpp: GetOriginalObject() - folgt ausschliesslich der Property
    "LinkedObject" (z.B. App::Link), NICHT FreeCADs generischer getLinkedObject()-Methode
    (die wird separat, direkt ueber die FreeCAD-API, fuer den Baum-Durchlauf verwendet - siehe
    _get_assembly_tree())."""
    seen = set()
    while obj is not None and id(obj) not in seen:
        seen.add(id(obj))
        target = getattr(obj, "LinkedObject", None)
        if target is not None and target != obj:
            obj = target
            continue
        break
    return obj


def _property_as_string(obj, prop_name):
    """Bestmoegliches String-Aequivalent zum "Value"-Feld, das
    getPropertiesAsStringMapbyGroup() im C++-Original fuer eine einzelne Property lieferte -
    reicht fuer resolvePdmValue(), das nur genau dieses eine Feld braucht."""
    if not hasattr(obj, prop_name):
        return None
    value = getattr(obj, prop_name)
    if value is None:
        return None
    if isinstance(value, App.DocumentObject):
        return value.Name
    return str(value)


def _resolve_pdm_value(obj, prop_name):
    """Portiert aus src/Utils.cpp: resolvePdmValue()."""
    if obj is None:
        return ""

    def is_usable(value):
        return bool(value) and value not in ("-", "None")

    target = _get_original_object(obj) or obj

    value = _property_as_string(target, prop_name)
    if value is not None and is_usable(value):
        return value

    for child in _get_objects_from_link_list(target, "Group"):
        if child is None:
            continue
        child_value = _property_as_string(child, prop_name)
        if child_value is not None and is_usable(child_value):
            return child_value

    return ""


def _extract_pdm_data(obj):
    """Portiert aus src/BOMManager.cpp: extractPdmData()."""
    result = {"ArticleID": _resolve_pdm_value(obj, "ArticleID")}

    bezeichnung = _resolve_pdm_value(obj, "Bezeichnung")
    if not bezeichnung:
        bezeichnung = _resolve_pdm_value(obj, "ProfilTyp")
    result["Bezeichnung"] = bezeichnung

    material = _resolve_pdm_value(obj, "MaterialName")
    if not material:
        material = _resolve_pdm_value(obj, "ShapeMaterial")
    result["Material"] = material or "-"

    preis = _resolve_pdm_value(obj, "Preis")
    result["Preis"] = preis if preis else "0.0"

    pdm_obj = _get_original_object(obj) or obj
    rohling = "-"
    if pdm_obj.TypeId != "Assembly::AssemblyObject":
        halbzeug = _resolve_pdm_value(obj, "BasiertAufHalbzeug")
        if halbzeug:
            rohling = halbzeug
    result["Rohling"] = rohling

    return result


def _get_assembly_tree(root_object):
    """Portiert aus src/Utils.cpp: getAssemblyTree() - iterativer Stack-Durchlauf statt
    Rekursion (identischer Zyklenschutz: ein Objekt darf nicht innerhalb seines eigenen
    Pfades vom Wurzelelement aus nochmal auftauchen)."""
    assembly_tree = []
    if root_object is None:
        return assembly_tree

    # Stack-Eintrag: (obj, depth, path_bis_hierher, index_path) - index_path wird wie im
    # C++-Original mitgefuehrt, aber von generateStructuralBom() nicht ausgewertet (die baut
    # ihren eigenen Struktur-Index ueber die Tiefe, siehe dort).
    stack = [(root_object, 0, (), (1,))]

    while stack:
        obj, depth, path, index_path = stack.pop()
        if obj in path:
            continue
        current_path = path + (obj,)

        artikel_id = "" if _is_pass_through_container(obj) else _resolve_pdm_value(obj, "ArticleID")
        if not artikel_id:
            artikel_id = "None"
        assembly_tree.append((obj, depth, artikel_id, index_path))

        children = _get_clean_children(obj)
        linked_obj = obj.getLinkedObject(False)
        if linked_obj is not None and linked_obj != obj:
            for child in _get_clean_children(linked_obj):
                if child is not None and child not in children:
                    children.append(child)

        # Kinder in umgekehrter Reihenfolge auf den Stack legen (LIFO), damit sie in
        # natuerlicher Reihenfolge wieder heruntergenommen werden - wie im C++-Original.
        n = len(children)
        for i in range(n - 1, -1, -1):
            stack.append((children[i], depth + 1, current_path, index_path + (i + 1,)))

    return assembly_tree


def generate_structural_bom(root_assembly):
    """Portiert aus src/BOMManager.cpp: generateStructuralBom()."""
    bom_list = []
    if root_assembly is None:
        return bom_list

    tree = _get_assembly_tree(root_assembly)

    visible_index_counters = []
    previous_depth = -1
    article_row_index = {}

    for obj, depth, artikel_id, _index_path in tree:
        if obj is None or not artikel_id or artikel_id == "None":
            continue

        if depth > previous_depth:
            if len(visible_index_counters) <= depth:
                visible_index_counters.extend([0] * (depth + 1 - len(visible_index_counters)))
            for d in range(previous_depth + 1, depth + 1):
                visible_index_counters[d] = 1
        elif depth == previous_depth:
            visible_index_counters[depth] += 1
        else:
            del visible_index_counters[depth + 1:]
            visible_index_counters[depth] += 1

        previous_depth = depth

        pdm_info = _extract_pdm_data(obj)

        # Fuehrendes "'" wie im C++-Original: zwingt Excel/LibreOffice, das Feld als Text
        # statt als Zahl/Datum zu interpretieren (z.B. "1.2" nicht als 1,2 oder 2. Januar).
        structure_index = "'" + ".".join(str(visible_index_counters[i]) for i in range(depth + 1))

        preis_str = "0.0"
        preis_roh = pdm_info.get("Preis") or ""
        if preis_roh:
            try:
                # Deutsches Dezimal-Komma in Punkt umwandeln, wie im C++-Original.
                preis_str = f"{float(preis_roh.replace(',', '.')):.6f}"
            except ValueError:
                preis_str = preis_roh

        article_id = pdm_info["ArticleID"]
        existing_row = article_row_index.get(article_id)
        if existing_row is None:
            article_row_index[article_id] = len(bom_list)
            bom_list.append([
                structure_index,
                article_id,
                pdm_info["Bezeichnung"],
                pdm_info["Material"],
                pdm_info["Rohling"],
                preis_str,
                "1",
            ])
        else:
            # Gleiche ArtikelID bereits vorhanden (z.B. Pattern-Kopie) -> nur Menge erhoehen,
            # keine eigene Zeile.
            row = bom_list[existing_row]
            try:
                menge = int(row[-1])
            except ValueError:
                menge = 1
            row[-1] = str(menge + 1)

    return bom_list


_CSV_HEADER = [
    "Position (Struktur-Index)", "Artikel-ID", "Benennung",
    "Werkstoff", "Rohling/Halbzeug", "Preis", "Menge",
]


def export_to_csv(root_assembly, target_dir):
    """Portiert aus src/BOMManager.cpp: exportToCsv(). Nutzt Pythons csv-Modul statt der
    manuellen escapeCsvField()-Maskierung aus dem C++-Original - deckt dieselben RFC-4180-
    Faelle ab (Komma/Anfuehrungszeichen/Zeilenumbruch im Feld) und schreibt per Excel-Dialekt
    zusaetzlich CRLF-Zeilenenden, was zur "Excel-konform"-Zielsetzung dieses Buttons passt."""
    rows = generate_structural_bom(root_assembly)
    if not rows:
        return ""

    name = root_assembly.Name if root_assembly is not None else "document"
    csv_path = Path(target_dir) / f"BOM_Struktur_{name}.csv"

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(_CSV_HEADER)
        writer.writerows(rows)

    return str(csv_path)


def export_to_spreadsheet(root_assembly):
    """Portiert aus src/BOMManager.cpp: exportToSpreadsheet(). Der target_dir-Parameter des
    C++-Originals blieb dort ebenfalls ungenutzt (Spreadsheet haengt am aktiven Dokument, nicht
    an einem Dateipfad) - hier deshalb konsequent weggelassen, siehe BOMManager.export_to_spreadsheet()
    fuer die Aufruf-kompatible Wrapper-Methode."""
    doc = App.ActiveDocument
    if doc is None:
        return False

    rows = generate_structural_bom(root_assembly)
    if not rows:
        return False

    sheet = doc.addObject("Spreadsheet::Sheet", "BOM_Struktur")
    if sheet is None:
        return False

    columns = ["A", "B", "C", "D", "E", "F", "G"]
    for col, title in zip(columns, _CSV_HEADER):
        sheet.set(f"{col}1", title)

    for r, row in enumerate(rows, start=2):
        for col, value in zip(columns, row):
            sheet.set(f"{col}{r}", str(value))

    doc.recompute()
    return True


class BOMManager:
    """Reiner Python-Ersatz fuer FCProjectCore.BOMManager (frueher C++/pybind11) - siehe
    Modul-Docstring oben. Gleiche oeffentliche Schnittstelle wie zuvor (Konstruktor mit
    root_name, generate_structural_bom()/export_to_csv()/export_to_spreadsheet()), damit
    BOMCommand.py nur die Import-Zeile aendern musste."""

    def __init__(self, root_name=""):
        self.root_assembly = None
        doc = App.ActiveDocument
        if doc is not None and root_name:
            self.root_assembly = doc.getObject(root_name)

    def generate_structural_bom(self):
        return generate_structural_bom(self.root_assembly)

    def export_to_csv(self, target_dir):
        return export_to_csv(self.root_assembly, target_dir)

    def export_to_spreadsheet(self, target_dir=None):
        return export_to_spreadsheet(self.root_assembly)
