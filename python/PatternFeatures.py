# FCProject: Parametrische Pattern-Features (Linear/Circular) analog zu PartDesign
import os
import FreeCAD as App
from FreeCAD import Vector, Placement, Rotation

try:
    import FreeCADGui as Gui
    from PySide6 import QtWidgets
    _GUI_AVAILABLE = True
except ImportError:
    _GUI_AVAILABLE = False

ICON_DIR = os.path.join(os.path.dirname(__file__), 'resources', 'icons')

_AXIS_VECTORS = {
    "X-Achse": Vector(1, 0, 0),
    "Y-Achse": Vector(0, 1, 0),
    "Z-Achse": Vector(0, 0, 1),
}


def _get_axis_vector(name):
    return _AXIS_VECTORS.get(name, Vector(1, 0, 0))


def _set_visibility(obj, visible):
    try:
        if obj is not None and obj.ViewObject:
            obj.ViewObject.Visibility = visible
    except Exception:
        pass


def _is_valid_source_element(element):
    """Validiert, ob ein Element als Pattern-Quelle taugt (Part, Body, Assembly, Link, oder Shape)."""
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

    name_lower = element.Name.lower() if hasattr(element, 'Name') else ''
    label_lower = element.Label.lower() if hasattr(element, 'Label') else ''
    if 'joint' in name_lower or 'joint' in label_lower:
        return False
    if 'bom' in name_lower or 'bom' in label_lower:
        return False
    return True


def _remove_after_recompute(doc, name):
    """Entfernt ein Objekt sicher außerhalb eines laufenden Recomputes."""
    try:
        doc.removeObject(name)
    except Exception as e:
        App.Console.PrintWarning(f"FCProject: Konnte '{name}' nicht entfernen: {e}\n")


def _deferred_remove(doc, name):
    """Verschiebt removeObject() per QTimer auf nach dem aktuellen Recompute.

    Wird removeObject() direkt aus execute() heraus aufgerufen, befindet
    sich das Zielobjekt oft noch im Zustand PendingRecompute — FreeCAD
    muss die Löschung dann in pendingRemove zurückstellen und meldet
    'pending remove … after recomputing' sowie 'still touched after recompute'.
    Ein QTimer(0)-Aufruf stellt sicher, dass die Löschung erst nach dem
    Recompute-Durchlauf erfolgt, wenn der PendingRecompute-Status gelöscht ist.
    """
    if _GUI_AVAILABLE:
        from PySide6 import QtCore
        QtCore.QTimer.singleShot(0, lambda: _remove_after_recompute(doc, name))
    else:
        _remove_after_recompute(doc, name)


def _sync_link_copies(doc, source, existing_copies, target_count, label_prefix):
    """Gleicht App::Link-Kopien von `source` idempotent auf `target_count` Stück ab.

    Bestehende Link-Objekte werden wiederverwendet (kein Re-Create bei jeder
    kleinen Änderung), überschüssige entfernt, fehlende neu erstellt.
    """
    copies = [c for c in existing_copies if c is not None and getattr(c, 'LinkedObject', None) == source]

    while len(copies) > target_count:
        obsolete = copies.pop()
        _deferred_remove(doc, obsolete.Name)

    while len(copies) < target_count:
        index = len(copies) + 1
        new_link = doc.addObject("App::Link", f"{source.Name}_Copy_{index}")
        new_link.LinkedObject = source
        copies.append(new_link)

    for i, copy in enumerate(copies, start=1):
        copy.Label = f"{label_prefix}{i}"

    return copies


def _get_assembly_joint_modules():
    """Importiert die echten Assembly-Workbench-Module für die Joint-Erstellung.

    Gibt (JointObject, UtilsAssembly) zurück, oder (None, None), falls die
    Assembly-Workbench nicht geladen ist (z.B. im Konsolenmodus ohne GUI).
    """
    try:
        import JointObject
        import UtilsAssembly
        return JointObject, UtilsAssembly
    except ImportError:
        return None, None


def _sub_name_for_child(child, root):
    """Ermittelt den Subnamen-Pfad von `child` relativ zu `root` (über Parents)."""
    if child is None or root is None or child == root:
        return None
    try:
        for parent_obj, path in (child.Parents or []):
            if parent_obj == root or parent_obj.Name == root.Name:
                return f"{path}{child.Name}" if path.endswith('.') else f"{path}.{child.Name}"
    except Exception:
        pass
    return child.Name


