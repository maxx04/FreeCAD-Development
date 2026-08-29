# FCProject: "Interface-Positionierung" - erster Baustein des groesseren Interface-Konzepts
# (Referenzelemente Achse+Flaeche/LCS am Teil + Gegenelemente bei Einbau -> solver-freie
# Ausrichtung, siehe project_fcproject_interface_feature_concept-Memory), aufbauend auf der
# Import-Komponente aus ImportComponentCommand.py (2026-08-28, Nutzerentscheidung: "LCS als
# Interfaces Anfang" - statt eines eigenen Referenzelement-Systems nutzen wir FreeCADs eigenes,
# bewaehrtes Attachment-System (Part::LocalCoordinateSystem) als Referenzelement-Typ).
#
# Ablauf (2026-08-29, nach Nutzer-Feedback auf FeaturePython umgebaut): der Nutzer legt in der
# QUELLE (dem zu importierenden Dokument) ein LCS an der gewuenschten Andock-Stelle an (per
# normalem FreeCAD-Attachment - Flaeche/Kante waehlen), und in der ZIEL-Baugruppe ein zweites LCS
# an der Gegenstelle. Zum Anlegen eines Interfaces waehlt der Nutzer zuerst die Import-Komponente
# aus und startet den Befehl - das legt ein neues, leeres InterfacePlacement-Feature in der
# "Interfaces"-Gruppe an (analog zur "Joints"-Gruppe von FreeCADs eigenem Assembly-Modul) und
# oeffnet direkt dessen Aufgabenfenster, in dem Quell-/Ziel-LCS per Knopfdruck + Anklicken im
# Baum/3D-Fenster ausgewaehlt werden (kein Vorab-Auswaehlen zweier LCS mehr noetig). Ein
# Doppelklick auf ein bestehendes Interface im Baum oeffnet dasselbe Aufgabenfenster wieder, um
# die Zuordnung nachzuschauen/zu korrigieren. Das Feature berechnet bei JEDER Neuberechnung die
# Placement der Import-Komponente automatisch aus der aktuellen Lage beider LCS neu (Nutzerwunsch:
# "bei jedem Umrechnen die zwei LCS zusammenhalten") - kein lebendiger Joint, keine
# Solver-Abhaengigkeit, nur eine direkte geometrische Berechnung.
import os
import weakref

import FreeCAD as App

try:
    import FreeCADGui as Gui
    from PySide6 import QtWidgets
    _GUI_AVAILABLE = True
except ImportError:
    _GUI_AVAILABLE = False

ICON_DIR = os.path.join(os.path.dirname(__file__), 'resources', 'icons')

LCS_TYPE = "Part::LocalCoordinateSystem"
INTERFACES_GROUP_LABEL = "Interfaces"


def find_interface_placement_for(import_link):
    """Findet ein bereits bestehendes InterfacePlacement-Feature fuer 'import_link', falls
    vorhanden - beim erneuten Bearbeiten soll kein ZWEITES Feature entstehen, das gegen dasselbe
    Import-Objekt schreibt (zwei Features, die dieselbe ImportComponent.Placement setzen, wuerden
    sich in der Recompute-Reihenfolge gegenseitig ueberschreiben - nicht diagnostizierbar, welches
    zuletzt gewinnt)."""
    for obj in import_link.Document.Objects:
        if isinstance(getattr(obj, "Proxy", None), InterfacePlacementProxy):
            if getattr(obj, "ImportComponent", None) is import_link:
                return obj
    return None


def is_interface_placement(obj):
    return obj is not None and isinstance(getattr(obj, "Proxy", None), InterfacePlacementProxy)


