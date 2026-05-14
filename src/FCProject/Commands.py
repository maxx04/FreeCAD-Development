# Macro Version: 1.6.0 - FCProject: Command-Schnittstelle für Toolbar

import FreeCAD as App
import FreeCADGui as Gui
from TaskPanel import FCProjectTaskPanel

class PartCreatorCommand:
    """Befehl zum Öffnen des FCProject TaskPanels aus der Toolbar."""
    def GetResources(self):
        return {
            'Pixmap': 'freecad', 
            'MenuText': 'FCProject: PDM-Teil erstellen',
            'ToolTip': 'Erstellt eine neue, strukturierte Bauteil-Datei'
        }

    def Activated(self):
        # Altes Gui.Control.showDialog(panel) ERSETZEN durch:
        from TaskPanel import FCProjectTaskPanel
        self.dialog = FCProjectTaskPanel()
        self.dialog.show() # Öffnet das Fenster schwebend im Vordergrund


def IsActive(self):
        # Extrem schneller Einzeiler ohne Imports – blockiert den Debugger nicht
        return App.ActiveDocument is not None

Gui.addCommand('FCProject_CreatePart', PartCreatorCommand())
