# Macro Version: 2.8.0 - FCProject: Automatische Erstellung der Stamm-CAD-Datei
import os
import json
from datetime import datetime
import FreeCAD as App
import FreeCADGui as Gui
from PySide6 import QtWidgets

class ProjectManagerCommand:
    SCRIPT_VERSION = "1.0"

    def GetResources(self):
        return {
            'Pixmap': 'freecad', 
            'MenuText': 'FCProject: Projekt initialisieren',
            'ToolTip': 'Erstellt PDM-Umgebung inklusive der leeren Stamm-CAD-Datei'
        }

    def get_default_project_data(self, project_name):
        """ZENTRALE STEUERUNG: Konfiguration für Eigen-, Kaufteile und Profile."""
        iso_date = datetime.now().strftime("%Y-%m-%d")
        return {
            "Configuration": {
                "Version": self.SCRIPT_VERSION,
                "CreatedBy": os.getlogin(),
                "CreationDate": iso_date
            },
            "ProjectMetadata": {
                "ProjectName": project_name,
                "FreeCADVersion": "1.1"
            },
            "Entities": {
                "P": {"Label": "P - Einzelteil (Part)", "FreeCADType": "PartDesign::Body", "Prefix": "BODY", "Properties": {"Bezeichnung": {"Type": "App::PropertyString", "Category": "FCProject_PDM", "Default": "Latte"}}},
                "A": {"Label": "A - Baugruppe (Assembly)", "FreeCADType": "Assembly::AssemblyObject", "Prefix": "ASM", "Properties": {"Bezeichnung": {"Type": "App::PropertyString", "Category": "FCProject_PDM", "Default": "Unterbaugruppe"}}},
                "R": {"Label": "R - Halbzeug (Profile/Rohmaterial)", "FreeCADType": "PartDesign::Body", "Prefix": "RAW", "Properties": {"Length": {"Type": "App::PropertyLength", "Category": "FCProject_PDM", "Default": 500.0}, "ProfilTyp": {"Type": "App::PropertyString", "Category": "FCProject_PDM", "Default": "60x40"}}},
                "G": {"Label": "G - Geometrie (Skelett/Referenz)", "FreeCADType": "App::Part", "Prefix": "SKEL", "Properties": {}},
                "B": {"Label": "B - Kaufteil (Purchased Component)", "FreeCADType": "App::Part", "Prefix": "PUR", "Properties": {"Bezeichnung": {"Type": "App::PropertyString", "Category": "FCProject_PDM", "Default": "Kaufteil"}, "Hersteller": {"Type": "App::PropertyString", "Category": "FCProject_PDM", "Default": "TraceParts"}, "Bestellnummer": {"Type": "App::PropertyString", "Category": "FCProject_PDM", "Default": "000-000"}}}
            }
        }

    def Activated(self):
        main_window = Gui.getMainWindow()
        
        # 1. Arbeitsverzeichnis abfragen
        base_dir = QtWidgets.QFileDialog.getExistingDirectory(main_window, "Wähle deinen zentralen CAD-Arbeitsordner")
        if not base_dir: return

        # 2. Ressourcen-Verzeichnisse absichern
        common_dir = os.path.join(base_dir, "_Common_Resources")
        os.makedirs(os.path.join(common_dir, "Profiles"), exist_ok=True)
        os.makedirs(os.path.join(common_dir, "PurchasedComponents"), exist_ok=True)

        # 3. Projektnamen abfragen (z.B. U10)
        project_name, ok = QtWidgets.QInputDialog.getText(main_window, "FCProject: Neues Projekt", "Bitte gib den Projektnamen ein (z.B. U10):")
        if not ok or not project_name: return

        # 4. Projektordner anlegen (z.B. PROJ_U10)
        project_folder_name = f"PROJ_{project_name}"
        target_project_dir = os.path.join(base_dir, project_folder_name)
        os.makedirs(target_project_dir, exist_ok=True)

        # 5. Pfade für JSON und die Stamm-CAD-Datei bestimmen
        json_path = os.path.join(target_project_dir, f"{project_folder_name}.json")
        fc_file_path = os.path.join(target_project_dir, f"{project_name}.FCStd") # <-- NEU: Zieldatei z.B. U10.FCStd

        # System-Arbeitsverzeichnis sofort umschalten, damit alle Folgemodule hier ansetzen
        os.chdir(target_project_dir)

        if os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if data.get("Configuration", {}).get("Version") != self.SCRIPT_VERSION:
                QtWidgets.QMessageBox.critical(main_window, "Versions-Konflikt", "Inkompatible JSON-Version!")
                return
        else:
            # Neue JSON wegschreiben
            project_data = self.get_default_project_data(project_name)
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(project_data, f, indent=4, ensure_ascii=False)

        # 6. NEU: Leere Stamm-CAD-Datei anlegen, falls sie noch nicht existiert
        if not os.path.exists(fc_file_path):
            new_doc = App.newDocument(project_name)
            new_doc.saveAs(fc_file_path)
            new_doc.recompute()
            Gui.setActiveDocument(new_doc.Name)
            App.Console.PrintMessage(f"FCProject: Stammdatei '{project_name}.FCStd' erfolgreich generiert.\n")
        else:
            # Falls die Datei schon existiert, öffnen wir sie einfach!
            App.openDocument(fc_file_path)
            Gui.setActiveDocument(project_name)

        QtWidgets.QMessageBox.information(
            main_window, "FCProject", 
            f"Projekt '{project_name}' erfolgreich initialisiert und geöffnet!\n\nArbeitsverzeichnis ist aktiv gesetzt."
        )

    def IsActive(self):
        return True

Gui.addCommand('FCProject_ProjectManager', ProjectManagerCommand())
