# Macro Version: 1.4.1 - FCProject: Eigenständiges ProjectManager Modul
import os
import json
import FreeCAD as App
import FreeCADGui as Gui

# Modul-Import mit Stummschaltung für VS Code (Pylance)
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

    def Activated(self):
        doc = App.ActiveDocument
        if not doc:
            QtWidgets.QMessageBox.warning(None, "FCProject", "Bitte erstelle oder öffne zuerst ein FreeCAD-Dokument!")
            return

        # 1. Aktuelles Verzeichnis der FreeCAD-Datei ermitteln
        if not doc.FileName:
            QtWidgets.QMessageBox.information(None, "FCProject", "Das Dokument ist noch nicht gespeichert. Bitte wähle einen Speicherort für dein Projekt.")
            save_path, _ = QtWidgets.QFileDialog.getSaveFileName(None, "Projekt保存 unter...", "", "FreeCAD Dateien (*.FCStd)")
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
                project_name = data.get("ProjectName", "Unbekannt")
                QtWidgets.QMessageBox.information(None, "FCProject", f"Projekt gefunden!\n\nProjektname: {project_name}\nDatei: {json_path}")
            except Exception as e:
                App.Console.PrintError(f"Fehler beim Lesen der JSON: {str(e)}\n")
        else:
            # 3. Wenn keine Datei da ist -> Erstellen und Name abfragen
            project_name, ok = QtWidgets.QInputDialog.getText(None, "FCProject: Neu", "Keine Projektdatei gefunden.\nBitte gib den Namen für das neue Projekt ein:")
            if ok and project_name:
                project_data = {
                    "ProjectName": project_name,
                    "CreatedBy": os.getlogin(),
                    "FreeCADVersion": "1.1",
                    "Halbzeuge": {},
                    "BOM_Settings": {
                        "GroupBy": "ArticleID",
                        "DetailParts": True
                    }
                }
                
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
