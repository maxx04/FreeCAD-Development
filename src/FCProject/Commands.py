# Macro Version: 1.6.0 - FCProject: Command-Schnittstelle für Toolbar
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
        panel = FCProjectTaskPanel()
        Gui.Control.showDialog(panel)

    def IsActive(self):
        import FreeCAD as App
        return not App.ActiveDocument is None

Gui.addCommand('FCProject_CreatePart', PartCreatorCommand())