def _first_lcs_subname(element):
    """Sucht das erste lokale Koordinatensystem (LCS) im tatsächlichen Teil-Objekt
    und gibt dessen Subnamen-Pfad zurück.

    Bei App::Link-Ketten (z.B. Pattern-Kopie → Quell-Link → eigentliches Teil) wird
    die gesamte LinkedObject-Kette durchlaufen, bis das eigentliche Teil erreicht ist.
    App::Link ist für Subnamen transparent: der Subname relativ zum letzten Glied der
    Kette funktioniert genauso beim Zugriff über die Kopie.
    None, falls kein LCS gefunden wird.
    """
    if element is None:
        return None
    root = element
    seen = set()
    while True:
        rid = id(root)
        if rid in seen:
            break
        seen.add(rid)
        linked = getattr(root, 'LinkedObject', None)
        if linked is None:
            break
        root = linked
    try:
        children = list(root.OutList)
    except Exception:
        return None

    for child in children:
        if child is not None and child.isDerivedFrom('App::LocalCoordinateSystem'):
            return _sub_name_for_child(child, root)
    return None


def _build_joint_ref(element, lcs_subname):
    return [element, [lcs_subname or "", ""]]


def _compute_joint_offset2(ref1, ref2, UtilsAssembly):
    """Berechnet das Offset2 für ein Fixed-Joint, das die aktuelle relative
    Position von ref1 und ref2 einfriert. None bei Fehler.
    """
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
    except Exception:
        return None


def _sync_pattern_joints(doc, assembly, source, copies, existing_joints, label_prefix):
    """Gleicht Stern-Joints (Original <-> jede Kopie) idempotent mit `copies` ab.

    Die Joints sind rein informativ/dokumentarisch: sie machen die durch das
    Pattern erzeugte Beziehung als echtes Assembly-Joint im Baum sichtbar und
    editierbar, bestimmen aber NICHT die Position der Kopien - das bleibt
    Aufgabe von execute() (Pattern-Code bleibt maßgeblich). Schlägt die
    Joint-Erstellung fehl (z.B. Assembly-Workbench nicht geladen, kein
    GeoFeatureGroup), wird das ohne Auswirkung auf das Pattern selbst nur
    gewarnt - Joints sind ein optionales Add-on, kein hartes Erfordernis.
    """
    JointObject, UtilsAssembly = _get_assembly_joint_modules()
    if JointObject is None or not hasattr(assembly, 'newObject'):
        return [j for j in existing_joints if j is not None]

    # Bestehende Joints einsammeln, die noch zu einer aktuellen Kopie passen;
    # verwaiste Joints (Kopie wurde inzwischen entfernt, z.B. Count verkleinert) löschen.
    joint_by_copy = {}
    for joint in existing_joints:
        if joint is None:
            continue
        try:
            ref1_obj = joint.Reference1[0] if joint.Reference1 else None
            ref2_obj = joint.Reference2[0] if joint.Reference2 else None
        except Exception:
            continue
        other = ref2_obj if ref1_obj == source else (ref1_obj if ref2_obj == source else None)
        if other in copies and other not in joint_by_copy:
            joint_by_copy[other] = joint
        else:
            _deferred_remove(doc, joint.Name)

    try:
        joint_group = UtilsAssembly.getJointGroup(assembly)
    except Exception as e:
        App.Console.PrintWarning(f"FCProject: Konnte Joint-Gruppe nicht ermitteln: {e}\n")
        return list(joint_by_copy.values())

    ref1 = _build_joint_ref(source, _first_lcs_subname(source))
    result = []

    for i, copy in enumerate(copies, start=1):
        ref2 = _build_joint_ref(copy, _first_lcs_subname(copy))
        offset = _compute_joint_offset2(ref1, ref2, UtilsAssembly)

        joint = joint_by_copy.get(copy)
        if joint is None:
            try:
                joint = joint_group.newObject("App::FeaturePython", f"{label_prefix}Joint_{i}")
                joint.Label = f"{label_prefix}Joint_{i}"
                JointObject.Joint(joint, 0)  # Index 0 = "Fixed"
                if _GUI_AVAILABLE and joint.ViewObject:
                    JointObject.ViewProviderJoint(joint.ViewObject)
                joint.Reference1 = ref1
                joint.Reference2 = ref2
            except Exception as e:
                App.Console.PrintWarning(
                    f"FCProject: Joint zwischen '{source.Label}' und '{copy.Label}' konnte nicht erstellt werden: {e}\n"
                )
                continue

        if offset is not None:
            try:
                joint.Offset2 = offset
            except Exception:
                pass

        try:
            joint_group.purgeTouched()
            joint.purgeTouched()
        except Exception:
            pass

        result.append(joint)

    return result


