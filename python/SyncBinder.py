# SPDX-License-Identifier: LGPL-2.1-or-later
"""Sync-Binder (2026-11-26, Nutzerauftrag): Binder in einem Teil, der Geometrie eines Nachbarteils
so uebernimmt, wie sie in einer Baugruppe liegt - ohne DAG-Kreis.

Problem: Ein normaler SubShapeBinder im Teil (z.B. CNC_STK_001_P_Steuerbox) verweist mit Support
und Context auf die Baugruppe (CNC_STK_003_A_Steuerbox), die das Teil selbst einbaut: Kreis
001 -> 003 -> 001, FreeCAD meldet "Document::getDependentDocuments: The graph must be a DAG".
Keine Bindungsart vermeidet das (Frozen behaelt Support, Detached behaelt Context).

Loesung: der Sync-Binder ist ein ganz normaler, SYNCHRONISIERTER PartDesign::SubShapeBinder (neu angelegt als
SubShapeBinderPython, nur damit der Baum sein eigenes Icon zeigen kann) im Body
des Teils (MakeFace, Refine, Offset und Flaechennamen wie gewohnt). Seine Quelle ist aber nicht die
Baugruppe, sondern ein verstecktes Halte-Objekt (Part::Feature "<Binder>_SyncQuelle") in DERSELBEN
Teil-Datei - kein Verweis nach aussen, also kein Kreis. In das Halte-Objekt schreibt die
Synchronisierung die kopierte Geometrie. Die Quelle in der Baugruppe steht nur als Text in eigenen
Eigenschaften des Binders (Gruppe FCProject_Sync):
    SyncDatei      Dateiname der Baugruppe (z.B. "CNC_STK_003_A_Steuerbox.FCStd")
    SyncObjekt     interner Name des obersten Objekts dort (Baugruppe), wie Context
    SyncPfad       Pfad ab diesem Objekt zu DIESEM Binder in der Baugruppe ("Link.Binder."),
                   wie die Unterpfad-Angabe von Context - legt die Instanz des Teils fest
    SyncQuellen    Pfade ab dem obersten Objekt zu den Quell-Elementen ("Arduino.Edge12")
    SyncHalter     interner Name des Halte-Objekts (bei mehreren Quellen eine kommagetrennte Liste:
                   ein Halte-Objekt PRO Quelle - der Binder ist dann eine "Mappe" mit den Elementen
                   darunter, siehe ClaimChildren)
    Synchronisiert True: nach jedem Neuberechnen der Baugruppe automatisch aktualisieren
Die Baugruppe rechnet von oben nach unten: nach ihrem Neuberechnen holt die Synchronisierung die
Quellgeometrie in der geloesten Lage (auch durch verschachtelte Unterbaugruppen und Spiegel),
rechnet sie in die Koordinaten der Teil-Datei um und schreibt sie in das Halte-Objekt; der Binder
folgt beim Neuberechnen des Teils. Geschrieben wird nur bei geaenderter Form (kein Kreislauf).
Wird ein Teil mit synchronisierten Sync-Bindern allein geoeffnet, laedt es (wie die Verknuepfung eines
normalen Binders) die Baugruppe unsichtbar mit und aktualisiert die Binder sofort.
Ist die Teil-Datei nur teilweise geladen (FreeCAD laedt Unterdokumente einer Baugruppe oft so),
wird sie vorher vollstaendig nachgeladen - Aenderungen an teilweise geladenen Dokumenten speichert
FreeCAD nicht ("Changes to partial loaded document will not be saved").

Dateikompatibel: Vanilla-FreeCAD oeffnet den Sync-Binder als normalen Binder auf das Halte-Objekt
(zeigt die zuletzt kopierte Form); die Zusatz-Eigenschaften bleiben erhalten.
"""
import os
import re
import time

import FreeCAD as App
import Part

try:
    import FreeCADGui as Gui
    _GUI = True
except ImportError:
    _GUI = False

GROUP = "FCProject_Sync"
# Normaler Binder; die Python-Variante wird fuer neu angelegte Sync-Binder benutzt: nur sie erlaubt
# einem Python-Proxy im View Provider, das Baum-Icon zu bestimmen (das Icon des normalen Binders ist
# im FreeCAD-Kern festgelegt). Gleiche Eigenschaften und gleiches Verhalten.
BINDER_TYPES = ("PartDesign::SubShapeBinder", "PartDesign::SubShapeBinderPython")
LABEL_SUFFIX = " (Sync)"


# --- Erkennen und Anlegen -------------------------------------------------------------------

def is_sync_binder(obj):
    return (
        obj is not None
        and obj.TypeId in BINDER_TYPES
        and "SyncQuellen" in obj.PropertiesList
    )


def _add_sync_properties(binder):
    props = (
        ("App::PropertyString", "SyncDatei", "Dateiname der Baugruppe, aus der die Geometrie kommt"),
        ("App::PropertyString", "SyncObjekt", "Interner Name des obersten Objekts (Baugruppe) dort"),
        ("App::PropertyString", "SyncPfad", "Pfad ab dem obersten Objekt zu diesem Binder (Teil-Instanz)"),
        ("App::PropertyStringList", "SyncQuellen", "Pfade ab dem obersten Objekt zu den Quell-Elementen"),
        ("App::PropertyString", "SyncHalter", "Internes Halte-Objekt (gleiche Datei) mit der kopierten Geometrie"),
        ("App::PropertyBool", "Synchronisiert", "Nach jedem Neuberechnen der Baugruppe automatisch aktualisieren"),
        ("App::PropertyString", "SyncStatus", "Ergebnis der letzten Synchronisierung"),
    )
    for typ, name, doc in props:
        if name not in binder.PropertiesList:
            binder.addProperty(typ, name, GROUP, doc)
    binder.setEditorMode("SyncStatus", 1)  # nur lesen
    binder.setEditorMode("SyncHalter", 1)


