# In deiner InitGui.py
import os
import sys
import FreeCAD as App
import FreeCADGui

user_mod_dir = os.path.join(App.getUserAppDataDir(), "Mod", "FCProject")
if not os.path.exists(user_mod_dir):
    user_mod_dir = os.path.join(App.getHomePath(), "Mod", "FCProject")

if user_mod_dir not in sys.path:
    sys.path.append(user_mod_dir)

class FCProjectWorkbench(FreeCADGui.Workbench):
    Icon = FreeCADGui.getIcon("freecad")
    MenuText = "FCProject"

    def Initialize(self):
        import ProjectManager
        import Commands  
        
        self.appendToolbar("FCProject Tools", ["FCProject_ProjectManager", "FCProject_CreatePart"])

    def Activated(self):
        """AUTOMATISCHER START: Wird ausgeführt, wenn der User zur Workbench wechselt."""
        try:
            # Wir importieren das Modul direkt
            import ProjectManager
            
            # Wir erstellen direkt eine Instanz der Befehlsklasse und starten sie.
            # Das umgeht den Fehler mit FreeCADGui.getCommand komplett.
            manager = ProjectManager.ProjectManagerCommand()
            manager.Activated()
            
        except Exception as e:
            import FreeCAD as App
            App.Console.PrintError(f"FCProject: Fehler bei Auto-Aktivierung: {str(e)}\n")


    def GetClassName(self):
        return "Gui::PythonWorkbench"

FreeCADGui.addWorkbench(FCProjectWorkbench())