def _pattern_get_sub_object(obj, subname, ret_type, mat, transform, depth):
    """Löst einen Pfad-Abschnitt über die eigene "Group"-Property auf.

    App::FeaturePython besitzt (anders als App::DocumentObjectGroupPython mit
    GroupExtension) keine eingebaute Pfadauflösung durch seine Group-Kinder.
    Ohne diesen Hook schlägt jede Selektion/Bearbeitung eines Objekts
    *innerhalb* einer Pattern-Kopie fehl ("Sub-object ... not found"), da
    FreeCAD den Pfad "LinearPattern.Copy_1.Sketch" nicht durchnavigieren kann.
    Bildet exakt die Logik von GroupExtension::extensionGetSubObject nach.
    """
    if not subname or '.' not in subname:
        return False

    dot = subname.index('.')
    name = subname[:dot]
    rest = subname[dot + 1:]

    target = None
    if name.startswith('$'):
        label = name[1:]
        for child in obj.Group:
            if child.Label == label:
                target = child
                break
    else:
        candidate = obj.Document.getObject(name)
        if candidate in list(obj.Group):
            target = candidate

    if target is None:
        return False

    return target.getSubObject(rest, retType=ret_type, matrix=mat, transform=True, depth=depth + 1)


def _axis_from_reference(ref_obj, ref_sub):
    """Ermittelt (Achsenvektor, Punkt auf der Achse) aus einer Referenz.

    Unterstützt: gerade Kanten (Edge-Subelement) und Linien-/Datum-Achsen-
    Objekte (Achse = lokale Z-Richtung der Placement, Punkt = Placement.Base).
    Gibt None zurück, wenn die Referenz keine gültige Achse beschreibt.
    """
    if ref_obj is None:
        return None
    try:
        if ref_sub and ref_sub.startswith('Edge'):
            edge = ref_obj.Shape.getElement(ref_sub)
            if len(edge.Vertexes) < 2:
                return None
            p1 = edge.Vertexes[0].Point
            p2 = edge.Vertexes[-1].Point
            direction = p2 - p1
            if direction.Length < 1e-9:
                return None
            return direction.normalize(), p1

        rot = ref_obj.Placement.Rotation
        return rot.multVec(Vector(0, 0, 1)), ref_obj.Placement.Base
    except Exception:
        return None


def _resolve_rotation_axis(obj):
    """Liefert (Achsenvektor, Punkt auf der Achse) für das Pattern.

    Ist ReferenceAxis gesetzt und gültig, hat sie Vorrang vor der globalen
    X/Y/Z-Achse (Eigenschaft "Axis"), die weiterhin als einfacher Standardfall
    durch den globalen Ursprung wirkt.
    """
    ref = getattr(obj, 'ReferenceAxis', None)
    if ref and ref[0] is not None:
        ref_sub = ref[1][0] if ref[1] else None
        axis = _axis_from_reference(ref[0], ref_sub)
        if axis is not None:
            return axis
        App.Console.PrintWarning(
            f"FCProject: Pattern '{obj.Label}' hat eine ungültige ReferenceAxis, verwende '{obj.Axis}' statt.\n"
        )
    return _get_axis_vector(obj.Axis), Vector(0, 0, 0)


def _check_reference_creates_cycle(obj, candidate):
    """Prüft, ob die neue Abhängigkeit obj -> candidate (via ReferenceAxis) einen
    DAG-Zyklus erzeugen würde, BEVOR die Eigenschaft tatsächlich gesetzt wird.

    Eine neue Kante obj -> candidate schließt genau dann einen Zyklus, wenn
    candidate im *bestehenden* Abhängigkeitsgraphen schon (transitiv) von obj
    abhängt, d.h. ein Pfad candidate -> ... -> obj existiert. Das prüfen wir
    über das von FreeCAD bereitgestellte getPathsByOutList().

    Gibt den gefundenen Pfad (Liste von DocumentObject, candidate...obj) zurück,
    oder None, falls keine Zyklusgefahr besteht.
    """
    if candidate is None or candidate == obj:
        return None
    try:
        paths = candidate.getPathsByOutList(obj)
    except Exception:
        return None
    return paths[0] if paths else None


