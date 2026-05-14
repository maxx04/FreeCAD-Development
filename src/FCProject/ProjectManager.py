# Macro Version: 1.10.1 - FCProject: Robustes Datums-Handling ohne Qt-Abhängigkeit
import os
import json
from datetime import datetime  # <-- NEU: Unabhängig von PySide/QtCore!
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
    """Befehl zum Initialisieren und Verwalten des FCProject-Datenfiles."""

    def GetResources(self):
        return {
            'Pixmap': 'freecad', 
            'MenuText': 'FCProject: Projekt initialisieren',
            'ToolTip': 'Sucht oder erstellt die FCProject.json im aktuellen Verzeichnis'
        }

    def get_default_project_data(self, project_name):
        """ZENTRALE STEUERUNG: Konfiguration für UI und PartCreator."""
        # Das aktuelle Datum im ISO-Format (YYYY-MM-DD) über pfeilschnelles Standard-Python
        iso_date = datetime.now().strftime("%Y-%m-%d")
        
        return {
            "Configuration": {
                "Version": "1.0",
                "CreatedBy": os.getlogin(),
                "CreationDate": iso_date  # <-- KORREKTUR: Keine QtCore-Abhängigkeit mehr!
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
                        "Gewicht": {"Type": "App::PropertyFloat", "Category": "FCProject_PDM", "Default": 0.0}
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
        main_window = Gui.getMainWindow()
        doc = App.ActiveDocument
        if not doc:
            QtWidgets.QMessageBox.warning(None, "FCProject", "Bitte erstelle oder öffne zuerst ein FreeCAD-Dokument!")
            return

        # 1. Aktuelles Verzeichnis ermitteln
        if not doc.FileName:
            QtWidgets.QMessageBox.information(None, "FCProject", "Das Dokument ist noch nicht gespeichert. Bitte wähle einen Speicherort für dein Projekt.")
            save_path, _ = QtWidgets.QFileDialog.getSaveFileName(None, "Projekt speichern unter...", "", "FreeCAD Dateien (*.FCStd)")
            if not save_path:
                return  # Abgebrochen
            doc.saveAs(save_path)
        
        project_dir = os.path.dirname(doc.FileName)
        json_path = os.path.join(project_dir, "FCProject.json")

# 2. Wenn das Projekt existiert (Korrektur von None zu main_window)
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                metadata = data.get("ProjectMetadata", {})
                project_name = metadata.get("ProjectName", "Unbekannt")
                
                # HIER: main_window statt None!
                QtWidgets.QMessageBox.information(main_window, "FCProject", f"Projekt gefunden!\n\nProjektname: {project_name}\nDatei: {json_path}")
            except Exception as e:
                App.Console.PrintError(f"Fehler: {str(e)}\n")
        else:
            # 3. Wenn das Projekt neu ist (Korrektur von None zu main_window)
            # HIER: main_window statt None!
            project_name, ok = QtWidgets.QInputDialog.getText(
            main_window, 
            "FCProject: Neu", 
            "Keine Projektdatei gefunden.\nBitte gib den Namen für das neue Projekt ein:"
                )
            if ok and project_name:
                # HIER NUTZEN WIR DIE INTERNE STRUKTUR DER KLASSE:
                project_data = self.get_default_project_data(project_name)
                
                try:
                    with open(json_path, 'w', encoding='utf-8') as f:
                        json.dump(project_data, f, indent=4, ensure_ascii=False)
                    App.Console.PrintMessage(f"FCProject: 'FCProject.json' erfolgreich in {project_dir} erstellt.\n")
                    QtWidgets.QMessageBox.information(main_window, "FCProject", f"Projekt '{project_name}' erfolgreich initialisiert!")
                except Exception as e:
                    App.Console.PrintError(f"Schreibfehler: {str(e)}\n")

    def IsActive(self):
        return not App.ActiveDocument is None

# Command bei FreeCAD registrieren
Gui.addCommand('FCProject_ProjectManager', ProjectManagerCommand())
