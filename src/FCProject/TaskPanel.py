# Macro Version: 1.6.0 - FCProject: Reines GUI TaskPanel mit PDM-Anbindung
import os
import json
import FreeCAD as App
from PySide6 import QtWidgets
# Wir importieren die reine Logik-Klasse
from PartCreator import PartCreator

class FCProjectTaskPanel:
    """TaskPanel für die Benutzeroberfläche des PDM-Creators."""
    def __init__(self):
        self.form = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.form)
        
        layout.addWidget(QtWidgets.QLabel("<h3>FCProject: PDM-Creator</h3>"))
        
        # Typ-Auswahl
        layout.addWidget(QtWidgets.QLabel("<b>Komponenten-Typ:</b>"))
        self.type_combo = QtWidgets.QComboBox()
        self.type_combo.addItem("P - Einzelteil (Part)", "P")
        self.type_combo.addItem("A - Baugruppe (Assembly)", "A")
        self.type_combo.addItem("R - Halbzeug (Profile/Rohmaterial)", "R")
        self.type_combo.addItem("G - Geometrie (Skelett/Referenz)", "G")
        layout.addWidget(self.type_combo)
        
        # AUTOMATISCHE NUMMER HOLEN
        proj_name, proj_dir = self._get_project_context()
        suggested_num = "0001"
        if proj_name and proj_dir:
            from PartCreator import PartCreator
            checker = PartCreator(proj_name, proj_dir)
            suggested_num = checker.get_next_available_number()

        # Teilnummer-Feld mit dem automatischen Vorschlag befüllen
        layout.addWidget(QtWidgets.QLabel("<b>Teilnummer:</b>"))
        self.number_input = QtWidgets.QLineEdit(suggested_num)
        layout.addWidget(self.number_input)
        
        # Button zum Auslösen
        self.create_btn = QtWidgets.QPushButton("Neue Komponente & Datei erstellen")
        self.create_btn.clicked.connect(self.on_create_clicked)
        layout.addWidget(self.create_btn)
        
        layout.addStretch()


    def _get_project_context(self):
        """Sucht die JSON und extrahiert Pfad und Projektname."""
        active_doc = App.ActiveDocument
        if active_doc and active_doc.FileName:
            current_dir = os.path.dirname(active_doc.FileName)
            json_path = os.path.join(current_dir, "FCProject.json")
            if os.path.exists(json_path):
                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    proj_name = data.get("ProjectMetadata", {}).get("ProjectName", "PROJ")
                    return proj_name, current_dir
                except:
                    pass
        return None, None

    def on_create_clicked(self):
        """Reine GUI-Event-Methode: Sammelt Daten und ruft den Creator auf."""
        proj_name, proj_dir = self._get_project_context()
        if not proj_dir:
            QtWidgets.QMessageBox.warning(None, "FCProject", "Kein initialisiertes Projekt gefunden!\nBitte zuerst Projekt initialisieren.")
            return

        comp_type = self.type_combo.currentData()
        comp_num = self.number_input.text().strip()

        # DIE ÜBERGABE AN DIE LOGIK-KLASSE:
        try:
            creator = PartCreator(proj_name, proj_dir)
            generated_name = creator.create_pdm_document(comp_type, comp_num)
            QtWidgets.QMessageBox.information(None, "FCProject", f"Komponente {generated_name} erfolgreich erstellt!")
        except FileExistsError as fe:
            QtWidgets.QMessageBox.warning(None, "FCProject", str(fe))
        except Exception as e:
            QtWidgets.QMessageBox.critical(None, "FCProject", f"Unerwarteter Fehler: {str(e)}")

    def getStandardButtons(self):
        return QtWidgets.QDialogButtonBox.Close