def attach_view_provider(binder):
    """Haengt den View Provider mit dem Sync-Icon an (nur Python-Variante, nur mit Oberflaeche)."""
    if not _GUI or binder.TypeId != "PartDesign::SubShapeBinderPython":
        return
    vobj = getattr(binder, "ViewObject", None)
    if vobj is not None and not isinstance(getattr(vobj, "Proxy", None), SyncBinderViewProvider):
        SyncBinderViewProvider(vobj)


def style_binder(binder):
    """Importierte Geometrie gelb und durchsichtig darstellen (Nutzerwunsch 2026-11-26)."""
    vobj = getattr(binder, "ViewObject", None)
    if not _GUI or vobj is None:
        return
    try:
        if "UseBinderStyle" in vobj.PropertiesList:
            vobj.UseBinderStyle = False
        vobj.ShapeColor = (1.0, 0.85, 0.0)
        vobj.LineColor = (0.85, 0.65, 0.0)
        vobj.PointColor = (0.85, 0.65, 0.0)
        vobj.Transparency = 60
    except Exception as exc:  # noqa: BLE001
        App.Console.PrintWarning(f"FCProject Sync-Binder: Farbe nicht gesetzt: {exc}\n")


def holders_of(binder):
    """Halte-Objekte des Binders in Reihenfolge (Namen kommagetrennt in SyncHalter)."""
    names = [n for n in getattr(binder, "SyncHalter", "").split(",") if n]
    objs = [binder.Document.getObject(n) for n in names]
    return [o for o in objs if o is not None]


def holder_of(binder):
    holders = holders_of(binder)
    return holders[0] if holders else None


def _ensure_holders(binder, count=1, labels=None):
    """Halte-Objekte anlegen (Dokument-Ebene, versteckt) und den Binder synchronisiert darauf binden.
    count = 1: ein Halte-Objekt fuer alle Quellen (zusammen als Kompound). count > 1: je ein
    Halte-Objekt pro Quelle - der Binder ist dann eine Mappe, die Elemente stehen als Kinder darunter."""
    doc = binder.Document
    holders = holders_of(binder)
    base_label = binder.Label.replace(LABEL_SUFFIX, "")
    created = []
    while len(holders) < count:
        holder = doc.addObject("Part::Feature", binder.Name + "_SyncQuelle")
        holder.Visibility = False
        holders.append(holder)
        created.append(holder)
    for extra in holders[count:]:
        doc.removeObject(extra.Name)
    holders = holders[:count]
    for i, holder in enumerate(holders):
        if labels is not None:
            holder.Label = f"{labels[i]} (Sync)"
        elif holder in created:
            holder.Label = base_label + " Quelle (Sync)"
    names = ",".join(h.Name for h in holders)
    if binder.SyncHalter != names:
        binder.SyncHalter = names
    # Relative = False: sonst setzt FreeCAD den Context selbst (SubShapeBinder::update(), ueber die
    # Eltern des Bodys - bei einem in die Baugruppe eingebauten Teil wieder die Baugruppe!) und
    # rechnet die Kopie ein zweites Mal relativ um (2026-11-26 an der Steuerbox: 44 mm daneben,
    # Verweis auf 003 wieder da). Ohne Relative nimmt der Binder die Form des Halte-Objekts so,
    # aus dem Halte-Objekt unveraendert (die Synchronisierung schreibt dort Body-Koordinaten).
    if binder.Relative:
        binder.Relative = False
    if binder.Context is not None:
        binder.Context = None
    # Reihenfolge egal: der Binder gibt seine Support-Liste in anderer Reihenfolge zurueck, als sie
    # gesetzt wurde (2026-11-26 gemessen) - ein Vergleich mit Reihenfolge schriebe bei jedem
    # Synchronisieren neu.
    support = binder.Support
    if {e[0].Name for e in support} != {h.Name for h in holders} or len(support) != len(holders):
        binder.Support = [(h, "") for h in holders]
    if binder.BindMode != "Synchronized":
        binder.BindMode = "Synchronized"
    # Halte-Objekte als Kinder unter dem Binder zeigen (auch bei nur einem Halter und bei aelteren
    # Bindern): sonst stehen Geometrie und Binder im Baum getrennt (Halter auf Dokumentebene)
    if "ClaimChildren" in binder.PropertiesList and not binder.ClaimChildren:
        binder.ClaimChildren = True
    return holders


def _ensure_holder(binder):
    return _ensure_holders(binder, max(1, len(holders_of(binder))))[0]


def _parent_of(obj):
    try:
        parent = obj.getParentGeoFeatureGroup()
    except Exception:
        parent = None
    if parent is not None:
        return parent
    for candidate in getattr(obj, "InList", []):
        if obj in getattr(candidate, "Group", []):
            return candidate
    return None


def path_from_top(top, obj):
    """Pfad ab 'top' bis 'obj' ("A.B." - leer, wenn obj top ist), None wenn obj nicht darunter liegt."""
    names = []
    current = obj
    while current is not None and current is not top:
        names.insert(0, current.Name)
        current = _parent_of(current)
    if current is not top:
        return None
    return "".join(n + "." for n in names)


def _deepest_body_prefix(top, element_path):
    """Laengster Pfad-Anfang von element_path, der (ggf. ueber Links) auf einen PartDesign::Body
    zeigt - der Body des angeklickten Teils. (prefix, body) oder (None, None)."""
    parts = element_path.split(".")
    best = (None, None)
    prefix = ""
    for name in parts[:-1]:
        prefix += name + "."
        try:
            obj = top.getSubObject(prefix, retType=1)
        except Exception:
            obj = None
        if obj is None:
            break
        resolved = obj.getLinkedObject(True) if hasattr(obj, "getLinkedObject") else obj
        if resolved is not None and resolved.TypeId == "PartDesign::Body":
            best = (prefix, resolved)
    return best


