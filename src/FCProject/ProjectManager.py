
import os
import json
import FreeCAD as App
import FreeCADGui as Gui

try:
    from PySide6 import QtWidgets, QtCore
except ImportError:
    try:
        from PySide2 import QtWidgets, QtCore
    except ImportError:
        from PySide import QtWidgets, QtCore  # type: ignore

class ProjectManagerCommand:
    """Befehl zum Initialisieren und Verwalten des FCProject-Datenfiles."""

    def GetResources(self):
        return {
            'Pixmap': 'freecad', 
            'MenuText': 'FCProject: Projekt initialisieren',
            'ToolTip': 'Sucht oder erstellt die FCProject.json im aktuellen Verzeichnis'
        }

    def get_default_project_data(self, project_name):
        """DEFINITIION DER DATENSTRUKTUR: Hier werden alle Standard-Projektvariablen zentral gepflegt."""
        return {
            "ProjectMetadata": {
                "ProjectName": project_name,
                "CreatedBy": os.getlogin(),
                "FreeCADVersion": "1.1",
                "CreationDate": QtCore.QDate.currentDate().toString(QtCore.Qt.ISODate)
            },
            "Components": {
                "Parts": {},       # Hier landen deine Standard-Bauteile
                "Halbzeuge": {}    # Hier landen deine Profile/Halbzeuge mit Längen
            },
            "BOM_Settings": {
                "GroupBy": "ArticleID",
                "DetailParts": True,
                "IncludeGroups": False
            }
        }

    def Activated(self):
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

        # 2. Prüfen, ob die JSON existiert
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # Tiefere Verschachtelung auslesen, da wir die Struktur geändert haben
                metadata = data.get("ProjectMetadata", {})
                project_name = metadata.get("ProjectName", "Unbekannt")
                QtWidgets.QMessageBox.information(None, "FCProject", f"Projekt gefunden!\n\nProjektname: {project_name}\nDatei: {json_path}")
            except Exception as e:
                App.Console.PrintError(f"Fehler beim Lesen der JSON: {str(e)}\n")
        else:
            # 3. Wenn keine Datei da ist -> Abfragen und über Klassenstruktur generieren
            project_name, ok = QtWidgets.QInputDialog.getText(None, "FCProject: Neu", "Keine Projektdatei gefunden.\nBitte gib den Namen für das neue Projekt ein:")
            if ok and project_name:
                # HIER NUTZEN WIR DIE INTERNE STRUKTUR DER KLASSE:
                project_data = self.get_default_project_data(project_name)
                
                try:
                    with open(json_path, 'w', encoding='utf-8') as f:
                        json.dump(project_data, f, indent=4, ensure_ascii=False)
                    App.Console.PrintMessage(f"FCProject: 'FCProject.json' erfolgreich in {project_dir} erstellt.\n")
                    QtWidgets.QMessageBox.information(None, "FCProject", f"Projekt '{project_name}' erfolgreich initialisiert!")
                except Exception as e:
                    App.Console.PrintError(f"Schreibfehler: {str(e)}\n")

    def IsActive(self):
        return not App.ActiveDocument is None

# Command bei FreeCAD registrieren
Gui.addCommand('FCProject_ProjectManager', ProjectManagerCommand())
