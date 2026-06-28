# FCProject: PartExchangeCommand - Original-Teil im Baum durch ein Ersatzteil ersetzen
import os
import FreeCAD as App
import FreeCADGui as Gui
from PySide6 import QtWidgets

from PartExchangeAnalyzer import is_valid_exchange_candidate
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
        self.resize(440, 180)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel(
            f"<b>Original:</b> {original_obj.Label}  [{original_obj.Document.Name}]"
        ))

        layout.addWidget(QtWidgets.QLabel("<b>Ersatzteil:</b>"))
        self.candidate_combo = QtWidgets.QComboBox()
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
        self.candidate_combo.clear()
        for obj in doc.Objects:
            if obj is self.original_obj:
                continue
            if is_valid_exchange_candidate(obj):
                self.candidate_combo.addItem(f"{obj.Label}  [{doc.Name}]", (doc.Name, obj.Name))

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
        idx = self.candidate_combo.currentIndex()
        if idx < 0:
            QtWidgets.QMessageBox.warning(self, "FCProject", "Bitte ein Ersatzteil wählen.")
            return

        doc_name, obj_name = self.candidate_combo.itemData(idx)
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
        icon_path = os.path.join(os.path.dirname(__file__), 'resources', 'icons', 'part_exchange.svg')
        return {
            'Pixmap': icon_path,
            'MenuText': 'FCProject: Part/Assembly ersetzen',
            'ToolTip': 'Ersetzt ein ausgewähltes Teil/Assembly durch ein Ersatzteil und ordnet dabei Joints/Referenzen neu zu'
        }

    def Activated(self):
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
