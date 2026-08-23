# FCProject: manuelles Placement-Panel - Ersatz fuer interaktives Ziehen bei fragilen
# Baugruppen (siehe patches/README.md, "GroundedJoint/RigidGroupJoint verschwindet bei
# verschachtelter flexibler Baugruppe" + der Live-Absturz beim Drag-Solve/runPreDrag()).
#
# Motivation (2026-08-23, Nutzer-Entscheidung): der interaktive Assembly-Solver (Ziehen mit
# der Maus, mbdAssembly->runPreDrag() im FreeCAD-Kern) ist der fragilste Teil des Solvers -
# genau dort kam gestern der "To be implemented"-Absturz her. Dieses Panel setzt stattdessen
# Placement direkt und numerisch, OHNE waehrend der Eingabe eine volle Dokument-Neuberechnung
# (und damit den Assembly-Solver) anzustossen - nur beim expliziten "OK" wird einmal
# `Document.recompute()` aufgerufen. Nebenbei ein praktischer Workaround fuer den oben
# genannten Bug: ein Teil, dessen automatische Erdung durch die Verschachtelung verloren geht,
# laesst sich hiermit einmalig manuell an die richtige Stelle setzen und sperren (dieselbe
# "Placement schreibgeschuetzt"-Technik, die JointObject.GroundedJoint.setReadOnly() normalerweise
# automatisch anwendet - hier nur direkt und ohne die kaputte Spiegelung ueber
# AssemblyLink-Grenzen hinweg).
import math
import os

import FreeCAD as App

try:
    import FreeCADGui as Gui
    from PySide6 import QtWidgets
    _GUI_AVAILABLE = True
except ImportError:
    _GUI_AVAILABLE = False

ICON_DIR = os.path.join(os.path.dirname(__file__), 'resources', 'icons')


def _find_local_mirror(doc, target_obj):
    """Findet die im Dokument 'doc' lokal lebende Mirror-Kopie von target_obj - vergleicht ueber
    getLinkedObject(True) (die letztendlich aufgeloeste Quelle), nicht ueber Objekt-Identitaet,
    damit es unabhaengig von der Verschachtelungstiefe funktioniert (siehe
    [[project_fcproject_selection_raw_source_vs_mirror_link]]: FreeCADs 3D-/Baum-Auswahl kann
    bei per App::Link eingebundenen Teilen innerhalb einer Baugruppe manchmal das ROHE Objekt
    aus dem verlinkten Quelldokument liefern statt das Mirror-Objekt, das tatsaechlich in der
    Baugruppe sitzt - Placement am rohen Objekt zu setzen bewegt dann etwas anderes als das
    sichtbar ausgewaehlte Teil). Dieselbe Technik wie AssemblyLink::mapToLocalComponent() im
    C++-Kern (siehe patches/freecad-assembly-grounded-joint-nested-flex.patch). FreeCADs
    Assembly-Workbench legt fuer jedes Teil auf JEDER Verschachtelungsebene einen eigenen,
    flachen App::Link an (empirisch bestaetigt) - ein einfacher Durchlauf ueber ALLE Objekte
    des Zieldokuments reicht daher aus, ohne rekursiv durch verschachtelte AssemblyLinks
    absteigen zu muessen."""
    if target_obj.Document is doc:
        return target_obj

    # FCPROJECT-FIX (2026-08-23): target_obj selbst ist manchmal KEIN Link-Ziel, z.B. wenn die
    # Baumauswahl ein internes PartDesign-Objekt liefert (z.B. "BaseFeature" tief in einem Body -
    # live beobachtet: "'BaseFeature' ist kein Link auf eine externe Quelldatei"). Kein App::Link
    # zeigt jemals DIREKT auf ein BaseFeature - Links zeigen auf den umschliessenden Body/Part.
    # Deshalb erst ueber getParentGeoFeatureGroup() (FreeCADs eigener Mechanismus fuer "wo bin
    # ich strukturell drin", siehe auch AssemblyPatternCreator._get_sub_name_for_child()) so
    # lange nach oben laufen, bis ein Objekt gefunden wird, das SELBST divergierend aufloest
    # (also tatsaechlich Ziel eines Links sein kann) - typischerweise der Body oder ein Part-
    # Container ein bis zwei Ebenen hoeher.
    walker = target_obj
    visited = set()
    target_root = None
    while walker is not None and id(walker) not in visited:
        visited.add(id(walker))
        try:
            root = walker.getLinkedObject(True)
        except Exception:
            root = None
        if root is not None and root is not walker:
            target_root = root
            break
        try:
            walker = walker.getParentGeoFeatureGroup()
        except Exception:
            walker = None

    if target_root is None:
        return None  # weder target_obj noch einer seiner Container ist Ziel eines Links

    for candidate in doc.Objects:
        if candidate is target_obj or not candidate.isDerivedFrom("App::Link"):
            continue
        try:
            candidate_root = candidate.getLinkedObject(True)
        except Exception:
            continue
        if candidate_root is target_root:
            return candidate
    return None


