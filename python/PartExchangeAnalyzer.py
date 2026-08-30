# FCProject: Abhängigkeits-Analyse für den Part/Assembly-Tausch (PartExchange)
#
# Bewusst unabhängig von PatternFeatures.py/AssemblyPatternCreator.py - nutzt nur
# FreeCAD-Kern-API (FreeCADs Assembly-Modul UtilsAssembly).
#
# Umfang aktuell bewusst auf Joints begrenzt: beim Komponententausch zählt nur,
# dass (1) Joints intakt bleiben und (2) die darin benutzten Referenzen korrekt
# auf das Ersatzteil umgehängt werden. Generische Incoming/Outgoing-Listen
# (Gruppenmitgliedschaft, Origin, etc.) lieferten keinen verwertbaren Kontext
# für diese Aufgabe und wurden entfernt - Auswirkungen auf andere
# Abhängigkeiten sind ein späterer Schritt.

import os
import zipfile

import FreeCAD as App


def find_project_root(doc):
    """Findet den Projektordner (Konvention: "PROJ_<Name>", siehe ProjectManager.py) fuer das
    Dokument, in dem `doc` liegt - geht vom Dateipfad aus so lange nach oben, bis ein
    "PROJ_"-Ordner gefunden wird, sonst faellt es auf den direkten Elternordner der Datei
    zurueck (z.B. fuer Projekte, die diese Konvention nicht nutzen)."""
    if not doc.FileName:
        return None
    current = os.path.dirname(os.path.abspath(doc.FileName))
    start = current
    while current and current != os.path.dirname(current):
        if os.path.basename(current).startswith("PROJ_"):
            return current
        current = os.path.dirname(current)
    return start


def find_external_project_references(obj):
    """Durchsucht ALLE .FCStd-Dateien im Projektordner (nicht nur die aktuell geoeffneten
    Dokumente!) danach, ob `obj`s interner Name irgendwo referenziert wird - Ergaenzung zu
    find_joints_referencing(), das nur im eigenen Dokument sucht. FreeCADs eigener
    "Objektabhaengigkeiten"-Warndialog beim Loeschen kennt ebenfalls nur GERADE GEOEFFNETE
    Dokumente - eine Baugruppe, die gar nicht offen ist, wuerde dort still durchrutschen
    (Nutzer-Report 2026-08-30).

    Liest jede .FCStd DIREKT als ZIP (Document.xml als reinen Text durchsucht), OHNE sie in
    FreeCAD zu oeffnen - deutlich schneller als jedes Dokument tatsaechlich zu laden, und
    funktioniert auch fuer Dateien, die der Nutzer gerade gar nicht geoeffnet hat.

    Liefert eine Liste von (dateipfad, anzahl_treffer) fuer jede Fundstelle, die eigene Datei
    von `obj` selbst ausgenommen. Reiner Substring-Treffer auf den internen Namen (nicht das
    Label) - kann in seltenen Faellen auch auf einen laengeren, aehnlich beginnenden Namen
    anschlagen (z.B. "Foo" trifft auch "Foo002") - das ist bewusst so belassen: lieber einmal zu
    viel warnen als eine echte Referenz uebersehen."""
    own_path = os.path.abspath(obj.Document.FileName) if obj.Document.FileName else None
    project_root = find_project_root(obj.Document)
    if project_root is None:
        return []

    needle = obj.Name.encode("utf-8")
    results = []
    for dirpath, _dirnames, filenames in os.walk(project_root):
        for filename in filenames:
            if not filename.lower().endswith(".fcstd"):
                continue
            path = os.path.join(dirpath, filename)
            if own_path is not None and os.path.abspath(path) == own_path:
                continue
            try:
                with zipfile.ZipFile(path) as z:
                    data = z.read("Document.xml")
            except Exception:
                continue
            count = data.count(needle)
            if count > 0:
                results.append((path, count))
    return results


