# Macro Version: 2.9.7 - FCProject: Dynamischer JSON-Scanner für PROJ_*.json
import os
import sys
import FreeCAD as App
import FreeCADGui

# Pfad-Injektion für Module
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
        """AUTOMATISCHER CHECK: Scannt dynamisch nach der PROJ_[Name].json."""
        import json
        doc = App.ActiveDocument
        main_win = FreeCADGui.getMainWindow()
        
        if not doc or not doc.FileName:
            if main_win: main_win.statusBar().showMessage("FCProject: Kein aktives Projekt geöffnet.", 4000)
            return

        # Pfade extrahieren
        project_dir = os.path.dirname(doc.FileName)
        folder_name = os.path.basename(project_dir)

        # DYNAMISCHER NAMENS-CHECK VIA MATCH-CASE
        match folder_name.startswith("PROJ_"):
            case True:
                # Baut den Namen exakt nach deinem Schema: PROJ_U17.json
                json_filename = f"{folder_name}.json"
                json_path = os.path.join(project_dir, json_filename)
            case _:
                # Fallback für unstrukturierte Verzeichnisse
                json_path = os.path.join(project_dir, "FCProject.json")

        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                metadata = data.get("ProjectMetadata", {})
                proj_name = metadata.get("ProjectName", "Unbekannt")
                
                if main_win:
                    main_win.statusBar().showMessage(f"FCProject: Kontext '{proj_name}' aktiv.", 5000)
                App.Console.PrintMessage(f"FCProject: Projekt '{proj_name}' erfolgreich über {json_filename} verifiziert.\n")
            except Exception as e:
                App.Console.PrintError(f"FCProject: Fehler beim JSON-Scan ({json_filename}): {str(e)}\n")
        else:
            if main_win: 
                main_win.statusBar().showMessage("FCProject: Uninitialisiertes Verzeichnis (Nutze Button 1).", 5000)

    def GetClassName(self):
        return "Gui::PythonWorkbench"

FreeCADGui.addWorkbench(FCProjectWorkbench())