def _fully_loaded(obj):
    """obj aus einem teilweise geladenen Dokument: Dokument vollstaendig nachladen und das Objekt
    neu holen (das Nachladen ersetzt die Objekte) - sonst speichert FreeCAD Aenderungen nicht."""
    doc = obj.Document
    if not getattr(doc, "Partial", False) or not doc.FileName:
        return obj
    name, path = obj.Name, doc.FileName
    active = App.ActiveDocument
    App.Console.PrintMessage(f"FCProject Sync-Binder: lade '{doc.Label}' vollstaendig (war teilweise geladen).\n")
    App.openDocument(path)
    if _GUI and active is not None and active.Name in App.listDocuments():
        App.setActiveDocument(active.Name)
        Gui.ActiveDocument = Gui.getDocument(active.Name)
    full = next(d for d in App.listDocuments().values() if d.FileName == path)
    return full.getObject(name)


_INDEX_NAME = re.compile(r"(Face|Edge|Vertex|Solid)\d+$")


def normalize_element_path(path):
    """Entfernt aus einem Elementpfad den FreeCAD-internen Elementnamen (TNP), der bei Auswahl in
    importierten STEP-Teilen mit im Pfad steht:
        "Arduino.;Face14;:H92b,F;:H93b:8,F;:Ha25:12,F.Face5624"  ->  "Arduino.Face5624"
    Der einfache Name (Face5624) bezeichnet dasselbe Element; die langen Namen enthalten Punkte und
    brechen die Zerlegung des Pfads in Objekte (2026-11-26, Steuerbox/Arduino)."""
    if ".;" in path or ".?" in path:
        element = path.rsplit(".", 1)[-1]
        if _INDEX_NAME.match(element):
            cut = min(i for i in (path.find(".;"), path.find(".?")) if i >= 0)
            return path[:cut + 1] + element
    return path


def split_target_and_sources(top, paths):
    """Ziel und Quellen aus den gewaehlten Elementpfaden bestimmen (Pfade ab top).
    Das Ziel liegt in einem Teil mit PartDesign-Body (dort entsteht der Binder), die Quellen koennen
    beliebige Elemente sein - auch aus importierten STEP-Teilen ohne Body. Reihenfolge: das ERSTE
    Element ist das Ziel, wenn es einen Body hat (wie bisher). Hat es keinen (z.B. zuerst ein
    STEP-Teil als Quelle gewaehlt) und genau ein anderes Element liegt in einem Body-Teil, ist
    dieses das Ziel. Gibt (Ziel, [Quellen]) zurueck; wirft RuntimeError, wenn das nicht eindeutig ist."""
    paths = [normalize_element_path(x) for x in paths]
    if len(paths) < 2:
        raise RuntimeError("Mindestens zwei Elemente waehlen: ein Element des Ziel-Teils (mit PartDesign-Body) "
                           "und die Quell-Elemente.")
    has_body = [_deepest_body_prefix(top, x)[1] is not None for x in paths]
    if has_body[0]:
        index = 0
    else:
        candidates = [i for i, flag in enumerate(has_body) if flag]
        if not candidates:
            raise RuntimeError("Keines der gewaehlten Elemente gehoert zu einem Teil mit PartDesign-Body - der "
                               "Sync-Binder braucht ein Ziel-Teil mit Body (Quellen duerfen auch aus einem "
                               "importierten STEP ohne Body kommen).")
        if len(candidates) > 1:
            raise RuntimeError("Mehrere Elemente liegen in Teilen mit PartDesign-Body - bitte das Element des "
                               "Ziel-Teils zuerst waehlen.")
        index = candidates[0]
    return paths[index], [x for i, x in enumerate(paths) if i != index]


def _source_label(top, path):
    """Beschriftung fuer ein Halte-Objekt: "<Objekt> <Element>", z.B. "Arduino_UNO_R3_SMD Face5624"."""
    obj_path, _, element = path.rpartition(".")
    try:
        obj = top.getSubObject(obj_path + ".", retType=1) if obj_path else top
    except Exception:
        obj = None
    return f"{obj.Label if obj is not None else obj_path} {element}"


def create_sync_binder(top, target_element, source_elements, label=None):
    """Legt im Body des Teils, zu dem target_element gehoert (Pfad ab top, z.B.
    "Steuerbox.Face3"), einen Sync-Binder auf source_elements (Pfade ab top) an und
    synchronisiert ihn sofort. Gibt den Binder zurueck."""
    target_element = normalize_element_path(target_element)
    source_elements = [normalize_element_path(x) for x in source_elements]
    prefix, body = _deepest_body_prefix(top, target_element)
    if body is None:
        raise RuntimeError(f"'{target_element}' gehoert zu keinem PartDesign-Body - der Sync-Binder braucht ein "
                           "Ziel-Teil mit Body.")
    if not top.Document.FileName:
        raise RuntimeError("Die Baugruppe muss zuerst gespeichert sein.")
    if not source_elements:
        raise RuntimeError("Keine Quell-Elemente ausgewaehlt.")
    body = _fully_loaded(body)
    binder = body.newObject("PartDesign::SubShapeBinderPython", "SyncBinder")
    attach_view_provider(binder)
    style_binder(binder)
    _add_sync_properties(binder)
    binder.SyncDatei = os.path.basename(top.Document.FileName)
    binder.SyncObjekt = top.Name
    binder.SyncPfad = prefix + binder.Name + "."
    binder.SyncQuellen = list(source_elements)
    binder.Synchronisiert = True
    base = label or "Binder"
    # "(Sync)" nur anhaengen, wenn der Name nicht schon "Sync" enthaelt ("Sync-Binder (Sync)" waere doppelt)
    binder.Label = base if "sync" in base.lower() else base + LABEL_SUFFIX
    if len(source_elements) > 1:
        # Mappe: ein Halte-Objekt pro Quell-Element, als Kinder unter dem Binder (ClaimChildren)
        _ensure_holders(binder, len(source_elements), [_source_label(top, x) for x in source_elements])
    else:
        _ensure_holders(binder, 1)
    sync(binder, force=True)
    binder.Document.recompute()
    return binder