def _get_assembly_modules():
    """FreeCADs eigenes Assembly-Workbench-Modul (kein FCProject-Code)."""
    try:
        import JointObject
        import UtilsAssembly
        return JointObject, UtilsAssembly
    except ImportError:
        return None, None


def is_valid_exchange_candidate(element):
    """Validiert, ob ein Element als Original oder Ersatzteil taugt."""
    if element is None:
        return False

    is_valid = False
    if hasattr(element, 'Shape') and element.Shape is not None:
        is_valid = True
    elif element.isDerivedFrom('Assembly::AssemblyObject'):
        is_valid = True
    elif element.isDerivedFrom('App::Part'):
        is_valid = True
    elif element.isDerivedFrom('PartDesign::Body'):
        is_valid = True
    elif element.isDerivedFrom('App::Link'):
        is_valid = True

    if not is_valid:
        return False

    if element.isDerivedFrom('App::DocumentObjectGroup'):
        return False

    # Von FCProject_PartExchange selbst erzeugte Ersatzteil-Links (siehe
    # PartExchangeWindow._ensure_local_replacement()) sollen nicht selbst wieder als Kandidat
    # fuer einen weiteren Tausch auftauchen - fuehrte sonst zu einem Link-auf-Link ("..._Link_
    # Link"), der beim Solve nicht sauber durchrechnet (Nutzer-Report 2026-08-30).
    if hasattr(element, "FCProjectExchangeLink"):
        return False

    # Datum-/Referenzelemente (Achsen, Ebenen, Punkte, LCS/Origin) haben ALLE eine eigene
    # (Dummy-)Shape zur Visualisierung - der obige hasattr(element, 'Shape')-Check erwischt sie
    # deshalb faelschlich als "echte Geometrie" mit. App::Line/Plane/Point erben von
    # App::DatumElement, LCS und der automatische Origin-Container von
    # App::LocalCoordinateSystem (siehe FreeCAD-Kern App/Datums.h) - explizit ausschliessen,
    # das sind keine tauschbaren Teile (Nutzer-Report 2026-08-30: "Koordinaten/Achsen im
    # Ersatzteil-Dropdown").
    if element.isDerivedFrom('App::DatumElement'):
        return False
    if element.isDerivedFrom('App::LocalCoordinateSystem'):
        return False

    return True


def find_joint_group(doc):
    """Sucht die Assembly::JointGroup im Dokument."""
    for obj in doc.Objects:
        if obj.TypeId == "Assembly::JointGroup":
            return obj
    return None


def find_assembly(doc):
    """Sucht die Assembly::AssemblyObject im Dokument (für den Solver-Aufruf nach dem Rewiring)."""
    for obj in doc.Objects:
        if obj.TypeId == "Assembly::AssemblyObject":
            return obj
    return None


def is_joint(obj):
    """Pragmatische Joint-Erkennung: kein fester TypeId verfügbar, daher Attribut-Check."""
    return hasattr(obj, 'Reference1') and hasattr(obj, 'Reference2')


def iter_joints(doc):
    """Liefert alle Joint-Objekte in der JointGroup des Dokuments."""
    joint_group = find_joint_group(doc)
    if joint_group is None or not hasattr(joint_group, 'Group'):
        return []
    return [obj for obj in joint_group.Group if obj is not None and is_joint(obj)]


def _joint_sides_for(joint, target):
    sides = []
    try:
        if joint.Reference1 and joint.Reference1[0] is target:
            sides.append(1)
    except Exception:
        pass
    try:
        if joint.Reference2 and joint.Reference2[0] is target:
            sides.append(2)
    except Exception:
        pass
    return sides


def subelement_for_side(joint, side):
    """Liefert den ersten nicht-leeren Subnamen der Joint-Referenz (z.B. eine Fläche/LCS)."""
    ref = joint.Reference1 if side == 1 else joint.Reference2
    try:
        subs = ref[1] if ref and len(ref) > 1 else None
        if subs:
            for sub in subs:
                if sub:
                    return sub
    except Exception:
        pass
    return ""


