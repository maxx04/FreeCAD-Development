# Macro Version: 1.0.3 - FCProject: ProjectManager mit Inline-JSON und fixer Versionsprüfung
import os
import json
from datetime import datetime
import FreeCAD as App
import FreeCADGui as Gui
from PySide6 import QtWidgets

class ProjectManagerCommand:
    # SCRIPT_VERSION: Die Version, die dieses Python-Script maximal versteht
    SCRIPT_VERSION = "1.0"

    def GetResources(self):
        return {
            'Pixmap': 'freecad', 
            'MenuText': 'FCProject: Projekt initialisieren',
            'ToolTip': 'Erstellt eine strukturierte PDM-Umgebung und setzt das Arbeitsverzeichnis'
        }

    def get_default_project_data(self, project_name):
        """ZENTRALE STEUERUNG (INLINE INCLUDE): Die Master-Vorlage für deine PROJ_.json."""
        iso_date = datetime.now().strftime("%Y-%m-%d")
        
        # Das Python-Dictionary ersetzt das externe JSON-Template vollständig
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
                "P": {
                    "Label": "P - Einzelteil (Part)", 
                    "FreeCADType": "PartDesign::Body", 
                    "Prefix": "BODY", 
                    "Properties": {
                        "Bezeichnung": {"Type": "App::PropertyString", "Category": "FCProject_PDM", "Default": "Latte"}
                    }
                },
                "A": {
                    "Label": "A - Baugruppe (Assembly)", 
                    "FreeCADType": "Assembly::AssemblyObject", 
                    "Prefix": "ASM", 
                    "Properties": {
                        "Bezeichnung": {"Type": "App::PropertyString", "Category": "FCProject_PDM", "Default": "Unterbaugruppe"}
                    }
                },
                "R": {
                    "Label": "R - Halbzeug (Profile/Rohmaterial)", 
                    "FreeCADType": "PartDesign::Body", 
                    "Prefix": "RAW", 
                    "Properties": {
                        "Length": {"Type": "App::PropertyLength", "Category": "FCProject_PDM", "Default": 500.0}, 
                        "ProfilTyp": {"Type": "App::PropertyString", "Category": "FCProject_PDM", "Default": "60x40"}
                    }
                },
                "G": {
                    "Label": "G - Geometrie (Skelett/Referenz)", 
                    "FreeCADType": "App::Part", 
                    "Prefix": "SKEL", 
                    "Properties": {}
                },
                "B": {
                    "Label": "B - Kaufteil (Purchased Component)", 
                    "FreeCADType": "App::Part", 
                    "Prefix": "PUR", 
                    "Properties": {
                        "Bezeichnung": {"Type": "App::PropertyString", "Category": "FCProject_PDM", "Default": "Kaufteil"},
                        "Hersteller": {"Type": "App::PropertyString", "Category": "FCProject_PDM", "Default": "TraceParts"},
                        "Bestellnummer": {"Type": "App::PropertyString", "Category": "FCProject_PDM", "Default": "000-000"}
                    }
                }
            }
        }

    def Activated(self):
        main_window = Gui.getMainWindow()
        
        # 1. PRE-FLIGHT CHECK: Prüfen, ob im aktuellen Verzeichnis bereits ein Projekt aktiv ist
        current_dir = os.getcwd()
        folder_name = os.path.basename(current_dir)
        
        if folder_name.startswith("PROJ_"):
            json_filename = f"{folder_name}.json"
            json_path = os.path.join(current_dir, json_filename)
            
            if os.path.exists(json_path):
                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    # KORREKTUR: Die Versionsprüfung greift jetzt auch beim Pre-Flight Check fehlerfrei!
                    config_version = data.get("Configuration", {}).get("Version", "0.0")
                    if config_version != self.SCRIPT_VERSION:
                        QtWidgets.QMessageBox.critical(
                            main_window, 
                            "FCProject: Versions-Konflikt!", 
                            f"WARNUNG: Die vorhandene Projektdatei nutzt Version {config_version}.\n"
                            f"Dieses Makro unterstützt jedoch nur Version {self.SCRIPT_VERSION}.\n\n"
                            "Der Vorgang wurde zum Schutz deiner Daten abgebrochen!"
                        )
                        return
                    
                    QtWidgets.QMessageBox.information(main_window, "FCProject", f"Projekt '{folder_name.replace('PROJ_', '')}' ist bereits aktiv geladen und verifiziert (V{config_version}).")
                    return
                except Exception as e:
                    App.Console.PrintError(f"FCProject: Fehler beim schnellen JSON-Check: {str(e)}\n")

        # --- AB HIER: Wenn KEIN aktives Projekt im aktuellen Verzeichnis gefunden wurde (Neuanlage) ---
        
        # 2. Arbeitsverzeichnis abfragen
        base_dir = QtWidgets.QFileDialog.getExistingDirectory(main_window, "Wähle deinen zentralen CAD-Arbeitsordner")
        if not base_dir: return

        # 3. Ressourcen-Verzeichnisse absichern
        common_dir = os.path.join(base_dir, "_Common_Resources")
        os.makedirs(os.path.join(common_dir, "Profiles"), exist_ok=True)
        os.makedirs(os.path.join(common_dir, "PurchasedComponents"), exist_ok=True)

        # 4. Projektnamen abfragen (z.B. U17)
        project_name, ok = QtWidgets.QInputDialog.getText(main_window, "FCProject: Neues Projekt", "Bitte gib den Projektnamen ein (z.B. U17):")
        if not ok or not project_name: return

        # 5. Projektordner anlegen (z.B. PROJ_U17)
        project_folder_name = f"PROJ_{project_name}"
        target_project_dir = os.path.join(base_dir, project_folder_name)
        os.makedirs(target_project_dir, exist_ok=True)

        # 6. Pfade für JSON und die Stamm-CAD-Datei bestimmen
        json_path = os.path.join(target_project_dir, f"{project_folder_name}.json")
        fc_file_path = os.path.join(target_project_dir, f"{project_name}.FCStd")

        # System-Arbeitsverzeichnis umschalten
        os.chdir(target_project_dir)

        # Doppelte Absicherung beim Schreiben
        if os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            config_version = data.get("Configuration", {}).get("Version", "0.0")
            if config_version != self.SCRIPT_VERSION:
                QtWidgets.QMessageBox.critical(main_window, "FCProject: Versions-Konflikt!", "Inkompatible JSON-Version beim Überschreiben blockiert!")
                return
        else:
            # Neue JSON über die Inline-Include-Methode generieren und wegschreiben
            project_data = self.get_default_project_data(project_name)
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(project_data, f, indent=4, ensure_ascii=False)

        # 7. Leere Stamm-CAD-Datei anlegen oder öffnen
        if not os.path.exists(fc_file_path):
            new_doc = App.newDocument(project_name)
            new_doc.saveAs(fc_file_path)
            new_doc.recompute()
            Gui.setActiveDocument(new_doc.Name)
        else:
            App.openDocument(fc_file_path)
            Gui.setActiveDocument(project_name)

        QtWidgets.QMessageBox.information(
            main_window, "FCProject", 
            f"Projekt '{project_name}' erfolgreich initialisiert und geöffnet!"
        )

    def IsActive(self):
        return True

Gui.addCommand('FCProject_ProjectManager', ProjectManagerCommand())