def _signature(element):
    """Geometrische Kennung eines Elements: Typ, Schwerpunkt bzw. Punkt, Groesse."""
    kind = element.ShapeType
    if kind == "Vertex":
        return kind, element.Point, 0.0
    size = element.Area if kind == "Face" else element.Length if kind == "Edge" else element.Volume
    return kind, element.CenterOfMass, size


def _record_references(binder):
    """Alle Verweise anderer Objekte (gleiches Dokument) auf Elemente des Binders, mit der
    Geometrie des Elements - die internen Elementnamen (TNP) aendern sich beim Umwandeln."""
    records = []
    for obj in binder.Document.Objects:
        if obj is binder:
            continue
        for prop in obj.PropertiesList:
            try:
                typ = obj.getTypeIdOfProperty(prop)
            except Exception:
                continue
            # Sketch.ExternalGeometry ist ueber Python schreibgeschuetzt und loest sich nach dem
            # Neuberechnen ueber die einfachen Namen selbst auf (an der Steuerbox geprueft).
            if "LinkSub" not in typ or prop == "ExternalGeometry" or "ReadOnly" in obj.getPropertyStatus(prop):
                continue
            value = getattr(obj, prop)
            entries = value if isinstance(value, list) else [value] if value else []
            for entry in entries:
                if not entry or entry[0] is not binder:
                    continue
                subs = entry[1] if isinstance(entry[1], (list, tuple)) else [entry[1]]
                for sub in subs:
                    if not sub:
                        continue
                    # "?Face1": FreeCAD findet den internen (TNP-)Namen nicht mehr, der einfache
                    # Name dahinter gilt weiter - Geometrie ueber den einfachen Namen holen.
                    plain = sub.lstrip("?").split(".")[-1] if "." in sub.lstrip("?") else sub.lstrip("?")
                    try:
                        sig = _signature(binder.Shape.getElement(plain))
                    except Exception:
                        continue
                    records.append((obj.Name, prop, sub, sig))
    return records


def _find_element(shape, sig):
    kind, point, size = sig
    elements = {"Face": shape.Faces, "Edge": shape.Edges, "Vertex": shape.Vertexes}.get(kind, [])
    best, best_d = None, None
    for i, element in enumerate(elements, start=1):
        k2, p2, s2 = _signature(element)
        d = (p2 - point).Length + abs(s2 - size)
        if best_d is None or d < best_d:
            best, best_d = f"{kind}{i}", d
    return best if best_d is not None and best_d < 1e-6 else None


def _repair_references(binder, records):
    """Verweise nach dem Umwandeln wieder auf die geometrisch gleichen Elemente setzen."""
    doc = binder.Document
    by_prop = {}
    for name, prop, old_sub, sig in records:
        by_prop.setdefault((name, prop), {})[old_sub] = _find_element(binder.Shape, sig)
    repaired, failed = 0, []
    for (name, prop), mapping in by_prop.items():
        obj = doc.getObject(name)
        if obj is None:
            continue
        value = getattr(obj, prop)
        is_list = isinstance(value, list)
        entries = value if is_list else [value]
        new_entries = []
        for entry in entries:
            if entry and entry[0] is binder:
                subs = entry[1] if isinstance(entry[1], (list, tuple)) else [entry[1]]
                new_subs = []
                for sub in subs:
                    target = mapping.get(sub) if sub else sub
                    if sub and target is None:
                        # Geometrie nicht eindeutig wiedergefunden: einfachen Namen behalten (ohne
                        # das "?" fuer einen veralteten internen Namen) - FreeCAD loest ihn auf.
                        target = sub.lstrip("?")
                        try:
                            binder.Shape.getElement(target.split(".")[-1])
                        except Exception:
                            failed.append(f"{obj.Label}.{prop}:{sub}")
                    new_subs.append(target)
                new_entries.append((binder, new_subs if isinstance(entry[1], (list, tuple)) else new_subs[0]))
            else:
                new_entries.append(entry)
        try:
            setattr(obj, prop, new_entries if is_list else new_entries[0])
            repaired += 1
        except Exception as e:  # noqa: BLE001
            failed.append(f"{obj.Label}.{prop}: {e}")
    return repaired, failed


def convert_native_binder(binder):
    """Wandelt einen normalen SubShapeBinder mit Context (Baugruppe) und Support in einen
    Sync-Binder um: Pfade uebernehmen, Binder auf ein Halte-Objekt in der eigenen Datei umhaengen
    (bleibt Synchronized, MakeFace/Offset/Refine wie vorher), Context leeren.
    Gibt eine Meldung zurueck; wirft RuntimeError, wenn die Angaben fehlen."""
    if binder.TypeId != "PartDesign::SubShapeBinder" or is_sync_binder(binder):
        raise RuntimeError(f"'{binder.Label}' ist kein normaler Binder.")
    binder = _fully_loaded(binder)
    context = binder.Context
    top, ctx_sub = (context[0], context[1]) if isinstance(context, tuple) else (context, "")
    if top is None or not ctx_sub:
        raise RuntimeError(f"'{binder.Label}' hat keinen Context in einer Baugruppe.")
    if not top.Document.FileName:
        raise RuntimeError(f"Baugruppe von '{binder.Label}' ist nicht gespeichert.")
    sources = []
    for obj, subs in binder.Support:
        prefix = "" if obj is top else path_from_top(top, obj)
        if prefix is None:
            raise RuntimeError(
                f"Quelle '{obj.Label}' von '{binder.Label}' liegt nicht unter '{top.Label}' - nicht umwandelbar."
            )
        for sub in (subs if isinstance(subs, (list, tuple)) else [subs]):
            sources.append(prefix + sub)
    _add_sync_properties(binder)
    binder.SyncDatei = os.path.basename(top.Document.FileName)
    binder.SyncObjekt = top.Name
    binder.SyncPfad = ctx_sub
    binder.SyncQuellen = sources
    binder.Synchronisiert = True
    if not binder.Label.endswith(LABEL_SUFFIX):
        binder.Label = binder.Label + LABEL_SUFFIX
    # Erst das Halte-Objekt fuellen, dann umhaengen: der Binder wechselt von der Baugruppe auf
    # das Halte-Objekt in derselben Datei (Context leer - kein Verweis nach aussen mehr).
    references = _record_references(binder)
    binder.Context = None
    _ensure_holder(binder)
    status, _changed = sync(binder, force=True)
    binder.Document.recompute()
    repaired, failed = _repair_references(binder, references)
    binder.Document.recompute()
    note = f", {repaired} Verweis(e) neu gesetzt" if repaired else ""
    if failed:
        note += f", NICHT zugeordnet: {', '.join(failed)}"
    return f"'{binder.Label}' umgewandelt ({len(sources)} Quelle(n)): {status}{note}"


