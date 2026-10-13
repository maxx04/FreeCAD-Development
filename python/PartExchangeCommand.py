# FCProject: PartExchangeCommand - Original-Teil im Baum durch ein Ersatzteil ersetzen
import os
import FreeCAD as App
import FreeCADGui as Gui
from PySide6 import QtWidgets, QtCore

from PartExchangeAnalyzer import is_valid_exchange_candidate, find_assembly
from PartExchangeWindow import PartExchangeWindow


def _get_selected_original():
    selection = Gui.Selection.getSelection()
    if len(selection) != 1:
        return None
    candidate = selection[0]
    return candidate if is_valid_exchange_candidate(candidate) else None


class PartExchangeSelectDialog(QtWidgets.QDialog):
    """Dialog zur Auswahl des Ersatzteils (aus dem aktiven Dokument oder einer anderen .FCStd-Datei)."""

    def __init__(self, original_obj, parent=None):
        super().__init__(parent or Gui.getMainWindow())
        self.original_obj = original_obj
        self.replacement_obj = None

        self.setWindowTitle("FCProject: Ersatzteil wählen")
        self.resize(440, 340)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel(
            f"<b>Original:</b> {original_obj.Label}  [{original_obj.Document.Name}]"
        ))

        layout.addWidget(QtWidgets.QLabel("<b>Ersatzteil:</b>"))
        # FCPROJECT-FIX (2026-10-13, Nutzer-Report "Liste geoeffnet, Maus geht nirgends mehr" -
        # live per gdb-Backtrace + python-xlib-Grab-Test bestaetigt, siehe
        # PartExchangeCommand.Activated()): urspruenglich eine QComboBox - deren Popup-Liste
        # erzeugt beim Oeffnen einen echten X11-Pointer-Grab (fuer "Klick ausserhalb schliesst
        # die Liste"). Auf diesem Mehrbildschirm-Setup (GNOME/Mutter) blieb dieser Grab beim
        # Schliessen des Popups global haengen (auch andere Anwendungen betroffen), bis der
        # FreeCAD-Prozess beendet wurde - ein bekanntes Qt/X11/Mutter-Mehrbildschirm-Problem,
        # nicht in unserem Code beeinflussbar. Fix: QListWidget statt QComboBox - eine normale,
        # immer sichtbare Liste ohne eigenes Popup-Fenster, braucht also auch keinen X11-Grab.
        self.candidate_combo = QtWidgets.QListWidget()
        layout.addWidget(self.candidate_combo)

        browse_row = QtWidgets.QHBoxLayout()
        self.browse_btn = QtWidgets.QPushButton("Datei wählen…")
        self.browse_btn.clicked.connect(self._on_browse_file)
        browse_row.addWidget(self.browse_btn)
        browse_row.addStretch()
        layout.addLayout(browse_row)

        layout.addStretch()

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()
        self.ok_btn = QtWidgets.QPushButton("Weiter")
        self.ok_btn.clicked.connect(self._on_confirm)
        self.cancel_btn = QtWidgets.QPushButton("Abbrechen")
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.ok_btn)
        btn_row.addWidget(self.cancel_btn)
        layout.addLayout(btn_row)

        self._populate_candidates(self.original_obj.Document)

    def _populate_candidates(self, doc):
        # WICHTIG (2026-08-30, Nutzer-Report): Label ist NICHT eindeutig - z.B. nach "Einfache
        # Kopie erstellen" tragen Original und Kopie dasselbe Label, aber unterschiedliche
        # .Name. Intern wird zur Adressierung bereits korrekt .Name verwendet (siehe
        # _on_confirm()), aber wenn die Anzeige nur das Label zeigt, sind zwei gleich
        # benannte Objekte in der Liste nicht unterscheidbar und man waehlt leicht das
        # falsche aus. Deshalb den internen Namen mit anzeigen, sobald er vom Label abweicht.
        # FCPROJECT-PATCH (2026-09-06, per Live-Absturz bestaetigt): das Assembly::AssemblyObject
        # eines Dokuments gilt laut is_valid_exchange_candidate() grundsaetzlich als gueltiger
        # Kandidat (fuer den Fall, dass eine per App::Link eingebundene SUB-Baugruppe ersetzt
        # werden soll) - waehlt man aber versehentlich die Assembly-Wurzel DESSELBEN Dokuments
        # `doc` selbst aus, erzeugt _ensure_local_replacement() einen App::Link INNERHALB dieser
        # Baugruppe, der auf die Baugruppe SELBST zurueckzeigt ("...Link" mit demselben Namen
        # wie das Dokument im Absturz-Log) - ein direkter Zyklus im Coin3D-Szenengraph, der
        # FreeCAD zuverlaessig abstuerzen laesst. Deshalb hier ausschliessen.
        own_assembly = find_assembly(doc)
        self.candidate_combo.clear()
        for obj in doc.Objects:
            if obj is self.original_obj or obj is own_assembly:
                continue
            if is_valid_exchange_candidate(obj):
                display = obj.Label if obj.Label == obj.Name else f"{obj.Label} ({obj.Name})"
                item = QtWidgets.QListWidgetItem(f"{display}  [{doc.Name}]")
                item.setData(QtCore.Qt.UserRole, (doc.Name, obj.Name))
                self.candidate_combo.addItem(item)
        if self.candidate_combo.count() > 0:
            self.candidate_combo.setCurrentRow(0)

    def _on_browse_file(self):
        start_dir = os.getcwd()
        if self.original_obj.Document.FileName:
            start_dir = os.path.dirname(self.original_obj.Document.FileName)

        selected_file, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Ersatzteil-Datei wählen…", start_dir, "FreeCAD Dokumente (*.FCStd)",
            options=QtWidgets.QFileDialog.DontUseNativeDialog
        )
        if not selected_file:
            return

        already_open_name = None
        for doc_name, doc in App.listDocuments().items():
            if getattr(doc, 'FileName', None) == selected_file:
                already_open_name = doc_name
                break

        try:
            doc = App.getDocument(already_open_name) if already_open_name else App.openDocument(selected_file)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "FCProject", f"Datei konnte nicht geöffnet werden:\n{str(e)}")
            return

        self._populate_candidates(doc)
        if self.candidate_combo.count() == 0:
            QtWidgets.QMessageBox.warning(
                self, "FCProject", "In dieser Datei wurde kein gültiges Ersatzteil gefunden."
            )

    def _on_confirm(self):
        item = self.candidate_combo.currentItem()
        if item is None:
            QtWidgets.QMessageBox.warning(self, "FCProject", "Bitte ein Ersatzteil wählen.")
            return

        doc_name, obj_name = item.data(QtCore.Qt.UserRole)
        doc = App.getDocument(doc_name)
        candidate = doc.getObject(obj_name) if doc else None

        if candidate is None:
            QtWidgets.QMessageBox.warning(self, "FCProject", "Das gewählte Ersatzteil ist nicht mehr gültig.")
            return
        if candidate is self.original_obj:
            QtWidgets.QMessageBox.warning(self, "FCProject", "Original und Ersatzteil dürfen nicht identisch sein.")
            return

        self.replacement_obj = candidate
        self.accept()