def _set_placement_readonly(obj, value):
    """Sperrt/entsperrt die Placement-(und bei App::Link zusaetzlich LinkPlacement-)Eigenschaft
    eines Objekts - dieselbe Technik wie JointObject.GroundedJoint.setReadOnly() in FreeCADs
    eigenem Assembly-Modul, hier direkt genutzt statt ueber einen (bei verschachtelten
    flexiblen Baugruppen aktuell kaputten) GroundedJoint."""
    tag = "ReadOnly" if value else "-ReadOnly"
    prop_list = obj.PropertiesList
    if "Placement" in prop_list:
        obj.setPropertyStatus("Placement", tag)
    if "LinkPlacement" in prop_list:
        obj.setPropertyStatus("LinkPlacement", tag)


def _is_placement_readonly(obj):
    try:
        return "ReadOnly" in obj.getPropertyStatus("Placement")
    except Exception:
        # Aeltere/andere FreeCAD-Versionen exponieren den Status evtl. anders - im Zweifel
        # "nicht gesperrt" annehmen, damit reject() wenigstens den Placement-Wert korrekt
        # zuruecksetzt (auch wenn der Sperr-Status dann u.U. nicht exakt wiederhergestellt wird).
        return False


if _GUI_AVAILABLE:
    class ManualPlacementTaskPanel:
        """Aufgabenfenster zum manuellen, numerischen Setzen eines Placements - bewusst OHNE
        Live-Neuberechnung waehrend der Eingabe (siehe Moduldocstring). Die 3D-Ansicht wird bei
        jeder Aenderung trotzdem sofort aktualisiert (reine Anzeige, kein Solve)."""

        def __init__(self, obj):
            self.obj = obj
            plc = obj.Placement
            axis, angle = plc.Rotation.Axis, plc.Rotation.Angle
            self._snapshot_placement = App.Placement(plc)
            self._snapshot_readonly = _is_placement_readonly(obj)

            self.form = QtWidgets.QWidget()
            self.form.setWindowTitle(f"FCProject: Placement setzen - {obj.Label}")
            layout = QtWidgets.QVBoxLayout(self.form)

            layout.addWidget(QtWidgets.QLabel("Position (mm):"))
            pos_layout = QtWidgets.QHBoxLayout()
            self.pos_x = self._make_spinbox(plc.Base.x)
            self.pos_y = self._make_spinbox(plc.Base.y)
            self.pos_z = self._make_spinbox(plc.Base.z)
            for label, box in (("X", self.pos_x), ("Y", self.pos_y), ("Z", self.pos_z)):
                pos_layout.addWidget(QtWidgets.QLabel(label))
                pos_layout.addWidget(box)
            layout.addLayout(pos_layout)

            layout.addWidget(QtWidgets.QLabel("Rotationsachse:"))
            axis_layout = QtWidgets.QHBoxLayout()
            self.axis_x = self._make_spinbox(axis.x, decimals=4)
            self.axis_y = self._make_spinbox(axis.y, decimals=4)
            self.axis_z = self._make_spinbox(axis.z, decimals=4)
            for label, box in (("X", self.axis_x), ("Y", self.axis_y), ("Z", self.axis_z)):
                axis_layout.addWidget(QtWidgets.QLabel(label))
                axis_layout.addWidget(box)
            layout.addLayout(axis_layout)

            layout.addWidget(QtWidgets.QLabel("Winkel um diese Achse (°):"))
            self.angle_spinbox = QtWidgets.QDoubleSpinBox()
            self.angle_spinbox.setDecimals(3)
            self.angle_spinbox.setMinimum(-3600.0)
            self.angle_spinbox.setMaximum(3600.0)
            self.angle_spinbox.setValue(angle)
            self.angle_spinbox.valueChanged.connect(self._apply_live)
            layout.addWidget(self.angle_spinbox)

            reset_button = QtWidgets.QPushButton("Aus aktuellem Placement übernehmen")
            reset_button.clicked.connect(self._reset_from_current)
            layout.addWidget(reset_button)

            self.lock_checkbox = QtWidgets.QCheckBox(
                "Placement danach sperren (schreibgeschützt - wie eine manuelle Erdung)"
            )
            self.lock_checkbox.setChecked(self._snapshot_readonly)
            layout.addWidget(self.lock_checkbox)

            note = QtWidgets.QLabel(
                "Hinweis: waehrend der Eingabe wird nur die 3D-Ansicht aktualisiert, NICHT das "
                "gesamte Dokument neu berechnet (kein Assembly-Solve). Erst 'OK' loest eine "
                "einmalige Neuberechnung aus."
            )
            note.setWordWrap(True)
            layout.addWidget(note)

            for box in (self.pos_x, self.pos_y, self.pos_z, self.axis_x, self.axis_y, self.axis_z):
                box.valueChanged.connect(self._apply_live)

        def _make_spinbox(self, value, decimals=3):
            box = QtWidgets.QDoubleSpinBox()
            box.setDecimals(decimals)
            box.setMinimum(-1000000.0)
            box.setMaximum(1000000.0)
            box.setValue(value)
            return box

        def _reset_from_current(self):
            plc = self.obj.Placement
            axis, angle = plc.Rotation.Axis, plc.Rotation.Angle
            for box, value in (
                (self.pos_x, plc.Base.x), (self.pos_y, plc.Base.y), (self.pos_z, plc.Base.z),
                (self.axis_x, axis.x), (self.axis_y, axis.y), (self.axis_z, axis.z),
            ):
                box.blockSignals(True)
                box.setValue(value)
                box.blockSignals(False)
            self.angle_spinbox.blockSignals(True)
            self.angle_spinbox.setValue(angle)
            self.angle_spinbox.blockSignals(False)
            self._apply_live()

        def _build_placement(self):
            axis = App.Vector(self.axis_x.value(), self.axis_y.value(), self.axis_z.value())
            if axis.Length < 1e-9:
                axis = App.Vector(0, 0, 1)
            base = App.Vector(self.pos_x.value(), self.pos_y.value(), self.pos_z.value())
            rotation = App.Rotation(axis, self.angle_spinbox.value())
            return App.Placement(base, rotation)

        def _apply_live(self, *_args):
            # Bewusst KEIN Document.recompute() hier - siehe Moduldocstring. Placement direkt
            # setzen ist eine reine Eigenschaftszuweisung, kein Solve; Gui.updateGui() sorgt nur
            # dafuer, dass die 3D-Ansicht das sofort zeigt.
            _set_placement_readonly(self.obj, False)
            self.obj.Placement = self._build_placement()
            Gui.updateGui()

        def accept(self):
            _set_placement_readonly(self.obj, False)
            placement = self._build_placement()
            self.obj.Placement = placement
            if self.lock_checkbox.isChecked():
                # Echtes, sichtbares Interface-Objekt statt nur der rohen Sperr-Eigenschaft
                # (siehe InterfaceFeature.py) - setzt die Placement zusaetzlich nach jedem
                # Recompute aktiv durch, nicht nur einmalig.
                import InterfaceFeature
                InterfaceFeature.make_interface(
                    self.obj.Document, self.obj, placement,
                    note="Manuell gesetzt ueber FCProject_ManualPlacement"
                )
            self.obj.Document.recompute()
            Gui.Control.closeDialog()
            return True

        def reject(self):
            _set_placement_readonly(self.obj, False)
            self.obj.Placement = self._snapshot_placement
            _set_placement_readonly(self.obj, self._snapshot_readonly)
            Gui.updateGui()
            Gui.Control.closeDialog()
            return True

        def getStandardButtons(self):
            return int(QtWidgets.QDialogButtonBox.Ok.value) | int(QtWidgets.QDialogButtonBox.Cancel.value)


    class ManualPlacementCommand:
        """Befehl: oeffnet das manuelle Placement-Panel fuer das aktuell ausgewaehlte Objekt."""

        def GetResources(self):
            return {
                'Pixmap': os.path.join(ICON_DIR, 'manual_placement.svg'),
                'MenuText': 'FCProject: Placement manuell setzen',
                'ToolTip': (
                    'Setzt Position/Rotation eines Teils numerisch, ohne waehrend der Eingabe '
                    'den Assembly-Solver auszuloesen (Ersatz fuer interaktives Ziehen bei '
                    'fragilen/verschachtelten Baugruppen). Optional danach sperren '
                    '(schreibgeschuetztes Placement, wie eine manuelle Erdung).'
                )
            }

        def Activated(self):
            main_win = Gui.getMainWindow()
            sel = Gui.Selection.getSelection()
            if len(sel) != 1:
                QtWidgets.QMessageBox.warning(
                    main_win, "FCProject",
                    "Bitte genau ein Teil auswaehlen."
                )
                return
            obj = sel[0]
            active_doc = App.ActiveDocument
            if active_doc is not None:
                mirror = _find_local_mirror(active_doc, obj)
                if mirror is not None and mirror is not obj:
                    App.Console.PrintMessage(
                        f"FCProject: Auswahl '{obj.Label}' gehoert zum Quelldokument von "
                        f"Mirror-Objekt '{mirror.Label}' in '{active_doc.Name}' - verwende "
                        "dieses (hat die tatsaechliche, zusammengebaute Placement).\n"
                    )
                    obj = mirror
            if not hasattr(obj, "Placement"):
                QtWidgets.QMessageBox.warning(
                    main_win, "FCProject",
                    f"'{obj.Label}' hat keine Placement-Eigenschaft."
                )
                return

            if Gui.Control.activeDialog():
                Gui.Control.closeDialog()

            Gui.Control.showDialog(ManualPlacementTaskPanel(obj))

        def IsActive(self):
            return App.ActiveDocument is not None

    Gui.addCommand('FCProject_ManualPlacement', ManualPlacementCommand())