# --- Synchronisieren ------------------------------------------------------------------------

def _find_document(file_name, near_doc=None):
    """Offenes Dokument mit diesem Dateinamen; bei mehreren das im Ordner von near_doc."""
    matches = [d for d in App.listDocuments().values() if d.FileName and os.path.basename(d.FileName) == file_name]
    if len(matches) > 1 and near_doc is not None and near_doc.FileName:
        folder = os.path.dirname(near_doc.FileName)
        same = [d for d in matches if os.path.dirname(d.FileName) == folder]
        if same:
            return same[0]
    return matches[0] if matches else None


def _without_element_map(shape):
    """Reine Geometrie ohne Element-Namen-Tabelle. Part.getShape(..., noElementMap=True) wird bei Links
    ignoriert: die Form kommt trotzdem mit einer Tabelle, deren Hasher zum Dokument der Baugruppe gehoert.
    In der Teil-Datei gespeichert fuehrt das beim Laden zu "Missing element name prefix id" und beim
    Neuberechnen der Binder und der darauf aufbauenden Features zu "hasher mismatch" (2026-11-26,
    Steuerbox). Der Umweg ueber BREP verwirft die Tabelle; der Binder baut seine Namen selbst."""
    clean = Part.Shape()
    clean.importBrepFromString(shape.exportBrepToString())
    return clean


def _vertex_key(shape):
    return sorted((round(v.Point.x, 7), round(v.Point.y, 7), round(v.Point.z, 7)) for v in shape.Vertexes)


def _same_shape(a, b):
    if a.isNull() or b.isNull():
        return a.isNull() and b.isNull()
    if (len(a.Vertexes), len(a.Edges), len(a.Faces)) != (len(b.Vertexes), len(b.Edges), len(b.Faces)):
        return False
    ba, bb = a.BoundBox, b.BoundBox
    corners = [(ba.XMin - bb.XMin), (ba.YMin - bb.YMin), (ba.ZMin - bb.ZMin),
               (ba.XMax - bb.XMax), (ba.YMax - bb.YMax), (ba.ZMax - bb.ZMax)]
    if max(abs(c) for c in corners) > 1e-7:
        return False
    if len(a.Vertexes) <= 5000 and _vertex_key(a) != _vertex_key(b):
        return False
    return True


def _set_status(binder, text):
    if "SyncStatus" in binder.PropertiesList and binder.SyncStatus != text:
        binder.SyncStatus = text


def sync(binder, force=False):
    """Holt die Quellgeometrie aus der (geoeffneten) Baugruppe und schreibt sie, in die
    Koordinaten der Teil-Instanz umgerechnet, in den Binder. (Status-Text, geaendert?)"""
    doc = _find_document(binder.SyncDatei, binder.Document)
    if doc is None:
        return "Baugruppe nicht geoeffnet - letzte Form bleibt", False
    top = doc.getObject(binder.SyncObjekt)
    if top is None:
        status = f"'{binder.SyncObjekt}' nicht in {binder.SyncDatei} - letzte Form bleibt"
        _set_status(binder, status)
        return status, False
    try:
        instance = top.getSubObject(binder.SyncPfad, retType=1)
    except Exception:
        instance = None
    if instance is not binder:
        status = f"Instanz '{binder.SyncPfad}' nicht gefunden - letzte Form bleibt"
        _set_status(binder, status)
        return status, False
    shapes, missing = [], []
    for path in binder.SyncQuellen:
        try:
            # noElementMap: nur die Geometrie. Die Element-Namen (TNP) gehoeren zum Dokument der Baugruppe;
            # in die Teil-Datei geschrieben verweisen sie auf deren String-Tabelle ("Missing element name
            # prefix id" beim Laden) und loesen beim Lesen "hasher mismatch" aus (2026-11-26, Steuerbox).
            shape = Part.getShape(top, path, needSubElement=True, noElementMap=True)
        except Exception:
            shape = Part.Shape()
        if shape.isNull():
            missing.append(path)
        else:
            shapes.append(shape)
    if missing:
        status = f"Quelle nicht gefunden: {', '.join(missing)} - letzte Form bleibt"
        _set_status(binder, status)
        App.Console.PrintWarning(f"FCProject Sync-Binder '{binder.Label}': {status}\n")
        return status, False
    # Koordinaten, in denen die Form des Binders liegt: die des Eltern-Objekts (Body, ueber den
    # Link gesehen). NICHT getSubObject(SyncPfad, transform=False): das enthaelt trotzdem die
    # bisherige Placement des Binders selbst - nach dem ersten Schreiben lag jede weitere
    # Synchronisierung daneben (2026-11-26 gemessen).
    parent_path = binder.SyncPfad.rstrip(".").rsplit(".", 1)[0] + "." if "." in binder.SyncPfad.rstrip(".") else ""
    if parent_path:
        matrix = top.getSubObject(parent_path, retType=4, transform=True)
    else:
        matrix = top.Placement.toMatrix()

    def to_body(world):
        local = _without_element_map(world.copy())
        local.Placement = App.Placement(matrix.inverse()).multiply(world.Placement)
        # Der Binder (Relative = False) uebernimmt vom Halte-Objekt genau dessen GEOMETRIE: ohne
        # Umrechnung in seinen Body und ohne die Placement des Halte-Objekts (2026-11-26 gemessen).
        # Also die Body-Koordinaten fest in die Geometrie einrechnen, Placement = Identitaet.
        target = App.Placement(local.Placement)
        local.Placement = App.Placement()
        local.transformShape(target.toMatrix(), True)
        return local

    holders = _ensure_holders(binder, max(1, len(holders_of(binder))))
    if len(holders) > 1 and len(holders) == len(shapes):
        writes = [(h, to_body(sh)) for h, sh in zip(holders, shapes)]  # Mappe: ein Halter je Quelle
    else:
        world = shapes[0] if len(shapes) == 1 else Part.makeCompound(shapes)
        writes = [(holders[0], to_body(world))]
    changed = False
    for holder, local in writes:
        # Halter aus aelteren Staenden tragen noch Element-Namen aus der Baugruppe: einmal bereinigen
        has_old_names = holder.Shape.ElementMapSize > 0 and local.ElementMapSize == 0
        if force or has_old_names or not _same_shape(local, holder.Shape):
            holder.Shape = local
            changed = True
    if not changed:
        return "aktuell", False
    status = "aktualisiert " + time.strftime("%Y-%m-%d %H:%M:%S")
    _set_status(binder, status)
    return status, True


