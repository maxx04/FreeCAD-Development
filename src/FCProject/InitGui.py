# In deiner InitGui.py
import os
import sys
import FreeCAD as App
import FreeCADGui

# Der sichere FreeCAD-Weg: Wir holen den Pfad direkt aus dem Mod-Verzeichnis
# Da die Workbench im Ordner 'FCProject' liegt, fragen wir FreeCAD nach der Benutzer-Mod-Route
user_mod_dir = os.path.join(App.getUserAppDataDir(), "Mod", "FCProject")

# Falls du es global installiert hättest (Sicherheitshalber als Fallback)
if not os.path.exists(user_mod_dir):
    user_mod_dir = os.path.join(App.getHomePath(), "Mod", "FCProject")

# Jetzt injizieren wir den verifizierten Pfad in das Python-System
if user_mod_dir not in sys.path:
    sys.path.append(user_mod_dir)

class FCProjectWorkbench(FreeCADGui.Workbench):
    Icon = FreeCADGui.getIcon("freecad")
    MenuText = "FCProject"

    def Initialize(self):
        # Nun findet er die Dateien zu 100%, da der Pfad im System registriert ist
        import Commands
        import ProjectManager
        
        self.appendToolbar("FCProject Tools", ["FCProject_ProjectManager", "FCProject_CreatePart"])

    def GetClassName(self):
        return "Gui::PythonWorkbench"

FreeCADGui.addWorkbench(FCProjectWorkbench())