class PartExchangeCommand:
    """Befehl zum Ersetzen eines Original-Teils/Assembly durch ein Ersatzteil."""

    def GetResources(self):
        import IconUtils
        icon_dir = os.path.join(os.path.dirname(__file__), 'resources', 'icons')
        return {
            'Pixmap': IconUtils.icon_path(icon_dir, 'part_exchange.svg'),
            'MenuText': 'FCProject: Part/Assembly ersetzen',
            'ToolTip': 'Ersetzt ein ausgewähltes Teil/Assembly durch ein Ersatzteil und ordnet dabei Joints/Referenzen neu zu'
        }

    def Activated(self):
        # FCPROJECT-FIX (2026-10-13, Nutzer-Report "Liste geoeffnet, Maus geht ueberhaupt
        # nirgends mehr - auch nicht in anderen Programmen"): live per gdb-Backtrace UND einem
        # X11-Grab-Test bestaetigt (python-xlib: root.grab_pointer() lieferte "AlreadyGrabbed",
        # ein von aussen gesendetes ungrab_pointer() half NICHT dauerhaft - erst das Beenden
        # des FreeCAD-Prozesses gab den Grab wieder frei). Root Cause: dieser komplette Ablauf
        # (inkl. QDialog.exec() fuer "Ersatzteil waehlen") lief bisher SYNCHRON noch INNERHALB
        # von Qts eigenem mouseReleaseEvent()-Handler des geklickten Toolbar-Buttons
        # (Backtrace: QToolButton::mouseReleaseEvent -> QAction::activate -> Gui::Command::
        # invoke -> PythonCommand::activated -> hierher). Qt haelt waehrend der Klick-Erkennung
        # eines Buttons kurz einen eigenen internen Maus-Grab - startet ein modaler Dialog
        # SYNCHRON mitten in dieser Verarbeitung (statt erst einen Event-Loop-Durchlauf
        # spaeter), kann Qt diesen Grab nicht mehr sauber zuruecknehmen, sobald der Dialog
        # irgendwann schliesst - der Grab blieb dadurch GLOBAL (auch fuer andere Anwendungen)
        # haengen. Fix: die komplette Logik per QTimer.singleShot(0, ...) auf den naechsten
        # Event-Loop-Durchlauf verschieben, NACHDEM der Button-Klick selbst fertig verarbeitet
        # (und sein interner Grab wieder freigegeben) ist.
        QtCore.QTimer.singleShot(0, self._do_activate)

    def _do_activate(self):
        main_win = Gui.getMainWindow()
        self._close_active_task_dialog()
        original_obj = _get_selected_original()

        if not original_obj:
            QtWidgets.QMessageBox.warning(
                main_win,
                "FCProject: Part/Assembly ersetzen",
                "Bitte wähle zuerst genau ein gültiges Original-Teil im Baum aus."
            )
            return

        select_dialog = PartExchangeSelectDialog(original_obj, main_win)
        if select_dialog.exec() != QtWidgets.QDialog.Accepted:
            return

        replacement_obj = select_dialog.replacement_obj
        if not replacement_obj:
            return

        self.window = PartExchangeWindow(original_obj, replacement_obj)
        self.window.show()

    @staticmethod
    def _close_active_task_dialog():
        """Schließt ein offenes Taskpanel (z.B. Assembly-Joint-Erstellen/-Bearbeiten), bevor das
        Split-View-Fenster mehrere Dokumente aktiviert - sonst bleibt dessen globaler
        Selection-Gate aktiv und prüft Klicks im Ersatzteil-Dokument gegen das Original-Assembly
        (FreeCADError: "Cannot check an object from another document with this group")."""
        try:
            if Gui.Control.activeDialog() is not None:
                Gui.Control.closeDialog()
        except Exception as e:
            App.Console.PrintWarning(f"FCProject PartExchange: Taskpanel konnte nicht geschlossen werden: {str(e)}\n")

    def IsActive(self):
        if not App.ActiveDocument:
            return False
        return _get_selected_original() is not None


Gui.addCommand('FCProject_PartExchange', PartExchangeCommand())