def _pattern_get_sub_objects(obj, reason):
    return [f"{child.Name}." for child in obj.Group if child is not None and child.isAttachedToDocument()]


class LinearPatternProxy:
    """Proxy für ein lineares Pattern-Feature (App::FeaturePython)."""

    def __init__(self, obj):
        self._add_properties(obj)
        obj.Proxy = self

    def _add_properties(self, obj):
        if not hasattr(obj, 'Group'):
            #HACK:
            # PropertyLinkListHidden statt PropertyLinkList: Kopien dürfen auf
            # Objekte verweisen, die bereits einer Assembly/einem Part zugeordnet
            # sind, ohne den GeoFeatureGroup-Scope-Check ("out of scope") auszulösen.
            obj.addProperty("App::PropertyLinkListHidden", "Group", "Pattern", "Vom Pattern erzeugte Kopien", locked=True)
        if not hasattr(obj, 'SourceElement'):
            # PropertyXLink statt PropertyLink: Quell-Element darf auch in einem
            # anderen Dokument liegen (z.B. ein per Link eingebundenes Teil-Dokument).
            obj.addProperty("App::PropertyXLink", "SourceElement", "Pattern", "Zu wiederholendes Element")
        if not hasattr(obj, 'Direction'):
            obj.addProperty("App::PropertyEnumeration", "Direction", "Pattern", "Richtung der Wiederholung")
            obj.Direction = ["X-Achse", "Y-Achse", "Z-Achse"]
        if not hasattr(obj, 'Spacing'):
            obj.addProperty("App::PropertyDistance", "Spacing", "Pattern", "Abstand zwischen den Elementen (mm)")
            obj.Spacing = 600.0
        if not hasattr(obj, 'Count'):
            obj.addProperty("App::PropertyInteger", "Count", "Pattern", "Anzahl Kopien (zusätzlich zum Original)")
            obj.Count = 3
        if not hasattr(obj, 'Joints'):
            # Hidden, wie Group: rein dokumentarisch, kein Einfluss auf den DAG.
            obj.addProperty("App::PropertyLinkListHidden", "Joints", "Pattern",
                             "Vom Pattern erzeugte Fixed-Joints (Original<->jede Kopie), rein informativ", locked=True)

    def onChanged(self, obj, prop):
        if prop == 'Count' and obj.Count < 0:
            obj.Count = 0

    def getSubObject(self, obj, subname, ret_type, mat, transform, depth):
        return _pattern_get_sub_object(obj, subname, ret_type, mat, transform, depth)

    def getSubObjects(self, obj, reason):
        return _pattern_get_sub_objects(obj, reason)

    def execute(self, obj):
        source = obj.SourceElement
        if source is None:
            App.Console.PrintWarning(f"FCProject: Pattern '{obj.Label}' hat kein SourceElement.\n")
            return

        base = source.Placement
        axis_vector = _get_axis_vector(obj.Direction)
        spacing = obj.Spacing.Value

        copies = _sync_link_copies(obj.Document, source, list(obj.Group), obj.Count, f"{source.Label}_Copy_")

        for i, copy in enumerate(copies, start=1):
            offset = axis_vector * (spacing * i)
            copy.Placement = Placement(base.Base + offset, base.Rotation)
            _set_visibility(copy, True)

        obj.Group = copies

        assembly = obj.getParentGeoFeatureGroup()
        if assembly is not None:
            try:
                obj.Joints = _sync_pattern_joints(obj.Document, assembly, source, copies, list(obj.Joints), f"{obj.Name}_")
            except Exception as e:
                App.Console.PrintWarning(f"FCProject: Pattern-Joints konnten nicht synchronisiert werden: {e}\n")

    def onDocumentRestored(self, obj):
        self._add_properties(obj)
        obj.Proxy = self

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


