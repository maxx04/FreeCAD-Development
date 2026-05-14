# Macro Version: 1.10.0 - FCProject: Dynamische GUI aus JSON gesteuert
import os
import json
import FreeCAD as App
from PySide6 import QtWidgets, QtCore
from PartCreator import PartCreator

class FCProjectTaskPanel:
    """TaskPanel, das sich komplett dynamisch an die JSON-Struktur anpasst."""
    def __init__(self):
        self.form = QtWidgets.QWidget()
        self.main_layout = QtWidgets.QVBoxLayout(self.form)
        self.main_layout.addWidget(QtWidgets.QLabel("<h3>FCProject: PDM-Creator</h3>"))
        
        # 1. JSON Kontext holen
        self.proj_name, self.proj_dir = self._get_project_context()
        self.config_data = self._load_config()
        
        # 2. Typ-Auswahl (Dynamisch befüllt aus JSON)
        self.main_layout.addWidget(QtWidgets.QLabel("<b>Komponenten-Typ:</b>"))
        self.type_combo = QtWidgets.QComboBox()
        
        entities = self.config_data.get("Entities", {})
        for key, entity_data in entities.items():
            self.type_combo.addItem(entity_data.get("Label", key), key)
        self.main_layout.addWidget(self.type_combo)
        
        # 3. Teilnummer (Auto-Zählung)
        suggested_num = "0001"
        if self.proj_name and self.proj_dir:
            checker = PartCreator(self.proj_name, self.proj_dir)
            suggested_num = checker.get_next_available_number()
            
        self.main_layout.addWidget(QtWidgets.QLabel("<b>Teilnummer:</b>"))
        self.number_input = QtWidgets.QLineEdit(suggested_num)
        self.main_layout.addWidget(self.number_input)
        
        # 4. DYNAMISCHE ATTRIBUT-CONTAINER
        # Wir erstellen einen Platzhalter für die variablen Felder
        self.dynamic_widget = QtWidgets.QWidget()
        self.dynamic_layout = QtWidgets.QVBoxLayout(self.dynamic_widget)
        self.dynamic_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.addWidget(self.dynamic_widget)
        
        # Map zum Speichern der Eingabefelder für die Erstellung
        self.inputs_map = {}
        
        # Event verknüpfen und ersten Zustand aufbauen
        self.type_combo.currentIndexChanged.connect(self.rebuild_dynamic_fields)
        self.rebuild_dynamic_fields()
        
        # 5. Erstellen Button
        self.create_btn = QtWidgets.QPushButton("Neue Komponente & Datei erstellen")
        self.create_btn.clicked.connect(self.on_create_clicked)
        self.main_layout.addWidget(self.create_btn)
        self.main_layout.addStretch()

    def rebuild_dynamic_fields(self):
        """Löscht alte Felder und baut die GUI passend zu den JSON-Properties neu auf."""
        # Alte Widgets im dynamischen Layout löschen
        while self.dynamic_layout.count():
            item = self.dynamic_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        self.inputs_map.clear()
        comp_type = self.type_combo.currentData()
        
        # Properties aus der JSON für diesen Typ holen
        entity_config = self.config_data.get("Entities", {}).get(comp_type, {})
        properties = entity_config.get("Properties", {})
        
        # Für jede definierte Eigenschaft ein Eingabefeld erzeugen
        for prop_name, prop_meta in properties.items():
            self.dynamic_layout.addWidget(QtWidgets.QLabel(f"<b>{prop_name}:</b>"))
            default_val = str(prop_meta.get("Default", ""))
            input_field = QtWidgets.QLineEdit(default_val)
            
            self.dynamic_layout.addWidget(input_field)
            # Speichern für den Create-Klick
            self.inputs_map[prop_name] = input_field

    def _load_config(self):
        """Lädt die JSON Konfigurationsdatei."""
        if self.proj_dir:
            json_path = os.path.join(self.proj_dir, "FCProject.json")
            if os.path.exists(json_path):
                with open(json_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        return {}

    def _get_project_context(self):
        active_doc = App.ActiveDocument
        if active_doc and active_doc.FileName:
            current_dir = os.path.dirname(active_doc.FileName)
            json_path = os.path.join(current_dir, "FCProject.json")
            if os.path.exists(json_path):
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                metadata = data.get("ProjectMetadata", {})
                return metadata.get("ProjectName", "PROJ"), current_dir
        return None, None

    def on_create_clicked(self):
        if not self.proj_dir: return
        
        comp_type = self.type_combo.currentData()
        comp_num = self.number_input.text().strip()
        
        # Werte aus der dynamischen GUI einsammeln
        payload_properties = {}
        for prop_name, field in self.inputs_map.items():
            payload_properties[prop_name] = field.text().strip()

        try:
            creator = PartCreator(self.proj_name, self.proj_dir)
            # Wir übergeben das gesamte JSON-Eigenschafts-Paket an die Logik
            generated_name = creator.create_pdm_document(comp_type, comp_num, payload_properties)
            QtWidgets.QMessageBox.information(None, "FCProject", f"Komponente {generated_name} erfolgreich erstellt!")
            self.number_input.setText(creator.get_next_available_number())
        except Exception as e:
            QtWidgets.QMessageBox.critical(None, "FCProject", f"Fehler: {str(e)}")

    def getStandardButtons(self):
        return QtWidgets.QDialogButtonBox.Close
