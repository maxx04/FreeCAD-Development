#  FCProject: Command-Schnittstelle für Toolbar

import FreeCAD as App
import FreeCADGui as Gui
from PySide6 import QtWidgets

class PartCreatorCommand:
    """Befehl zum Öffnen des FCProject TaskPanels aus der Toolbar."""
    def GetResources(self):
        import os
        icon_path = os.path.join(os.path.dirname(__file__), 'resources', 'icons', 'part_creator.svg')
        return {
            'Pixmap': icon_path,
            'MenuText': 'FCProject: PDM-Teil erstellen',
            'ToolTip': 'Erstellt eine neue, strukturierte Bauteil-Datei'
        }

    def Activated(self):
        # Läuft jetzt im Aufgabenbereich (Combo View) statt als freischwebendes Fenster -
        # Gui.Control.showDialog() hängt das Panel am aktuell aktiven Dokument auf, ohne
        # Dokument gibt es nichts zum Anhängen (stille Konsolen-Warnung, kein sichtbarer Fehler).
        if not App.ActiveDocument:
            QtWidgets.QMessageBox.warning(
                Gui.getMainWindow(), "FCProject",
                "Bitte öffne zuerst ein Dokument/Projekt (Button 1)."
            )
            return

        self._close_active_task_dialog()

        from TaskPanel import FCProjectTaskPanel
        self.dialog = FCProjectTaskPanel()
        if not self.dialog.valid:
            return  # Fehlermeldung (fehlende Projekt-Konfiguration) kam bereits aus dem Panel selbst

        Gui.Control.showDialog(self.dialog)

    @staticmethod
    def _close_active_task_dialog():
        """Schließt ein evtl. bereits offenes Task-Panel, bevor ein neues geöffnet wird - sonst
        weist Gui.Control.showDialog() den Aufruf mit einer Konsolen-Warnung lautlos ab
        ("already an active task dialog"). Gui.Control.activeDialog() liefert in Python (anders
        als der Name vermuten lässt) ein bool zurück, kein Objekt - siehe FreeCADGui._Control.pyi -
        deshalb direkt als Wahrheitswert prüfen statt gegen None."""
        try:
            if Gui.Control.activeDialog():
                # Falls es UNSER eigenes Panel ist: dessen reject() zuerst selbst aufrufen (stoppt
                # z.B. den STEP-Beobachtungs-Timer) - Gui.Control kennt in Python kein reject(),
                # closeDialog() allein würde das Aufräumen sonst überspringen.
                import TaskPanel
                if TaskPanel._active_panel is not None:
                    TaskPanel._active_panel.reject()
                Gui.Control.closeDialog()
        except Exception as e:
            App.Console.PrintWarning(f"FCProject: Vorhandenes Task-Panel konnte nicht geschlossen werden: {str(e)}\n")

    def IsActive(self):
        return App.ActiveDocument is not None

Gui.addCommand('FCProject_CreatePart', PartCreatorCommand())