class CircularPatternProxy:
    """Proxy für ein zirkulares Pattern-Feature (echtes PolarPattern wie in PartDesign)."""

    def __init__(self, obj):
        self._add_properties(obj)
        obj.Proxy = self

    def _add_properties(self, obj):
        if not hasattr(obj, 'Group'):
            # PropertyLinkListHidden statt PropertyLinkList: Kopien dürfen auf
            # Objekte verweisen, die bereits einer Assembly/einem Part zugeordnet
            # sind, ohne den GeoFeatureGroup-Scope-Check ("out of scope") auszulösen.
            obj.addProperty("App::PropertyLinkListHidden", "Group", "Pattern", "Vom Pattern erzeugte Kopien", locked=True)
        if not hasattr(obj, 'SourceElement'):
            # PropertyXLink statt PropertyLink: Quell-Element darf auch in einem
            # anderen Dokument liegen (z.B. ein per Link eingebundenes Teil-Dokument).
            obj.addProperty("App::PropertyXLink", "SourceElement", "Pattern", "Zu wiederholendes Element")
        if not hasattr(obj, 'Axis'):
            obj.addProperty("App::PropertyEnumeration", "Axis", "Pattern", "Rotationsachse (durch den globalen Ursprung), falls keine ReferenceAxis gewählt ist")
            obj.Axis = ["X-Achse", "Y-Achse", "Z-Achse"]
            obj.Axis = "Z-Achse"
        _ref_axis_type = "App::PropertyXLinkSub"
        _ref_axis_tip = "Datum-Achse, gerade Kante oder Linienobjekt als Rotationsachse (überschreibt 'Axis')"
        if not hasattr(obj, 'ReferenceAxis'):
            # Normale (nicht versteckte) Link-Property: Änderungen an der Referenz
            # lösen weiterhin automatisch ein Neuberechnen des Patterns aus. Ob die
            # Auswahl einen DAG-Zyklus erzeugen würde, wird stattdessen VOR der
            # Zuweisung im Task-Panel geprüft (siehe _check_reference_creates_cycle),
            # damit der Nutzer die Referenz von vornherein passend wählen kann.
            # PropertyXLink* statt PropertyLink*, damit die Referenz auch in einem
            # anderen Dokument liegen darf.
            obj.addProperty(_ref_axis_type, "ReferenceAxis", "Pattern", _ref_axis_tip)
        elif obj.getTypeIdOfProperty('ReferenceAxis') != _ref_axis_type:
            # Migration bereits gespeicherter Pattern-Objekte vom vorherigen
            # (versteckten) Property-Typ zurück auf den normalen Typ.
            old_value = obj.ReferenceAxis
            obj.removeProperty('ReferenceAxis')
            obj.addProperty(_ref_axis_type, "ReferenceAxis", "Pattern", _ref_axis_tip)
            if old_value:
                obj.ReferenceAxis = old_value
        if not hasattr(obj, 'Angle'):
            obj.addProperty("App::PropertyAngle", "Angle", "Pattern", "Gesamtwinkel des Patterns")
            obj.Angle = 360.0
        if not hasattr(obj, 'Count'):
            obj.addProperty("App::PropertyInteger", "Count", "Pattern", "Anzahl Kopien (zusätzlich zum Original)")
            obj.Count = 5
        if not hasattr(obj, 'Joints'):
            # Hidden, wie Group: rein dokumentarisch, kein Einfluss auf den DAG.
            obj.addProperty("App::PropertyLinkListHidden", "Joints", "Pattern",
                             "Vom Pattern erzeugte Fixed-Joints (Original<->jede Kopie), rein informativ", locked=True)

    def onChanged(self, obj, prop):
        if prop == 'Count' and obj.Count < 0:
            obj.Count = 0

    def getSubObject(self, obj, subname, ret_type, mat, transform, depth):
        return _pattern_get_sub_object(obj, subname, ret_type, mat, transform, depth)

    def getSubObjects(self, obj, reason):
        return _pattern_get_sub_objects(obj, reason)

    def execute(self, obj):
        source = obj.SourceElement
        if source is None:
            App.Console.PrintWarning(f"FCProject: Pattern '{obj.Label}' hat kein SourceElement.\n")
            return

        base = source.Placement
        axis_vector, axis_point = _resolve_rotation_axis(obj)
        angle = obj.Angle.Value
        count = obj.Count

        copies = _sync_link_copies(obj.Document, source, list(obj.Group), count, f"{source.Label}_Circular_")

        if count > 0:
            total = count + 1
            step = angle / total if abs(angle - 360.0) < 1e-7 else angle / count
        else:
            step = 0.0

        for i, copy in enumerate(copies, start=1):
            rot = Rotation(axis_vector, step * i)
            new_base = axis_point + rot.multVec(base.Base - axis_point)
            new_rot = rot.multiply(base.Rotation)
            copy.Placement = Placement(new_base, new_rot)
            _set_visibility(copy, True)

        obj.Group = copies

        assembly = obj.getParentGeoFeatureGroup()
        if assembly is not None:
            try:
                obj.Joints = _sync_pattern_joints(obj.Document, assembly, source, copies, list(obj.Joints), f"{obj.Name}_")
            except Exception as e:
                App.Console.PrintWarning(f"FCProject: Pattern-Joints konnten nicht synchronisiert werden: {e}\n")

    def onDocumentRestored(self, obj):
        self._add_properties(obj)
        obj.Proxy = self

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


