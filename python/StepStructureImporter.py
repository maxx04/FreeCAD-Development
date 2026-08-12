# FCProject: Baut aus einer STEP-Baumauswahl (rohe Shape-Objekte und/oder App::Part-Container mit
# Unterstruktur, beliebig tief verschachtelt) eine neutrale Baum-Beschreibung, aus der EntityCreator
# eine PDM-Hierarchie (Kaufteile + Baugruppen) erzeugen kann. Bewusst getrennt von PurchasedPartCreator/
# EntityCreator gehalten - hier geht es nur ums Erkennen/Beschreiben der Struktur, nicht ums Anlegen
# von PDM-Dokumenten.
import FreeCAD as App
from PurchasedPartCreator import _solids_from_shape

# Reine Struktur-/Referenzobjekte ohne eigene Geometrie - beim Rekursieren überspringen
_SKIP_TYPES = ("App::Origin", "App::OriginFeature", "App::Plane", "App::Line")


def resolve_refs_to_objects(step_source_refs):
    """Löst (Dokument, Objekt)-Referenzen aus der Baum-Auswahl in echte FreeCAD-Objekte auf."""
    objs = []
    for doc_name, obj_name in step_source_refs or []:
        doc = App.getDocument(doc_name) if doc_name else None
        obj = doc.getObject(obj_name) if doc else None
        if obj is not None:
            objs.append(obj)
        else:
            App.Console.PrintWarning(f"FCProject: STEP-Quellobjekt '{obj_name}' nicht auffindbar - übersprungen.\n")
    return objs


def build_step_tree(selected_objects):
    """Baut aus den ausgewählten Top-Level-Objekten je einen Knoten (Leaf oder Gruppe, rekursiv).

    Knoten-Form:
    - Leaf:  {"kind": "leaf",  "label": str, "solids": [(Shape, Quell-Label), ...]}
    - Gruppe: {"kind": "group", "label": str, "children": [Knoten, ...]}
    """
    nodes = []
    for obj in selected_objects:
        node = _walk_node(obj)
        if node is not None:
            nodes.append(node)
    return nodes


def _walk_node(obj):
    if obj.isDerivedFrom("App::Part") or obj.isDerivedFrom("App::DocumentObjectGroup"):
        children = []
        for child in (getattr(obj, "Group", None) or []):
            if child is None or any(child.isDerivedFrom(t) for t in _SKIP_TYPES):
                continue
            sub = _walk_node(child)
            if sub is not None:
                children.append(sub)
        if not children:
            App.Console.PrintWarning(f"FCProject: Struktur-Gruppe '{obj.Label}' enthält keine verwertbare Geometrie - übersprungen.\n")
            return None
        return {"kind": "group", "label": obj.Label, "children": children}

    if hasattr(obj, "Shape") and obj.Shape is not None and not obj.Shape.isNull():
        solids = _solids_from_shape(obj.Shape)
        if not solids:
            App.Console.PrintWarning(f"FCProject: '{obj.Label}' enthält keine verwertbare Geometrie - übersprungen.\n")
            return None
        # Jedes Solid trägt hier das Label des Quellobjekts mit (gebraucht für Bezeichnung/Log in
        # EntityCreator - Format muss zu _collect_solids_from_refs in PurchasedPartCreator passen).
        return {"kind": "leaf", "label": obj.Label, "solids": [(s, obj.Label) for s in solids]}

    return None