def full_reference_path(obj, sub):
    """Voller Pfad einer Referenz: Objekt-Label + Subnamen-Pfad (z.B. 'Motor.Origin.X_Axis')."""
    return f"{obj.Label}.{sub}" if sub else obj.Label


def find_all_project_joints_referencing(obj, log=None):
    """Sammelt ALLE echten Joints im GESAMTEN Projekt, die `obj` (bzw. ein gleichnamiges Objekt
    in einer anderen Datei) referenzieren - nicht nur im lokalen Dokument wie
    find_joints_referencing(). Oeffnet dafuer jede von find_external_project_references()
    gefundene Kandidatendatei (falls noch nicht offen) und prueft dort auf einen ECHTEN Joint,
    genau wie es vorher die einzelnen, gefuehrten Fenster pro Datei manuell taten - hier aber
    ohne Zwischenfenster, als eine einzige gesammelte Liste (Nutzerwunsch 2026-08-30: bei vielen
    betroffenen Dateien - z.B. 58 - ist ein Fenster pro Datei nicht praktikabel).

    `log`, falls uebergeben, bekommt menschenlesbare Zeilen zu uebersprungenen Dateien
    angehaengt (kein Objekt/kein echter Joint gefunden) - rein informativ fuers Fenster.

    Jeder Eintrag wie bei find_joints_referencing(), zusaetzlich "file_path"."""
    entries = []
    for entry in find_joints_referencing(obj):
        entry = dict(entry)
        entry["file_path"] = obj.Document.FileName or obj.Document.Name
        entries.append(entry)

    try:
        hits = find_external_project_references(obj)
    except Exception as e:
        if log is not None:
            log.append(f"Projektweite Suche fehlgeschlagen: {str(e)}")
        return entries

    for path, _count in hits:
        try:
            already_open_name = None
            for doc_name, d in App.listDocuments().items():
                if getattr(d, "FileName", None) and os.path.abspath(d.FileName) == os.path.abspath(path):
                    already_open_name = doc_name
                    break
            ext_doc = App.getDocument(already_open_name) if already_open_name else App.openDocument(path)
        except Exception as e:
            if log is not None:
                log.append(f"{os.path.basename(path)}: konnte nicht geöffnet werden ({str(e)}).")
            continue

        ext_obj = ext_doc.getObject(obj.Name)
        if ext_obj is None:
            if log is not None:
                log.append(f"{os.path.basename(path)}: kein Objekt '{obj.Name}' gefunden - übersprungen.")
            continue

        ext_joints = find_joints_referencing(ext_obj)
        if not ext_joints:
            if log is not None:
                log.append(
                    f"{os.path.basename(path)}: kein echter Joint auf '{ext_obj.Label}' gefunden "
                    "(vermutlich nur ein automatischer Assembly-Mirror-Eintrag) - übersprungen."
                )
            continue

        for entry in ext_joints:
            entry = dict(entry)
            entry["file_path"] = path
            entries.append(entry)

    return entries


def find_joints_referencing(obj):
    """Liefert alle Joints, die `obj` referenzieren (Original-Seite des Tauschs).

    Jeder Eintrag: {"label", "joint_obj", "joint_side", "subelement", "full_path"}.
    """
    entries = []
    for joint in iter_joints(obj.Document):
        for side in _joint_sides_for(joint, obj):
            sub = subelement_for_side(joint, side)
            full_path = full_reference_path(obj, sub)
            label = f'Joint "{joint.Label}" (Reference{side}) – {full_path}'
            entries.append({
                "label": label,
                "joint_obj": joint,
                "joint_side": side,
                "subelement": sub,
                "full_path": full_path,
            })
    return entries