if _GUI_AVAILABLE:

    class ViewProviderPattern:
        """Gemeinsamer ViewProvider für Linear- und Circular-Pattern-Features.

        Die Pattern-Objekte sind App::FeaturePython (nicht GroupPython), damit
        die eigene "Group"-Property als App::PropertyLinkListHidden angelegt
        werden kann (kein GeoFeatureGroup-Scope-Konflikt mit der Assembly).
        Die Tree-Verschachtelung der Kopien muss daher hier manuell erfolgen.
        """

        def __init__(self, vobj):
            vobj.Proxy = self

        def attach(self, vobj):
            self.Object = vobj.Object

        def claimChildren(self):
            return list(self.Object.Group)

        def getIcon(self):
            # Beim Laden eines gespeicherten Dokuments ruft FreeCAD __setstate__
            # statt __init__ auf - das Icon wird daher hier anhand des Proxy-Typs
            # bestimmt statt aus einem beim Restore nicht vorhandenen Attribut.
            if isinstance(self.Object.Proxy, CircularPatternProxy):
                return os.path.join(ICON_DIR, 'circular_pattern.svg')
            return os.path.join(ICON_DIR, 'assembly_pattern.svg')

        def doubleClicked(self, vobj):
            Gui.ActiveDocument.setEdit(vobj.Object.Name)
            return True

        def setEdit(self, vobj, mode=0):
            proxy = vobj.Object.Proxy
            if isinstance(proxy, LinearPatternProxy):
                Gui.Control.showDialog(LinearPatternTaskPanel(vobj.Object))
            elif isinstance(proxy, CircularPatternProxy):
                Gui.Control.showDialog(CircularPatternTaskPanel(vobj.Object))
            else:
                return False
            return True

        def unsetEdit(self, vobj, mode=0):
            Gui.Control.closeDialog()
            return True

        def __getstate__(self):
            return None

        def __setstate__(self, state):
            return None


    class LinearPatternTaskPanel:
        """Aufgabenfenster (Gui.Control-Task-Panel) zum Bearbeiten eines linearen Patterns."""

        def __init__(self, obj):
            self.obj = obj
            self._snapshot = {
                'Direction': obj.Direction,
                'Spacing': obj.Spacing.Value,
                'Count': obj.Count,
            }

            self.form = QtWidgets.QWidget()
            self.form.setWindowTitle("FCProject: Lineares Pattern bearbeiten")
            layout = QtWidgets.QVBoxLayout(self.form)

            layout.addWidget(QtWidgets.QLabel("Pattern-Richtung:"))
            self.direction_combo = QtWidgets.QComboBox()
            self.direction_combo.addItems(["X-Achse", "Y-Achse", "Z-Achse"])
            self.direction_combo.setCurrentText(obj.Direction)
            self.direction_combo.currentTextChanged.connect(self._on_change)
            layout.addWidget(self.direction_combo)

            layout.addWidget(QtWidgets.QLabel("Abstand zwischen Elementen (mm):"))
            self.spacing_spinbox = QtWidgets.QDoubleSpinBox()
            self.spacing_spinbox.setDecimals(3)
            self.spacing_spinbox.setMinimum(0.001)
            self.spacing_spinbox.setMaximum(100000.0)
            self.spacing_spinbox.setValue(obj.Spacing.Value)
            self.spacing_spinbox.valueChanged.connect(self._on_change)
            layout.addWidget(self.spacing_spinbox)

            layout.addWidget(QtWidgets.QLabel("Anzahl Kopien:"))
            self.count_spinbox = QtWidgets.QSpinBox()
            self.count_spinbox.setMinimum(0)
            self.count_spinbox.setMaximum(500)
            self.count_spinbox.setValue(obj.Count)
            self.count_spinbox.valueChanged.connect(self._on_change)
            layout.addWidget(self.count_spinbox)

        def _on_change(self, *_args):
            self.obj.Direction = self.direction_combo.currentText()
            self.obj.Spacing = self.spacing_spinbox.value()
            self.obj.Count = self.count_spinbox.value()
            self.obj.Document.recompute()

        def accept(self):
            self.obj.Document.recompute()
            Gui.ActiveDocument.resetEdit()
            return True

        def reject(self):
            self.obj.Direction = self._snapshot['Direction']
            self.obj.Spacing = self._snapshot['Spacing']
            self.obj.Count = self._snapshot['Count']
            self.obj.Document.recompute()
            Gui.ActiveDocument.resetEdit()
            return True

        def getStandardButtons(self):
            return int(QtWidgets.QDialogButtonBox.Ok.value) | int(QtWidgets.QDialogButtonBox.Cancel.value)


    class CircularPatternTaskPanel:
        """Aufgabenfenster (Gui.Control-Task-Panel) zum Bearbeiten eines zirkularen Patterns."""

        def __init__(self, obj):
            self.obj = obj
            self._snapshot = {
                'Axis': obj.Axis,
                'ReferenceAxis': obj.ReferenceAxis,
                'Angle': obj.Angle.Value,
                'Count': obj.Count,
            }

            self.form = QtWidgets.QWidget()
            self.form.setWindowTitle("FCProject: Zirkulares Pattern bearbeiten")
            layout = QtWidgets.QVBoxLayout(self.form)

            layout.addWidget(QtWidgets.QLabel("Rotationsachse (Standard, durch den globalen Ursprung):"))
            self.axis_combo = QtWidgets.QComboBox()
            self.axis_combo.addItems(["X-Achse", "Y-Achse", "Z-Achse"])
            self.axis_combo.setCurrentText(obj.Axis)
            self.axis_combo.currentTextChanged.connect(self._on_change)
            layout.addWidget(self.axis_combo)

            layout.addWidget(QtWidgets.QLabel(
                "Oder: Datum-Achse, Kante oder Linienobjekt in 3D-Ansicht/Baum auswählen:"
            ))
            self.reference_label = QtWidgets.QLabel(self._format_reference(obj.ReferenceAxis))
            self.reference_label.setWordWrap(True)
            layout.addWidget(self.reference_label)

            buttons_row = QtWidgets.QHBoxLayout()
            self.pick_axis_button = QtWidgets.QPushButton("Auswahl als Achse verwenden")
            self.pick_axis_button.clicked.connect(self._on_pick_axis)
            buttons_row.addWidget(self.pick_axis_button)
            self.clear_axis_button = QtWidgets.QPushButton("Zurücksetzen (X/Y/Z verwenden)")
            self.clear_axis_button.clicked.connect(self._on_clear_axis)
            buttons_row.addWidget(self.clear_axis_button)
            layout.addLayout(buttons_row)

            layout.addWidget(QtWidgets.QLabel("Gesamtwinkel (°):"))
            self.angle_spinbox = QtWidgets.QDoubleSpinBox()
            self.angle_spinbox.setDecimals(2)
            self.angle_spinbox.setMinimum(1.0)
            self.angle_spinbox.setMaximum(360.0)
            self.angle_spinbox.setValue(obj.Angle.Value)
            self.angle_spinbox.valueChanged.connect(self._on_change)
            layout.addWidget(self.angle_spinbox)

            layout.addWidget(QtWidgets.QLabel("Anzahl Kopien:"))
            self.count_spinbox = QtWidgets.QSpinBox()
            self.count_spinbox.setMinimum(0)
            self.count_spinbox.setMaximum(500)
            self.count_spinbox.setValue(obj.Count)
            self.count_spinbox.valueChanged.connect(self._on_change)
            layout.addWidget(self.count_spinbox)

        @staticmethod
        def _format_reference(ref):
            if not ref or ref[0] is None:
                return "Keine ausgewählt (es wird die obige globale Achse verwendet)"
            ref_obj, subs = ref
            sub = subs[0] if subs else ""
            return f"{ref_obj.Label}{'.' + sub if sub else ''}"

        def _on_change(self, *_args):
            self.obj.Axis = self.axis_combo.currentText()
            self.obj.Angle = self.angle_spinbox.value()
            self.obj.Count = self.count_spinbox.value()
            self.obj.Document.recompute()

        def _on_pick_axis(self):
            selection = Gui.Selection.getSelectionEx()
            if len(selection) != 1 or len(selection[0].SubElementNames) > 1:
                QtWidgets.QMessageBox.warning(
                    self.form,
                    "FCProject Pattern",
                    "Bitte genau eine Kante, Datum-Achse oder ein Linienobjekt in der 3D-Ansicht oder im Baum auswählen."
                )
                return

            sel = selection[0]
            sub = sel.SubElementNames[0] if sel.SubElementNames else None
            if _axis_from_reference(sel.Object, sub) is None:
                QtWidgets.QMessageBox.warning(
                    self.form,
                    "FCProject Pattern",
                    "Die Auswahl ist keine gültige Achse (erwartet: gerade Kante, Datum-Achse oder Linienobjekt)."
                )
                return

            cycle_path = _check_reference_creates_cycle(self.obj, sel.Object)
            if cycle_path is not None:
                # cycle_path = [Auswahl, ..., Pattern] (bestehender Pfad). Die neue
                # Kante Pattern -> Auswahl (ReferenceAxis) würde ihn zum Kreis schließen.
                chain = " → ".join(o.Label for o in cycle_path)
                QtWidgets.QMessageBox.warning(
                    self.form,
                    "FCProject Pattern",
                    "Diese Auswahl kann nicht als Achse verwendet werden: Sie würde eine "
                    "zirkuläre Abhängigkeit erzeugen (das Pattern würde indirekt von sich "
                    f"selbst abhängen).\n\nBestehende Abhängigkeitskette:\n{chain}\n\n"
                    f"Die neue Verknüpfung '{self.obj.Label} → {sel.Object.Label}' würde diese "
                    "Kette zu einem Kreis schließen.\n\n"
                    "Wähle stattdessen eine Achse/Kante, die nicht (auch nicht indirekt über "
                    "die Assembly) vom Pattern selbst abhängt - z.B. eine Kante am Quell-Element."
                )
                return

            self.obj.ReferenceAxis = (sel.Object, [sub] if sub else [])
            self.reference_label.setText(self._format_reference(self.obj.ReferenceAxis))
            self.obj.Document.recompute()

        def _on_clear_axis(self):
            self.obj.ReferenceAxis = None
            self.reference_label.setText(self._format_reference(None))
            self.obj.Document.recompute()

        def accept(self):
            self.obj.Document.recompute()
            Gui.ActiveDocument.resetEdit()
            return True

        def reject(self):
            self.obj.Axis = self._snapshot['Axis']
            self.obj.ReferenceAxis = self._snapshot['ReferenceAxis']
            self.obj.Angle = self._snapshot['Angle']
            self.obj.Count = self._snapshot['Count']
            self.obj.Document.recompute()
            Gui.ActiveDocument.resetEdit()
            return True

        def getStandardButtons(self):
            return int(QtWidgets.QDialogButtonBox.Ok.value) | int(QtWidgets.QDialogButtonBox.Cancel.value)


