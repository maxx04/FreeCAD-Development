# Macro Version: 1.11.1 - FCProject: ProjectManager mit automatischer JSON-Versionsprüfung
import os
import json
from datetime import datetime
import FreeCAD as App
import FreeCADGui as Gui

try:
    from PySide6 import QtWidgets
except ImportError:
    try:
        from PySide2 import QtWidgets
    except ImportError:
        from PySide import QtWidgets  # type: ignore

class ProjectManagerCommand:
    """Befehl zum Initialisieren und Verwalten des FCProject-Datenfiles mit Versionsschutz."""

    # SCRIPT_VERSION: Die Version, die dieses Python-Script maximal versteht
    SCRIPT_VERSION = "1.0"

    def GetResources(self):
        return {
            'Pixmap': 'freecad', 
            'MenuText': 'FCProject: Projekt initialisieren',
            'ToolTip': 'Sucht oder erstellt die FCProject.json im aktuellen Verzeichnis'
        }

    def get_default_project_data(self, project_name):
        """ZENTRALE STEUERUNG: Konfiguration für UI und PartCreator."""
        iso_date = datetime.now().strftime("%Y-%m-%d")
        
        return {
            "Configuration": {
                "Version": self.SCRIPT_VERSION, # Nutzt die zentral definierte Version
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
                        "Bezeichnung": {"Type": "App::PropertyString", "Category": "FCProject_PDM", "Default": "Standardteil"}
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
                }
            }

        }

    def Activated(self):
        doc = App.ActiveDocument
        if not doc:
            QtWidgets.QMessageBox.warning(None, "FCProject", "Bitte erstelle oder öffne zuerst ein FreeCAD-Dokument!")
            return

        main_window = Gui.getMainWindow()

        if not doc.FileName:
            QtWidgets.QMessageBox.information(main_window, "FCProject", "Das Dokument ist noch nicht gespeichert. Bitte wähle einen Speicherort für dein Projekt.")
            save_path, _ = QtWidgets.QFileDialog.getSaveFileName(main_window, "Projekt speichern unter...", "", "FreeCAD Dateien (*.FCStd)")
            if not save_path:
                return
            doc.saveAs(save_path)
        
        project_dir = os.path.dirname(doc.FileName)
        json_path = os.path.join(project_dir, "FCProject.json")

        # 2. Prüfen, ob die JSON existiert
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # VERSIONS-PRÜFUNG: Version aus der JSON auslesen
                config_section = data.get("Configuration", {})
                json_version = config_section.get("Version", "0.0")
                
                # Vergleich: Passt die Datei-Version zu unserem Python-Script?
                if json_version != self.SCRIPT_VERSION:
                    QtWidgets.QMessageBox.critical(
                        main_window, 
                        "FCProject: Versions-Konflikt!", 
                        f"WARNUNG: Die vorhandene Projektdatei nutzt Version {json_version}.\n"
                        f"Dieses Makro unterstützt jedoch nur Version {self.SCRIPT_VERSION}.\n\n"
                        "Bitte aktualisiere dein FCProject-Addon, um Datenverlust zu vermeiden!"
                    )
                    return # Ablauf abbrechen, um die Datei nicht zu beschädigen

                metadata = data.get("ProjectMetadata", {})
                project_name = metadata.get("ProjectName", "Unbekannt")
                QtWidgets.QMessageBox.information(main_window, "FCProject", f"Projekt erfolgreich verifiziert!\n\nProjektname: {project_name}\nKonfig-Version: {json_version}\nDatei: {json_path}")
                
            except Exception as e:
                App.Console.PrintError(f"Fehler beim Lesen der JSON: {str(e)}\n")
        else:
            # 3. Wenn keine Datei da ist -> Neu anlegen
            project_name, ok = QtWidgets.QInputDialog.getText(main_window, "FCProject: Neu", "Keine Projektdatei gefunden.\nBitte gib den Namen für das neue Projekt ein:")
            if ok and project_name:
                project_data = self.get_default_project_data(project_name)
                
                try:
                    with open(json_path, 'w', encoding='utf-8') as f:
                        json.dump(project_data, f, indent=4, ensure_ascii=False)
                    App.Console.PrintMessage(f"FCProject: 'FCProject.json' erfolgreich in {project_dir} erstellt.\n")
                    QtWidgets.QMessageBox.information(main_window, "FCProject", f"Projekt '{project_name}' (V{self.SCRIPT_VERSION}) erfolgreich initialisiert!")
                except Exception as e:
                    App.Console.PrintError(f"Schreibfehler: {str(e)}\n")

    def IsActive(self):
        return not App.ActiveDocument is None

Gui.addCommand('FCProject_ProjectManager', ProjectManagerCommand())