class InterfacePlacementProxy:
    """Proxy fuer das InterfacePlacement-Feature (App::FeaturePython). Haelt Quell-/Ziel-LCS und
    die zu positionierende Import-Komponente als Eigenschaften und berechnet bei jeder
    Neuberechnung (execute()) die passende Placement neu - lebendig, nicht mehr nur einmalig."""

    def __init__(self, obj):
        self._add_properties(obj)
        obj.Proxy = self

    def _add_properties(self, obj):
        if not hasattr(obj, 'SourceLCS'):
            # PropertyXLink statt PropertyLink: die Quell-LCS liegt im PDM-Standardfall in einem
            # eigenen, per App::Link importierten Quelldokument (siehe SourceElement in
            # PatternFeatures.py/ReferencePlane in SectionSketchFeature.py - gleicher Grund).
            obj.addProperty(
                "App::PropertyXLink", "SourceLCS", "Interface",
                "LCS in der Quelle (Andock-Stelle am importierten Teil)"
            )
        if not hasattr(obj, 'TargetLCS'):
            obj.addProperty(
                "App::PropertyXLink", "TargetLCS", "Interface",
                "LCS im Ziel (Gegenstelle in der Baugruppe)"
            )
        if not hasattr(obj, 'ImportComponent'):
            # Hidden, wie Sketch in SectionSketchFeature.py: dieser Link ist rein informativ
            # ("wen positioniere ich") und darf NICHT in FreeCADs Abhaengigkeitsgraph auftauchen -
            # obj SCHREIBT in ImportComponent.Placement, haengt aber inhaltlich nicht von ihm ab.
            obj.addProperty(
                "App::PropertyLinkHidden", "ImportComponent", "Interface",
                "Zu positionierende Import-Komponente (App::Link, siehe ImportComponentCommand.py)",
                locked=True
            )
        if not hasattr(obj, 'Active'):
            obj.addProperty(
                "App::PropertyBool", "Active", "Interface",
                "Bei Bedarf abschalten, um die Neuberechnung bei jeder Baugruppen-Aktualisierung zu sparen"
            )
            obj.Active = True

    def onChanged(self, obj, prop):
        pass

    def execute(self, obj):
        if not obj.Active:
            return

        source_lcs = obj.SourceLCS
        target_lcs = obj.TargetLCS
        import_link = obj.ImportComponent

        if source_lcs is None or target_lcs is None:
            # Kein Fehler: ein frisch angelegtes Interface hat noch keine LCS zugewiesen, bis der
            # Nutzer sie im Aufgabenfenster auswaehlt - stiller Rueckzug statt Warnspam.
            return
        if import_link is None:
            App.Console.PrintWarning(
                f"FCProject: InterfacePlacement '{obj.Label}' hat keine ImportComponent.\n"
            )
            return

        # newImportPlacement * sourceLcsLocal = targetLcsGlobal
        # sourceLcsLocal ist die Placement der Quell-LCS OHNE die (noch zu berechnende) neue
        # Import-Placement - da source_lcs im Quelldokument selbst liegt (nicht gespiegelt durch
        # den Import-Link), ist ihre .Placement bereits genau das: die Placement relativ zum
        # Ursprung des Quelldokuments, unbeeinflusst von import_link.Placement.
        source_local = App.Placement(source_lcs.Placement)
        target_global = App.Placement(target_lcs.Placement)
        new_placement = target_global.multiply(source_local.inverse())

        if not import_link.Placement.isSame(new_placement, 1e-7):
            import_link.Placement = new_placement

    def onDocumentRestored(self, obj):
        self._add_properties(obj)
        obj.Proxy = self

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


