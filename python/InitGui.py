#FCProject: InitGui Hintergrund-Scanner mit Versions-Guard
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
    Icon = os.path.join(App.getUserAppDataDir(), 'Mod', 'FCProject', 'resources', 'icons', 'fcproject.svg') #FreeCADGui.getIcon("freecad")
    MenuText = "FCProject"

    # Muss exakt mit der Version des ProjectManagers übereinstimmen!
    SUPPORTED_VERSION = "1.1"

    def Initialize(self):
        import ProjectManager as ProjectManager
        import Commands as Commands
        import BOMCommand as BOMCommand
        import AssemblyPatternCommand as AssemblyPatternCommand
        import PatternFeatures as PatternFeatures
        import PartExchangeCommand as PartExchangeCommand
        import SelectableRepairCommand as SelectableRepairCommand
        import SectionSketchFeature as SectionSketchFeature
        import ManualPlacementCommand as ManualPlacementCommand
        import InterfaceFeature as InterfaceFeature
        import RestoreRigidGroupCommand as RestoreRigidGroupCommand
        import DocObserver
        DocObserver.register()

        self.appendToolbar("FCProject Tools", [
            "FCProject_ProjectManager",
            "FCProject_CreatePart",
            "FCProject_ExportBOM",
            "FCProject_PatternGroup",
            "FCProject_PartExchange",
            "FCProject_RepairSelectable",
            "FCProject_CreateSectionSketch",
            "FCProject_ManualPlacement",
            "FCProject_RestoreRigidGroup",
            "FCProject_CreateInterface"
        ])


    def Activated(self):
        """AUTOMATISCHER CHECK: Validiert den Projektkontext und schützt vor Versionskonflikten."""
        import json
        doc = App.ActiveDocument
        main_win = FreeCADGui.getMainWindow()
        
        if not doc or not doc.FileName:
            if main_win: main_win.statusBar().showMessage("FCProject: Kein aktives Projekt geöffnet.", 4000)
            return

        # Pfade extrahieren
        project_dir = os.path.dirname(doc.FileName)
        folder_name = os.path.basename(project_dir)

        # Dynamische JSON-Pfadermittlung via match-case
        match folder_name.startswith("PROJ_"):
            case True:
                json_filename = f"{folder_name}.json"
                json_path = os.path.join(project_dir, json_filename)
            case _:
                json_filename = "FCProject.json"
                json_path = os.path.join(project_dir, json_filename)

        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 1. KORREKTUR: Version direkt beim Workbench-Wechsel validieren!
                config_version = data.get("Configuration", {}).get("Version", "0.0")
                
                if config_version != self.SUPPORTED_VERSION:
                    # Rote Warnung in die Konsole knallen
                    App.Console.PrintError(
                        f"\n[FCProject CRITICAL] ABBRUCH: Die geladene '{json_filename}' nutzt das Schema V{config_version}.\n"
                        f"Diese Workbench unterstützt aktuell nur die Version V{self.SUPPORTED_VERSION}!\n"
                        f"Bitte initialisiere das Projekt neu oder aktualisiere dein Addon.\n\n"
                    )
                    if main_win: 
                        main_win.statusBar().showMessage(f"FCProject ERROR: Inkompatible Projekt-Version V{config_version}!", 6000)
                    return # Ablauf hart abbrechen!
                
                # 2. Wenn die Version passt, laden wir die Metadaten
                metadata = data.get("ProjectMetadata", {})
                proj_name = metadata.get("ProjectName", "Unbekannt")
                
                if main_win:
                    main_win.statusBar().showMessage(f"FCProject: Kontext '{proj_name}' aktiv.", 5000)
                App.Console.PrintMessage(f"FCProject: Projekt '{proj_name}' erfolgreich über {json_filename} verifiziert (V{config_version}).\n")
                
            except Exception as e:
                App.Console.PrintError(f"FCProject: Fehler beim JSON-Scan ({json_filename}): {str(e)}\n")
        else:
            if main_win: 
                main_win.statusBar().showMessage("FCProject: Uninitialisiertes Verzeichnis (Nutze Button 1).", 5000)

    def Deactivated(self):
        """Wird von FreeCAD aufgerufen, sobald zu einer ANDEREN Werkbench gewechselt wird
        (verifiziert in Application::activateWorkbench im FreeCAD-C++-Kern: die 'Deactivated'-
        Methode der zuvor aktiven Werkbench wird ohne Argumente aufgerufen, bevor die neue aktiv
        wird). Schließt unser eigenes PDM-Creator-Panel automatisch, falls es gerade offen ist -
        außerhalb dieser Werkbench ist es nicht mehr sinnvoll nutzbar und blieb bisher dauerhaft
        im Aufgabenbereich hängen, auch nach dem Wechsel in eine andere Werkbench.

        WICHTIG: FreeCADGui.Control.closeDialog() OHNE Dokument-Argument schließt in Wirklichkeit
        nur den Dialog des GERADE aktiven Dokuments (FreeCAD-Kern: ControlSingleton::docOrDefault()
        fällt darauf zurück) - nicht zwingend das Dokument, an dem UNSER Panel tatsächlich hängt
        (siehe FCProjectTaskPanel._attached_doc in TaskPanel.py). Nach dem Erstellen eines
        Kaufteils/einer Baugruppe (PurchasedPartCreator.create()/EntityCreator - läuft über mehrere
        App.newDocument()/App.setActiveDocument()-Aufrufe) zeigt das aktive Dokument oft schon auf
        ein anderes Dokument als das, an dem das Panel angehängt ist - ein Aufruf ohne Dokument
        würde dann lautlos ins Leere laufen und das Panel bliebe sichtbar im Aufgabenbereich hängen,
        z.B. beim Wechsel in die Assembly-Werkbench für "Teil hinzufügen". Deshalb explizit
        panel._attached_doc mitgeben statt uns auf das aktive Dokument zu verlassen."""
        try:
            import TaskPanel
            panel = TaskPanel._active_panel
            if panel is not None:
                # Gui.Control kennt in Python kein reject()/accept() (nur showDialog/
                # activeDialog/activeTaskDialog/closeDialog) - eigenes Aufräumen deshalb selbst
                # anstoßen, dann erst das Panel tatsächlich entfernen.
                panel.reject()
                FreeCADGui.Control.closeDialog(panel._attached_doc)
        except Exception as e:
            App.Console.PrintWarning(f"FCProject: Panel konnte beim Werkbench-Wechsel nicht geschlossen werden: {str(e)}\n")

    def GetClassName(self):
        return "Gui::PythonWorkbench"

FreeCADGui.addWorkbench(FCProjectWorkbench())
