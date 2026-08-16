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

        Gui.Control.showDialog(self.dialog, self.dialog._attached_doc)

    @staticmethod
    def _close_active_task_dialog():
        """Schließt ein evtl. bereits offenes eigenes Task-Panel, bevor ein neues geöffnet wird -
        sonst weist Gui.Control.showDialog() den Aufruf mit einer Konsolen-Warnung lautlos ab
        ("already an active task dialog").

        Prüft dafür DIREKT TaskPanel._active_panel statt Gui.Control.activeDialog(): Letzteres
        bezieht sich ohne explizites Dokument-Argument immer auf das GERADE aktive Dokument (siehe
        [[project_fcproject_kaufteil_step_workflow]] bzw. Erklärung bei
        FCProjectTaskPanel._attached_doc in TaskPanel.py) - ist das aktive Dokument seit dem Öffnen
        unseres Panels gewechselt (z.B. durch die Kaufteil-/Baugruppen-Erstellung, die dabei über
        mehrere App.newDocument()-Aufrufe läuft), fände activeDialog() fälschlich KEINEN offenen
        Dialog, obwohl unser Panel tatsächlich noch (an einem anderen Dokument hängend) offen ist."""
        try:
            import TaskPanel
            panel = TaskPanel._active_panel
            if panel is not None:
                # Erst reject() selbst aufrufen (stoppt z.B. den STEP-Beobachtungs-Timer) - Gui.Control
                # kennt in Python kein reject(), closeDialog() allein würde das Aufräumen überspringen.
                panel.reject()
                Gui.Control.closeDialog(panel._attached_doc)
        except Exception as e:
            App.Console.PrintWarning(f"FCProject: Vorhandenes Task-Panel konnte nicht geschlossen werden: {str(e)}\n")

    def IsActive(self):
        return App.ActiveDocument is not None

Gui.addCommand('FCProject_CreatePart', PartCreatorCommand())