def _load_partial_documents_with_binders(assembly_doc, name):
    """Teilweise geladene Dokumente mit Sync-Bindern auf diese Baugruppe vollstaendig nachladen -
    sonst speichert FreeCAD die geschriebene Geometrie nicht."""
    for d in list(App.listDocuments().values()):
        if not getattr(d, "Partial", False) or not d.FileName:
            continue
        if any(is_sync_binder(o) and o.SyncDatei == name for o in d.Objects):
            App.Console.PrintMessage(f"FCProject Sync-Binder: lade '{d.Label}' vollstaendig (war teilweise geladen).\n")
            App.openDocument(d.FileName)
            if _GUI and App.ActiveDocument is not assembly_doc:
                App.setActiveDocument(assembly_doc.Name)
                Gui.ActiveDocument = Gui.getDocument(assembly_doc.Name)


def sync_binders_of(assembly_doc, only_synchronized=True, force=False):
    """Synchronisiert alle Sync-Binder in offenen Dokumenten, die auf assembly_doc zeigen, und
    berechnet deren Dokumente neu. Liste (Binder, Status, geaendert)."""
    if not assembly_doc.FileName:
        return []
    name = os.path.basename(assembly_doc.FileName)
    results, changed_docs = [], []
    _load_partial_documents_with_binders(assembly_doc, name)
    for d in list(App.listDocuments().values()):
        for obj in d.Objects:
            if not is_sync_binder(obj) or obj.SyncDatei != name:
                continue
            if only_synchronized and not obj.Synchronisiert:
                continue
            if _find_document(obj.SyncDatei, obj.Document) is not assembly_doc:
                continue
            status, changed = sync(obj, force=force)
            results.append((obj, status, changed))
            if changed and obj.Document not in changed_docs:
                changed_docs.append(obj.Document)
    for d in changed_docs:
        d.recompute()
    return results


# --- Automatisch nach dem Neuberechnen einer Baugruppe ---------------------------------------

_busy = False
_pending = []


def _has_assembly(doc):
    return any(o.TypeId == "Assembly::AssemblyObject" for o in doc.Objects)


def _run_pending():
    global _busy
    docs = list(_pending)
    _pending.clear()
    _busy = True
    try:
        for doc in docs:
            if doc.Name in App.listDocuments():
                sync_binders_of(doc)
    except Exception as e:  # noqa: BLE001
        App.Console.PrintWarning(f"FCProject Sync-Binder: {e}\n")
    finally:
        _busy = False


def _remove_orphan_holder(doc_name, holder_names):
    """Halte-Objekte (kommagetrennte Namen) loeschen, die kein Sync-Binder mehr benutzt."""
    doc = App.listDocuments().get(doc_name)
    if doc is None:
        return
    for holder_name in [n for n in holder_names.split(",") if n]:
        holder = doc.getObject(holder_name)
        if holder is not None and not any(
                is_sync_binder(o) and holder_name in o.SyncHalter.split(",") for o in doc.Objects):
            doc.removeObject(holder_name)


def _assembly_document(file_name, near_doc, messages):
    """Offenes Dokument der Baugruppe 'file_name' - ist sie nicht offen, wird sie unsichtbar im
    Hintergrund geladen (mit Meldung im Log). None, wenn die Datei fehlt."""
    assembly_doc = _find_document(file_name, near_doc)
    if assembly_doc is not None:
        return assembly_doc
    path = os.path.join(os.path.dirname(near_doc.FileName), file_name)
    if not os.path.exists(path):
        messages.append(f"Baugruppe {file_name} nicht gefunden ({path})")
        return None
    App.Console.PrintMessage(
        f"FCProject Sync-Binder: lade Baugruppe {file_name} im Hintergrund fuer die Sync-Binder in '{near_doc.Label}'.\n")
    assembly_doc = App.openDocument(path, hidden=True)
    App.Console.PrintMessage(f"FCProject Sync-Binder: Baugruppe {file_name} geladen.\n")
    return assembly_doc