if _GUI_AVAILABLE:
    class _InterfaceLCSPickObserver:
        """Gui.Selection-Beobachter fuer das Aufgabenfenster: nimmt den naechsten Klick im
        Baum/3D-Fenster (in JEDEM offenen Dokument - die Quell-LCS liegt typischerweise in einem
        anderen Dokument als die Ziel-LCS) als Quell- oder Ziel-LCS entgegen, waehrend
        Panel._picking gesetzt ist. Nutzt weakref wie _ReplacementSelectionObserver in
        PartExchangeWindow.py, damit ein verwaistes Panel den Observer nicht dauerhaft haengen
        laesst."""

        def __init__(self, panel):
            self._panel_ref = weakref.ref(panel)

        def _panel(self):
            panel = self._panel_ref()
            if panel is None:
                try:
                    Gui.Selection.removeObserver(self)
                except Exception:
                    pass
            return panel

        def addSelection(self, doc_name, obj_name, sub_name, x=0, y=0, z=0):
            panel = self._panel()
            if panel is None or panel._picking is None:
                return
            doc = App.getDocument(doc_name)
            obj = doc.getObject(obj_name) if doc is not None else None
            if obj is None:
                return
            panel._on_pick(obj)

        def removeSelection(self, doc_name, obj_name, sub_name):
            pass

        def clearSelection(self, doc_name):
            pass

        def setSelection(self, doc_name):
            pass


    class InterfacePlacementTaskPanel:
        """Aufgabenfenster (Gui.Control-Task-Panel) zum Anlegen/Bearbeiten eines
        InterfacePlacement-Features - Quell-/Ziel-LCS werden per Knopf + Anklicken im
        Baum/3D-Fenster gewaehlt, keine Vorab-Selektion noetig."""

        def __init__(self, obj):
            self.obj = obj
            self._snapshot = {
                'SourceLCS': obj.SourceLCS,
                'TargetLCS': obj.TargetLCS,
                'Active': obj.Active,
            }
            self._picking = None  # 'source' | 'target' | None
            self._observer = _InterfaceLCSPickObserver(self)
            Gui.Selection.addObserver(self._observer)

            self.form = QtWidgets.QWidget()
            self.form.setWindowTitle("FCProject: Interface bearbeiten")
            layout = QtWidgets.QVBoxLayout(self.form)

            target_name = obj.ImportComponent.Label if obj.ImportComponent else "-"
            layout.addWidget(QtWidgets.QLabel(f"Import-Komponente: {target_name}"))

            layout.addWidget(QtWidgets.QLabel("Quell-LCS (Andock-Stelle am importierten Teil):"))
            self.source_edit, self.source_button = self._add_pick_row(layout, 'source')

            layout.addWidget(QtWidgets.QLabel("Ziel-LCS (Gegenstelle in der Baugruppe):"))
            self.target_edit, self.target_button = self._add_pick_row(layout, 'target')

            self.status_label = QtWidgets.QLabel("")
            self.status_label.setStyleSheet("color: #888;")
            layout.addWidget(self.status_label)

            self._refresh_labels()

        def _add_pick_row(self, layout, which):
            row = QtWidgets.QHBoxLayout()
            edit = QtWidgets.QLineEdit()
            edit.setReadOnly(True)
            row.addWidget(edit)
            button = QtWidgets.QPushButton("Waehlen...")
            button.clicked.connect(lambda: self._start_picking(which))
            row.addWidget(button)
            layout.addLayout(row)
            return edit, button

        def _refresh_labels(self):
            self.source_edit.setText(self.obj.SourceLCS.Label if self.obj.SourceLCS else "-")
            self.target_edit.setText(self.obj.TargetLCS.Label if self.obj.TargetLCS else "-")

        def _start_picking(self, which):
            self._picking = which
            Gui.Selection.clearSelection()
            hint = "Quell-LCS" if which == 'source' else "Ziel-LCS"
            self.status_label.setText(f"Bitte jetzt die {hint} im Baum oder 3D-Fenster anklicken...")

        def _on_pick(self, picked_obj):
            if picked_obj.TypeId != LCS_TYPE:
                self.status_label.setText(
                    f"'{picked_obj.Label}' ist kein Local Coordinate System - bitte erneut waehlen."
                )
                return
            if self._picking == 'source':
                self.obj.SourceLCS = picked_obj
            else:
                self.obj.TargetLCS = picked_obj
            self._picking = None
            self.status_label.setText("")
            self._refresh_labels()
            self.obj.Document.recompute()

        def accept(self):
            Gui.Selection.removeObserver(self._observer)
            self.obj.Document.recompute()
            Gui.ActiveDocument.resetEdit()
            return True

        def reject(self):
            Gui.Selection.removeObserver(self._observer)
            self.obj.SourceLCS = self._snapshot['SourceLCS']
            self.obj.TargetLCS = self._snapshot['TargetLCS']
            self.obj.Active = self._snapshot['Active']
            self.obj.Document.recompute()
            Gui.ActiveDocument.resetEdit()
            return True

        def getStandardButtons(self):
            return int(QtWidgets.QDialogButtonBox.Ok.value) | int(QtWidgets.QDialogButtonBox.Cancel.value)


    class ViewProviderInterfacePlacement:
        def __init__(self, vobj):
            vobj.Proxy = self

        def attach(self, vobj):
            self.Object = vobj.Object

        def getIcon(self):
            return os.path.join(ICON_DIR, 'interface_position.svg')

        def doubleClicked(self, vobj):
            Gui.ActiveDocument.setEdit(vobj.Object.Name)
            return True

        def setEdit(self, vobj, mode=0):
            Gui.Control.showDialog(InterfacePlacementTaskPanel(vobj.Object))
            return True

        def unsetEdit(self, vobj, mode=0):
            Gui.Control.closeDialog()
            return True

        def __getstate__(self):
            return None

        def __setstate__(self, state):
            return None


def find_active_assembly():
    try:
        import UtilsAssembly
        return UtilsAssembly.activeAssembly()
    except Exception as exc:
        App.Console.PrintWarning(f"FCProject: Aktive Baugruppe konnte nicht ermittelt werden: {exc}\n")
        return None


