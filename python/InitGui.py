#FCProject: InitGui Hintergrund-Scanner mit Versions-Guard
#
# FCPROJECT-PATCH (2026-10-10, Nutzerwunsch "Assembly hat jetzt eigene Arrays"): das eigene
# Pattern-Feature (AssemblyPatternCommand.py/AssemblyPatternCreator.py/PatternFeatures.py)
# entfernt - FreeCADs Assembly-Werkbench unterstuetzt seit Upstream-Commit 67103b19c9
# ("Assembly: support generated arrays and suppressed link elements", 9. Sep.) natives
# Part::LinkArray direkt in Baugruppen (Joints, Element-Sichtbarkeit etc. alles integriert),
# der urspruengliche Grund fuer ein eigenes Pattern-Feature (fehlende Array-Unterstuetzung in
# der Assembly-Werkbench) ist damit entfallen. Normales FreeCAD-"Array erstellen"
# (Part_LinkArrays) innerhalb der Baugruppe benutzen statt dieser eigenen Werkzeuge.
import os
import FreeCAD as App
import FreeCADGui


class FCProjectWorkbench(FreeCADGui.Workbench):
    MenuText = "FCProject"

    # Muss exakt mit der Version des ProjectManagers übereinstimmen!
    SUPPORTED_VERSION = "1.1"

    def __init__(self):
        # Icon-Pfad bewusst erst HIER (Instanz statt Klassen-Attribut) bestimmen: FreeCAD
        # fuehrt InitGui.py per exec() aus, nicht per import - ein ganz oben in dieser Datei
        # gebundener Name (z.B. "from _addon_paths import REPO_ROOT") landet dadurch nur im
        # lokalen exec()-Rahmen und ist fuer einen verschachtelten Klassenkoerper UNSICHTBAR
        # (NameError) - "os"/"App"/"FreeCADGui" funktionierten oben nur zufaellig, weil diese
        # Namen schon vorher in FreeCADGuiInit.pys eigenem globalen Namensraum existierten,
        # den der exec()-Aufruf mitbenutzt. Ein frischer, LOKALER Import innerhalb einer
        # Funktion ist dagegen unabhaengig von diesem Scope-Problem, weil er ueber eine
        # normale Funktions-Variable (nicht ueber den exec()-Rahmen) aufgeloest wird - siehe
        # _addon_paths.py fuer den Grund, warum __file__ hier direkt nicht funktioniert.
        import _addon_paths
        import IconUtils
        # resources/ liegt (wie bei allen anderen Command-Modulen dieses Addons) INNERHALB von
        # python/, nicht an der Repo-Wurzel - deshalb PYTHON_DIR statt REPO_ROOT.
        icon_dir = os.path.join(_addon_paths.PYTHON_DIR, 'resources', 'icons')
        self.Icon = IconUtils.icon_path(icon_dir, 'fcproject.svg')

    def Initialize(self):
        # Diese Imports laufen schon GANZ AM PROGRAMMSTART (siehe Block nach addWorkbench()
        # unten, _early_import_feature_modules() dort) - der erneute LOKALE Import hier ist
        # nur ein billiges No-Op (Python cached bereits importierte Module ueber sys.modules),
        # falls der Start-Import aus irgendeinem Grund nicht geklappt haben sollte. Bewusst
        # NICHT als Aufruf einer gemeinsamen Hilfsfunktion per blossem Namen: FreeCAD fuehrt
        # InitGui.py per exec() aus, nicht per import - ein nur am Dateianfang gebundener
        # Funktionsname ist aus einer spaeter (bei Werkbench-Aktivierung) aufgerufenen
        # Methode heraus NICHT sicher auflösbar (siehe gleiches Problem+Erklaerung in
        # __init__() oben zu icon_dir - live beobachtet: "name '_import_feature_modules' is
        # not defined" beim Werkbench-Wechsel). Jeder Aufrufort bekommt deshalb seine EIGENEN,
        # lokalen Imports.
        import ProjectManager as ProjectManager
        import Commands as Commands
        import BOMCommand as BOMCommand
        import PartExchangeCommand as PartExchangeCommand
        import SelectableRepairCommand as SelectableRepairCommand
        import SectionSketchFeature as SectionSketchFeature
        import ImportComponentCommand as ImportComponentCommand
        import InterfacePlacementFeature as InterfacePlacementFeature
        import PartPlayerCommand as PartPlayerCommand
        import ResetPlacementCommand as ResetPlacementCommand
        import RenamePartCommand as RenamePartCommand
        import DocObserver
        DocObserver.register()

        self.appendToolbar("FCProject Tools", [
            "FCProject_ProjectManager",
            "FCProject_CreatePart",
            "FCProject_ExportBOM",
            "FCProject_PartExchange",
            "FCProject_RepairSelectable",
            "FCProject_CreateSectionSketch",
            "FCProject_ImportComponent",
            "FCProject_PositionByInterface",
            "FCProject_PartPlayer",
            "FCProject_ResetPlacement",
            "FCProject_RenamePart"
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
                if panel._attached_doc is not None:  # None: Dokument samt Dialog schon weg
                    FreeCADGui.Control.closeDialog(panel._attached_doc)
        except Exception as e:
            App.Console.PrintWarning(f"FCProject: Panel konnte beim Werkbench-Wechsel nicht geschlossen werden: {str(e)}\n")

    def GetClassName(self):
        return "Gui::PythonWorkbench"

FreeCADGui.addWorkbench(FCProjectWorkbench())

# FCPROJECT-FIX (2026-11-08, siehe docs/CONSTRAINTS.md fuer den vollen Hintergrund): diese
# Imports laufen bewusst HIER, ganz am Programmstart (InitGui.py wird fuer JEDES installierte
# Addon schon beim Start per exec() ausgefuehrt, siehe Log-Zeile "Initializing .../FreeCAD-
# Development/python... done") - nicht erst in FCProjectWorkbench.Initialize(), das FreeCAD
# erst beim ERSTEN Aktivieren dieser Werkbench aufruft. Grund: wird ein Dokument mit eigenen
# FCProject-Objekten (z.B. SectionSketch) geladen, BEVOR die Werkbench je aktiviert wurde,
# versucht FreeCADs PropertyPythonObject::Restore das jeweilige Modul (z.B.
# "SectionSketchFeature") selbst zu importieren - und blockiert das seit einer brandneuen
# Kernaenderung (Sicherheitscheck gegen das Nachladen beliebigen Codes aus einer FCStd-Datei
# heraus), weil unser Sandbox-Profil FCProject nur per SYMLINK einbindet und der dadurch
# aufgeloeste reale Dateipfad nicht auf FreeCADs eigener Positivliste (FreeCAD.__ModDirs__)
# steht. Die einzige Regel in PropertyPythonObject::isAllowedModule(), die davon UNABHAENGIG
# ist: ein bereits in sys.modules geladenes Modul gilt immer als erlaubt - deshalb reicht es,
# alles schon hier zu importieren, bevor irgendein Dokument geladen wird.
import ProjectManager as ProjectManager
import Commands as Commands
import BOMCommand as BOMCommand
import PartExchangeCommand as PartExchangeCommand
import SelectableRepairCommand as SelectableRepairCommand
import SectionSketchFeature as SectionSketchFeature
import ImportComponentCommand as ImportComponentCommand
import InterfacePlacementFeature as InterfacePlacementFeature
import PartPlayerCommand as PartPlayerCommand
import ResetPlacementCommand as ResetPlacementCommand
import RenamePartCommand as RenamePartCommand
import DocObserver
DocObserver.register()