def sync_document_binders(doc, force=True):
    """Synchronisiert ALLE Sync-Binder in doc (Teil oder Baugruppe), auch die nicht automatisch
    synchronisierten. Die dafuer noetigen Baugruppen werden bei Bedarf im Hintergrund geladen,
    jeder Schritt steht im Log (Nutzerauftrag 2026-11-26). Gibt (doc, Meldungen) zurueck - doc kann ein
    neu geladenes Dokument sein (war es nur teilweise geladen, wird es vollstaendig nachgeladen)."""
    global _busy
    binders = [o for o in doc.Objects if is_sync_binder(o)]
    messages = []
    if not binders:
        return doc, messages
    if getattr(doc, "Partial", False) and doc.FileName:
        binders = [_fully_loaded(binders[0])]
        doc = binders[0].Document
        binders = [o for o in doc.Objects if is_sync_binder(o)]
    active = App.ActiveDocument
    changed = False
    _busy = True
    try:
        for file_name in sorted({b.SyncDatei for b in binders}):
            assembly_doc = _assembly_document(file_name, doc, messages)
            group = [b for b in binders if b.SyncDatei == file_name]
            if assembly_doc is None:
                for b in group:
                    _set_status(b, f"Baugruppe {file_name} nicht gefunden - letzte Form bleibt")
                    messages.append(f"{b.Label}: Baugruppe {file_name} nicht gefunden - letzte Form bleibt")
                continue
            for b in group:
                status, did = sync(b, force=force)
                changed |= did
                messages.append(f"{b.Label}: {status}")
    except Exception as e:  # noqa: BLE001
        messages.append(f"Fehler: {e}")
        App.Console.PrintWarning(f"FCProject Sync-Binder: {e}\n")
    finally:
        _busy = False
    if changed:
        doc.recompute()
    if _GUI and active is not None and active.Name in App.listDocuments() and App.ActiveDocument is not active:
        App.setActiveDocument(active.Name)
        Gui.ActiveDocument = Gui.getDocument(active.Name)
    return doc, messages


def _on_document_opened(doc_name):
    """Wie beim normalen Binder (dessen Verknuepfung laedt die Baugruppe mit): wird ein Teil mit
    synchronisierten Sync-Bindern geoeffnet, die Baugruppe unsichtbar mitladen und die Binder
    sofort aktualisieren (Nutzerauftrag 2026-11-26)."""
    global _busy
    doc = App.listDocuments().get(doc_name)
    if doc is not None and _GUI:
        for o in doc.Objects:
            if is_sync_binder(o):
                attach_view_provider(o)
    if doc is None or not doc.FileName or getattr(doc, "Partial", False):
        return  # teilweise geladen = Unterdokument einer gerade geoeffneten Baugruppe
    binders = [o for o in doc.Objects if is_sync_binder(o) and o.Synchronisiert]
    if not binders:
        return
    active = App.ActiveDocument
    changed = False
    _busy = True
    try:
        for file_name in sorted({b.SyncDatei for b in binders}):
            assembly_doc = _find_document(file_name, doc)
            if assembly_doc is None:
                path = os.path.join(os.path.dirname(doc.FileName), file_name)
                if not os.path.exists(path):
                    for b in binders:
                        if b.SyncDatei == file_name:
                            _set_status(b, f"Baugruppe {file_name} nicht gefunden - letzte Form bleibt")
                    continue
                App.Console.PrintMessage(
                    f"FCProject Sync-Binder: lade Baugruppe {file_name} fuer die Sync-Binder in '{doc.Label}'.\n")
                App.openDocument(path, hidden=True)
            for b in binders:
                if b.SyncDatei == file_name:
                    _status, did = sync(b)
                    changed |= did
    except Exception as e:  # noqa: BLE001
        App.Console.PrintWarning(f"FCProject Sync-Binder: {e}\n")
    finally:
        _busy = False
    if changed:
        doc.recompute()
    if _GUI and active is not None and active.Name in App.listDocuments() and App.ActiveDocument is not active:
        App.setActiveDocument(active.Name)
        Gui.ActiveDocument = Gui.getDocument(active.Name)


class _Observer:
    def slotCreatedDocument(self, doc):
        # wird auch beim Oeffnen gerufen, VOR dem Einlesen - deshalb einen Durchlauf spaeter pruefen
        if _GUI:
            from PySide import QtCore
            name = doc.Name
            QtCore.QTimer.singleShot(0, lambda: _on_document_opened(name))

    def slotDeletedObject(self, obj):
        # Binder geloescht -> sein Halte-Objekt mit (danach, nicht im Signal)
        if is_sync_binder(obj) and getattr(obj, "SyncHalter", ""):
            args = (obj.Document.Name, obj.SyncHalter)
            if _GUI:
                from PySide import QtCore
                QtCore.QTimer.singleShot(0, lambda: _remove_orphan_holder(*args))
            else:
                _remove_orphan_holder(*args)

    def slotRecomputedDocument(self, doc):
        if _busy or not doc.FileName or not _has_assembly(doc):
            return
        if doc not in _pending:
            _pending.append(doc)
            if _GUI:
                from PySide import QtCore
                QtCore.QTimer.singleShot(0, _run_pending)
            else:
                _run_pending()


_observer = None


def register():
    global _observer
    if _observer is None:
        _observer = _Observer()
        App.addDocumentObserver(_observer)


def unregister():
    global _observer
    if _observer is not None:
        App.removeDocumentObserver(_observer)
        _observer = None


# --- Befehle ---------------------------------------------------------------------------------