def ensure_interfaces_group(active_doc):
    """Findet/erstellt die "Interfaces"-Gruppe als Kind der aktiven Baugruppe (analog zur
    "Joints"-Gruppe von FreeCADs eigenem Assembly-Modul) - oder im Dokument-Root, falls gerade
    keine Baugruppe im Bearbeiten-Modus ist."""
    active_assembly = find_active_assembly()
    container = active_assembly if (active_assembly is not None and active_assembly.Document is active_doc) else None
    children = container.Group if container is not None else [
        obj for obj in active_doc.Objects if obj.getParentGeoFeatureGroup() is None
    ]
    for obj in children:
        if obj.TypeId == "App::DocumentObjectGroup" and obj.Label == INTERFACES_GROUP_LABEL:
            return obj

    group = active_doc.addObject("App::DocumentObjectGroup", "Interfaces")
    group.Label = INTERFACES_GROUP_LABEL
    if container is not None:
        container.addObject(group)
    return group


def make_interface_placement(active_doc, import_link):
    """Erstellt ein neues, noch leeres InterfacePlacement-Feature fuer 'import_link' in der
    "Interfaces"-Gruppe - die eigentliche LCS-Auswahl passiert danach im Aufgabenfenster
    (InterfacePlacementTaskPanel), nicht mehr hier."""
    group = ensure_interfaces_group(active_doc)

    active_doc.openTransaction("FCProject Interface Placement")
    try:
        obj = active_doc.addObject("App::FeaturePython", "InterfacePlacement")
        obj.Label = f"Interface: {import_link.Label}"
        InterfacePlacementProxy(obj)
        obj.ImportComponent = import_link
        group.addObject(obj)

        if _GUI_AVAILABLE and obj.ViewObject:
            ViewProviderInterfacePlacement(obj.ViewObject)

        active_doc.recompute()
        active_doc.commitTransaction()
        return obj
    except Exception:
        active_doc.abortTransaction()
        raise


if _GUI_AVAILABLE:
    class CommandPositionByInterface:
        def GetResources(self):
            return {
                'Pixmap': os.path.join(ICON_DIR, 'interface_position.svg'),
                'MenuText': 'FCProject: Interface anlegen/bearbeiten',
                'ToolTip': (
                    'Erstellt (oder bearbeitet) ein InterfacePlacement-Feature in der '
                    '"Interfaces"-Gruppe: richtet eine Import-Komponente anhand zweier lokaler '
                    'Koordinatensysteme (LCS) aus, im Aufgabenfenster per Knopf + Anklicken '
                    'ausgewaehlt. Aktualisiert sich bei jeder Neuberechnung automatisch mit, '
                    'falls sich eine der beiden LCS verschiebt - keine laufende '
                    'Solver-Abhaengigkeit.\n\n'
                    'Import-Komponente ausgewaehlt: legt ein neues Interface dafuer an.\n'
                    'Bestehendes Interface ausgewaehlt: oeffnet es zum Bearbeiten.'
                )
            }

        def Activated(self):
            from ImportComponentCommand import is_import_component
            main_win = Gui.getMainWindow()
            sel = Gui.Selection.getSelection()

            if len(sel) != 1:
                QtWidgets.QMessageBox.warning(
                    main_win, "FCProject",
                    "Bitte entweder eine Import-Komponente auswaehlen (legt ein neues Interface "
                    "an) oder ein bestehendes Interface-Objekt (zum Bearbeiten)."
                )
                return

            selected = sel[0]

            if is_interface_placement(selected):
                Gui.ActiveDocument.setEdit(selected.Name)
                return

            if not is_import_component(selected):
                QtWidgets.QMessageBox.warning(
                    main_win, "FCProject",
                    f"'{selected.Label}' ist weder eine Import-Komponente noch ein bestehendes "
                    "Interface-Objekt."
                )
                return

            active_doc = App.ActiveDocument
            if active_doc is None or selected.Document is not active_doc:
                QtWidgets.QMessageBox.warning(main_win, "FCProject", "Kein aktives Dokument geoeffnet.")
                return

            existing = find_interface_placement_for(selected)
            if existing is not None:
                Gui.ActiveDocument.setEdit(existing.Name)
                return

            try:
                feature = make_interface_placement(active_doc, selected)
            except Exception as exc:
                QtWidgets.QMessageBox.warning(main_win, "FCProject", str(exc))
                return

            Gui.Selection.clearSelection()
            Gui.ActiveDocument.setEdit(feature.Name)

        def IsActive(self):
            return App.ActiveDocument is not None

    Gui.addCommand('FCProject_PositionByInterface', CommandPositionByInterface())
