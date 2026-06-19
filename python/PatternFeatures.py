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


def _sync_link_copies(doc, source, existing_copies, target_count, label_prefix):
    """Gleicht App::Link-Kopien von `source` idempotent auf `target_count` Stück ab.

    Bestehende Link-Objekte werden wiederverwendet (kein Re-Create bei jeder
    kleinen Änderung), überschüssige entfernt, fehlende neu erstellt.
    """
    copies = [c for c in existing_copies if c is not None and getattr(c, 'LinkedObject', None) == source]

    while len(copies) > target_count:
        obsolete = copies.pop()
        try:
            doc.removeObject(obsolete.Name)
        except Exception as e:
            App.Console.PrintWarning(f"FCProject: Konnte Kopie '{obsolete.Name}' nicht entfernen: {e}\n")

    while len(copies) < target_count:
        index = len(copies) + 1
        new_link = doc.addObject("App::Link", f"{source.Name}_Copy_{index}")
        new_link.LinkedObject = source
        copies.append(new_link)

    for i, copy in enumerate(copies, start=1):
        copy.Label = f"{label_prefix}{i}"

    return copies


class LinearPatternProxy:
    """Proxy für ein lineares Pattern-Feature (App::FeaturePython)."""

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
            obj.addProperty("App::PropertyLink", "SourceElement", "Pattern", "Zu wiederholendes Element")
        if not hasattr(obj, 'Direction'):
            obj.addProperty("App::PropertyEnumeration", "Direction", "Pattern", "Richtung der Wiederholung")
            obj.Direction = ["X-Achse", "Y-Achse", "Z-Achse"]
        if not hasattr(obj, 'Spacing'):
            obj.addProperty("App::PropertyDistance", "Spacing", "Pattern", "Abstand zwischen den Elementen (mm)")
            obj.Spacing = 600.0
        if not hasattr(obj, 'Count'):
            obj.addProperty("App::PropertyInteger", "Count", "Pattern", "Anzahl Kopien (zusätzlich zum Original)")
            obj.Count = 3

    def onChanged(self, obj, prop):
        if prop == 'Count' and obj.Count < 0:
            obj.Count = 0

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
            obj.addProperty("App::PropertyLink", "SourceElement", "Pattern", "Zu wiederholendes Element")
        if not hasattr(obj, 'Axis'):
            obj.addProperty("App::PropertyEnumeration", "Axis", "Pattern", "Rotationsachse (durch den globalen Ursprung)")
            obj.Axis = ["X-Achse", "Y-Achse", "Z-Achse"]
            obj.Axis = "Z-Achse"
        if not hasattr(obj, 'Angle'):
            obj.addProperty("App::PropertyAngle", "Angle", "Pattern", "Gesamtwinkel des Patterns")
            obj.Angle = 360.0
        if not hasattr(obj, 'Count'):
            obj.addProperty("App::PropertyInteger", "Count", "Pattern", "Anzahl Kopien (zusätzlich zum Original)")
            obj.Count = 5

    def onChanged(self, obj, prop):
        if prop == 'Count' and obj.Count < 0:
            obj.Count = 0

    def execute(self, obj):
        source = obj.SourceElement
        if source is None:
            App.Console.PrintWarning(f"FCProject: Pattern '{obj.Label}' hat kein SourceElement.\n")
            return

        base = source.Placement
        axis_vector = _get_axis_vector(obj.Axis)
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
            new_base = rot.multVec(base.Base)
            new_rot = rot.multiply(base.Rotation)
            copy.Placement = Placement(new_base, new_rot)
            _set_visibility(copy, True)

        obj.Group = copies

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

        def __init__(self, vobj, icon_path):
            vobj.Proxy = self
            self.icon_path = icon_path

        def attach(self, vobj):
            self.Object = vobj.Object

        def claimChildren(self):
            return list(self.Object.Group)

        def getIcon(self):
            return self.icon_path

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
                'Angle': obj.Angle.Value,
                'Count': obj.Count,
            }

            self.form = QtWidgets.QWidget()
            self.form.setWindowTitle("FCProject: Zirkulares Pattern bearbeiten")
            layout = QtWidgets.QVBoxLayout(self.form)

            layout.addWidget(QtWidgets.QLabel("Rotationsachse:"))
            self.axis_combo = QtWidgets.QComboBox()
            self.axis_combo.addItems(["X-Achse", "Y-Achse", "Z-Achse"])
            self.axis_combo.setCurrentText(obj.Axis)
            self.axis_combo.currentTextChanged.connect(self._on_change)
            layout.addWidget(self.axis_combo)

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

        def _on_change(self, *_args):
            self.obj.Axis = self.axis_combo.currentText()
            self.obj.Angle = self.angle_spinbox.value()
            self.obj.Count = self.count_spinbox.value()
            self.obj.Document.recompute()

        def accept(self):
            self.obj.Document.recompute()
            Gui.ActiveDocument.resetEdit()
            return True

        def reject(self):
            self.obj.Axis = self._snapshot['Axis']
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
            ViewProviderPattern(obj.ViewObject, os.path.join(ICON_DIR, 'assembly_pattern.svg'))

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
            ViewProviderPattern(obj.ViewObject, os.path.join(ICON_DIR, 'circular_pattern.svg'))

        doc.recompute()
        doc.commitTransaction()
        return obj
    except Exception:
        doc.abortTransaction()
        raise
