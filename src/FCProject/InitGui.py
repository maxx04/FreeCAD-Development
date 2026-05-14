# In deiner InitGui.py
import os
import sys
import FreeCAD as App
import FreeCADGui

# Pfad-Injektion (Damit FreeCAD deine ProjectManager.py findet)
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
        """AUTOMATISCHER CHECK: Inline-Import von json verhindert den NameError."""
        # INLINE-IMPORT: Schützt das Modul vor der Bereinigung durch den Core!
        import json
        
        doc = App.ActiveDocument
        main_win = FreeCADGui.getMainWindow()
        
        if not doc or not doc.FileName:
            App.Console.PrintWarning("FCProject: Kein gespeichertes Dokument offen. Bitte manuell initialisieren.\n")
            if main_win: main_win.statusBar().showMessage("FCProject: Kein aktives Projekt.", 4000)
            return

        project_dir = os.path.dirname(doc.FileName)
        json_path = os.path.join(project_dir, "FCProject.json")

        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                metadata = data.get("ProjectMetadata", {})
                proj_name = metadata.get("ProjectName", "Unbekannt")
                
                if main_win:
                    main_win.statusBar().showMessage(f"FCProject: Kontext '{proj_name}' aktiv.", 5000)
                App.Console.PrintMessage(f"FCProject: Projekt '{proj_name}' erfolgreich im Hintergrund verifiziert.\n")
            except Exception as e:
                App.Console.PrintError(f"FCProject: Fehler beim automatischen JSON-Scan: {str(e)}\n")
        else:
            App.Console.PrintWarning("FCProject: Keine Projektdatei gefunden. Nutze den Button 'Projekt initialisieren'.\n")
            if main_win: 
                main_win.statusBar().showMessage("FCProject: Uninitialisiertes Verzeichnis (Nutze Button 1).", 5000)

    def GetClassName(self):
        return "Gui::PythonWorkbench"

FreeCADGui.addWorkbench(FCProjectWorkbench())