def _structural_children(obj):
    """Strukturelle Kinder eines Objekts (Group, Origin, dessen Achsen/Ebenen, Features).

    `obj.Parents` erfasst die Beziehung Body/Part -> Origin NICHT (Origin ist eine
    reine Property, kein Group-Mitglied) - daher hier ein expliziter Tree-Walk
    statt der `Parents`-Property.
    """
    children = []
    if hasattr(obj, "Group") and obj.Group:
        for child in obj.Group:
            if child is not None and child not in children:
                children.append(child)
    if hasattr(obj, "Origin") and obj.Origin:
        if obj.Origin not in children:
            children.append(obj.Origin)
    if hasattr(obj, "OriginFeatures") and obj.OriginFeatures:
        for child in obj.OriginFeatures:
            if child is not None and child not in children:
                children.append(child)
    if hasattr(obj, "Features") and obj.Features:
        for child in obj.Features:
            if child is not None and child not in children:
                children.append(child)
    return children


def _resolve_link_target(obj):
    """Loest die komplette LinkedObject-Kette von `obj` bis zum letzten echten Zielobjekt auf
    (z.B. Baugruppe -> Link-Mirror -> Link-Mirror -> rohes Quellobjekt in einer eigenen Datei) -
    liefert `obj` selbst zurueck, falls es kein Link ist."""
    seen = set()
    current = obj
    while True:
        obj_id = id(current)
        if obj_id in seen:
            break
        seen.add(obj_id)
        linked = getattr(current, "LinkedObject", None)
        if linked is None:
            break
        current = linked
    return current


def subpath_for_descendant(root, descendant):
    """Ermittelt den Subnamen-Pfad von `descendant` relativ zu `root`.

    Wird benötigt, wenn die Ersatzteil-Referenz im Baum statt im 3D-Fenster
    gewählt wird (z.B. eine Origin-Achse/-Ebene oder ein LCS, das einzeln im
    Baum liegt und in der 3D-Ansicht kaum treffsicher anklickbar ist), UND wenn
    ein 3D-Klick bei mehrstufig verschachtelten Baugruppen das ROHE Quellobjekt
    aus einer eigenen, tiefer verschachtelten Datei liefert statt des direkten
    Link-Mirrors (2026-08-30, Nutzer-Report - Debug-Log bestaetigte einen Klick
    zwei Verlinkungsebenen unter dem erwarteten Ersatzteil-Dokument). Prueft
    deshalb bei jedem Kind zusaetzlich, ob dessen AUFGELOESTE LinkedObject-Kette
    (siehe _resolve_link_target()) auf `descendant` fuehrt, nicht nur reine
    Objekt-Identitaet.
    """
    if root is None or descendant is None:
        return None
    if descendant is root:
        return ""

    visited = set()
    stack = [(root, "")]
    while stack:
        current, prefix = stack.pop()
        if current.Name in visited:
            continue
        visited.add(current.Name)
        for child in _structural_children(current):
            child_path = f"{prefix}{child.Name}"
            if child is descendant or _resolve_link_target(child) is descendant:
                return child_path
            stack.append((child, f"{child_path}."))
    return None


def compute_rewired_offset(ref1, ref2):
    """Berechnet Offset2 für ein Fixed-Joint, das ref1<->ref2 geometrisch einfriert.

    Eigenständige Implementierung derselben Formel, die FreeCADs Assembly-Modul
    (UtilsAssembly) auch bei der ursprünglichen Joint-Erstellung verwendet.
    """
    _, UtilsAssembly = _get_assembly_modules()
    if UtilsAssembly is None:
        return None
    try:
        plc1 = UtilsAssembly.findPlacement(ref1, False)
        plc2 = UtilsAssembly.findPlacement(ref2, False)
        if plc1 is None or plc2 is None:
            return None
        global1 = UtilsAssembly.getJcsGlobalPlc(plc1, ref1)
        global2 = UtilsAssembly.getJcsGlobalPlc(plc2, ref2)
        if global1 is None or global2 is None:
            return None
        return global2.inverse().multiply(global1)
    except Exception as e:
        App.Console.PrintWarning(f"FCProject PartExchange: Offset-Berechnung fehlgeschlagen: {str(e)}\n")
        return None