def make_linear_pattern(doc, assembly, source_element, direction="X-Achse", spacing=600.0, count=3):
    """Erstellt ein parametrisches lineares Pattern-Feature und hängt es in die Assembly ein."""
    doc.openTransaction("FCProject Linear Pattern")
    try:
        obj = doc.addObject("App::FeaturePython", "LinearPattern")
        obj.Label = f"Linear Pattern: {source_element.Label}"
        LinearPatternProxy(obj)
        obj.SourceElement = source_element
        obj.Direction = direction
        obj.Spacing = spacing
        obj.Count = count

        if hasattr(assembly, 'addObject'):
            assembly.addObject(obj)

        if _GUI_AVAILABLE and obj.ViewObject:
            ViewProviderPattern(obj.ViewObject)

        doc.recompute()
        doc.commitTransaction()
        return obj
    except Exception:
        doc.abortTransaction()
        raise


def make_circular_pattern(doc, assembly, source_element, axis="Z-Achse", angle=360.0, count=5):
    """Erstellt ein parametrisches zirkulares (Polar-)Pattern-Feature und hängt es in die Assembly ein."""
    doc.openTransaction("FCProject Circular Pattern")
    try:
        obj = doc.addObject("App::FeaturePython", "CircularPattern")
        obj.Label = f"Circular Pattern: {source_element.Label}"
        CircularPatternProxy(obj)
        obj.SourceElement = source_element
        obj.Axis = axis
        obj.Angle = angle
        obj.Count = count

        if hasattr(assembly, 'addObject'):
            assembly.addObject(obj)

        if _GUI_AVAILABLE and obj.ViewObject:
            ViewProviderPattern(obj.ViewObject)

        doc.recompute()
        doc.commitTransaction()
        return obj
    except Exception:
        doc.abortTransaction()
        raise
