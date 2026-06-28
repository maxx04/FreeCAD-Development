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

import FreeCAD as App


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


def subpath_for_descendant(root, descendant):
    """Ermittelt den Subnamen-Pfad von `descendant` relativ zu `root`.

    Wird benötigt, wenn die Ersatzteil-Referenz im Baum statt im 3D-Fenster
    gewählt wird (z.B. eine Origin-Achse/-Ebene oder ein LCS, das einzeln im
    Baum liegt und in der 3D-Ansicht kaum treffsicher anklickbar ist).
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
            if child is descendant:
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