if _GUI:
    import IconUtils

    ICON_DIR = os.path.join(os.path.dirname(__file__), "resources", "icons")

    class SyncBinderViewProvider:
        """Python-Proxy fuer den View Provider eines Sync-Binders: nur das Baum-Icon (Dreieck mit roten
        Eckpunkten und blauem Sync-Zeichen); alles andere macht weiter der View Provider des Binders."""

        def __init__(self, vobj):
            vobj.Proxy = self

        def attach(self, vobj):
            self.Object = vobj.Object

        def getIcon(self):
            return IconUtils.icon_path(ICON_DIR, "sync_binder_tree.svg")

        def __getstate__(self):
            return None

        def __setstate__(self, state):
            return None

    def _native_binders_into(assembly_doc):
        found = []
        for d in App.listDocuments().values():
            for obj in d.Objects:
                if obj.TypeId != "PartDesign::SubShapeBinder" or is_sync_binder(obj):
                    continue
                context = obj.Context
                top = context[0] if isinstance(context, tuple) else context
                if top is not None and top.Document is assembly_doc:
                    found.append(obj)
        return found

    class CommandCreateSyncBinder:
        def GetResources(self):
            return {
                "Pixmap": IconUtils.icon_path(ICON_DIR, "sync_binder.svg"),
                "MenuText": "FCProject: Sync-Binder anlegen",
                "ToolTip": (
                    "In der Baugruppe ein Element des Teils waehlen, das den Binder bekommt (Teil mit "
                    "PartDesign-Body), und die Quell-Elemente (Kanten/Flaechen anderer Teile, auch aus "
                    "einem importierten STEP; Reihenfolge egal, solange nur ein Element in einem Body-Teil "
                    "liegt). Bei mehreren Quellen entsteht der Binder als Mappe mit den Elementen darunter. "
                    "Der Sync-Binder kopiert "
                    "die Quelle so, wie sie in der Baugruppe liegt - ohne Verknuepfung, also ohne "
                    "DAG-Kreis - und wird nach jedem Neuberechnen der Baugruppe aktualisiert."
                ),
            }

        def Activated(self):
            from PySide import QtWidgets

            main_win = Gui.getMainWindow()
            entries = []
            for sel in Gui.Selection.getSelectionEx("", 0):
                for sub in sel.SubElementNames:
                    entries.append((sel.Object, sub))
            if len(entries) < 2 or len({id(o) for o, _ in entries}) != 1:
                QtWidgets.QMessageBox.warning(
                    main_win, "FCProject",
                    "Bitte in EINER Baugruppe die Elemente waehlen: ein Element des Ziel-Teils (mit "
                    "PartDesign-Body) und mindestens ein Quell-Element (auch aus einem importierten "
                    "STEP). Bei mehreren Quellen entsteht der Binder als Mappe mit den Elementen darunter.")
                return
            top = entries[0][0]
            try:
                target, sources = split_target_and_sources(top, [sub for _, sub in entries])
                binder = create_sync_binder(top, target, sources)
            except Exception as exc:
                QtWidgets.QMessageBox.warning(main_win, "FCProject", f"Sync-Binder nicht angelegt: {exc}")
                return
            App.Console.PrintMessage(
                f"FCProject: Sync-Binder '{binder.Label}' in {binder.Document.Label} angelegt "
                f"({binder.SyncStatus}). Teil-Datei speichern nicht vergessen.\n")

        def IsActive(self):
            return App.ActiveDocument is not None

    class CommandUpdateSyncBinders:
        def GetResources(self):
            return {
                "Pixmap": IconUtils.icon_path(ICON_DIR, "sync_binder_update.svg"),
                "MenuText": "FCProject: Sync-Binder aktualisieren",
                "ToolTip": (
                    "Synchronisiert die Sync-Binder im aktuellen Teil bzw. in der aktuellen Baugruppe "
                    "(auch die nicht automatisch synchronisierten); die dafuer noetigen Baugruppen werden "
                    "im Hintergrund geladen (Meldungen im Log). Zeigen Sync-Binder anderer offener "
                    "Dokumente auf diese Baugruppe, werden auch sie aktualisiert. Normale Binder, die per "
                    "Context auf diese Baugruppe zeigen (DAG-Kreis), werden auf Nachfrage umgewandelt."
                ),
            }

        def Activated(self):
            from PySide import QtWidgets

            main_win = Gui.getMainWindow()
            doc = App.ActiveDocument
            natives = _native_binders_into(doc)
            messages = []
            if natives:
                names = "\n".join(f"  {b.Document.Label}: {b.Label}" for b in natives)
                answer = QtWidgets.QMessageBox.question(
                    main_win, "FCProject",
                    f"Diese Binder verweisen auf diese Baugruppe (DAG-Kreis):\n{names}\n\n"
                    "In Sync-Binder umwandeln? (Form und Pfade bleiben, die Verknuepfung entfaellt.)",
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                )
                if answer == QtWidgets.QMessageBox.Yes:
                    for b in natives:
                        try:
                            messages.append(convert_native_binder(b))
                        except Exception as exc:
                            messages.append(f"'{b.Label}': {exc}")
            # 1. Sync-Binder in DIESEM Teil bzw. dieser Baugruppe: die noetigen Baugruppen werden im
            #    Hintergrund geladen (Meldungen im Log), die Binder fuer das Teil synchronisiert
            doc, own = sync_document_binders(doc, force=True)
            messages += [f"{doc.Label}: {m}" for m in own]
            # 2. Sync-Binder anderer geoeffneter Dokumente, die auf diese Baugruppe zeigen
            results = sync_binders_of(doc, only_synchronized=False, force=True)
            messages += [f"{b.Document.Label}: {b.Label} - {status}" for b, status, _ in results
                         if b.Document is not doc]
            for m in messages:
                App.Console.PrintMessage(f"FCProject Sync-Binder: {m}\n")
            if not messages:
                messages = ["Keine Sync-Binder in diesem Dokument oder fuer diese Baugruppe gefunden."]
            QtWidgets.QMessageBox.information(main_win, "FCProject", "\n".join(messages))

        def IsActive(self):
            return App.ActiveDocument is not None

    Gui.addCommand("FCProject_CreateSyncBinder", CommandCreateSyncBinder())
    Gui.addCommand("FCProject_UpdateSyncBinders", CommandUpdateSyncBinders())
