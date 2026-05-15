# Macro Version: 2.8.0 - FCProject: TaskPanel mit automatischer Arbeitsverzeichnis-JSON-Abfrage
import os
import json
import FreeCAD as App
import FreeCADGui as Gui
from PySide6 import QtWidgets, QtCore
from EntityCreator import EntityCreator

class FCProjectTaskPanel(QtWidgets.QDialog):
    def __init__(self):
        super().__init__(Gui.getMainWindow())
        
        self.setWindowTitle("FCProject: PDM-Creator")
        self.resize(350, 420)
        
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.addWidget(QtWidgets.QLabel("<h3>FCProject: PDM-Creator</h3>"))
        
        # KORREKTUR: Kontext direkt aus dem verifizierten System-Arbeitsverzeichnis laden!
        self.proj_name, self.proj_dir = self._get_project_context()
        self.config_data = self._load_config()
        
        if not self.config_data:
            QtWidgets.QMessageBox.critical(self, "FCProject", "Keine gültige Projekt-Konfiguration im aktiven Arbeitsverzeichnis gefunden!\nBitte nutze zuerst Button 1.")
            QtCore.QTimer.singleShot(10, self.close)
            return

        # 1. Typ-Auswahl
        self.main_layout.addWidget(QtWidgets.QLabel("<b>Komponenten-Typ:</b>"))
        self.type_combo = QtWidgets.QComboBox()
        entities = self.config_data.get("Entities", {})
        for key, entity_data in entities.items():
            self.type_combo.addItem(entity_data.get("Label", key), key)
        self.main_layout.addWidget(self.type_combo)
        
        # 2. Teilnummer
        suggested_num = "0001"
        if self.proj_name and self.proj_dir:
            checker = EntityCreator(self.proj_name, self.proj_dir)
            suggested_num = checker.get_next_available_number()
        self.main_layout.addWidget(QtWidgets.QLabel("<b>Teilnummer:</b>"))
        self.number_input = QtWidgets.QLineEdit(suggested_num)
        self.main_layout.addWidget(self.number_input)
        
        # 3. DYNAMISCHE FELDER
        self.dynamic_widget = QtWidgets.QWidget()
        self.dynamic_layout = QtWidgets.QVBoxLayout(self.dynamic_widget)
        self.dynamic_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.addWidget(self.dynamic_widget)
        
        # 4. INTERAKTIVER MATERIAL-BEREICH
        self.material_widget = QtWidgets.QWidget()
        mat_layout = QtWidgets.QVBoxLayout(self.material_widget)
        mat_layout.setContentsMargins(0, 0, 0, 0)
        mat_layout.addWidget(QtWidgets.QLabel("<b>Material (CAD-Standard):</b>"))
        
        h_layout = QtWidgets.QHBoxLayout()
        self.material_input = QtWidgets.QLineEdit("Aluminum")
        self.change_material_btn = QtWidgets.QPushButton("Material ändern...")
        self.change_material_btn.clicked.connect(self.open_material_gui_via_dummy_object)
        
        h_layout.addWidget(self.material_input)
        h_layout.addWidget(self.change_material_btn)
        mat_layout.addLayout(h_layout)
        self.main_layout.addWidget(self.material_widget)
        
        self.inputs_map = {}
        self.timer = None
        self.type_combo.currentIndexChanged.connect(self.rebuild_dynamic_fields)
        self.rebuild_dynamic_fields()
        
        # 5. Erstellen Button
        self.create_btn = QtWidgets.QPushButton("Neue Komponente & Datei erstellen")
        self.create_btn.clicked.connect(self.on_create_clicked)
        self.main_layout.addWidget(self.create_btn)
        
        self.close_btn = QtWidgets.QPushButton("Schließen")
        self.close_btn.clicked.connect(self.close)
        self.main_layout.addWidget(self.close_btn)
        
        self.main_layout.addStretch()

    def rebuild_dynamic_fields(self):
        """Baut die dynamischen Felder auf. Erzeugt bei Typ R ein Dropdown für die Profile."""
        while self.dynamic_layout.count():
            item = self.dynamic_layout.takeAt(0)
            if item.widget(): 
                item.widget().deleteLater()
                
        self.inputs_map.clear()
        comp_type = self.type_combo.currentData()
        
        # Material-Bereich ein- oder ausblenden
        if comp_type in ["P", "R", "B"]:
            self.material_widget.setVisible(True)
        else:
            self.material_widget.setVisible(False)
            
        entity_config = self.config_data.get("Entities", {}).get(comp_type, {})
        properties = entity_config.get("Properties", {})
        
        for prop_name, prop_meta in properties.items():
            self.dynamic_layout.addWidget(QtWidgets.QLabel(f"<b>{prop_name}:</b>"))
            default_val = str(prop_meta.get("Default", ""))
            
            # KORREKTUR: Wenn wir ein Halbzeug (R) erstellen und beim Feld 'ProfilTyp' sind
            if comp_type == "R" and prop_name == "ProfilTyp":
                combo_field = QtWidgets.QComboBox()
                
                # Pfad zum GLOBALEN Ressourcen-Profilordner ermitteln
                # self.proj_dir ist z.B. .../Arbeitsordner/PROJ_U20
                # Der gemeinsame Ordner liegt eine Ebene höher unter _Common_Resources/Profiles
                if self.proj_dir:
                    base_cad_dir = os.path.dirname(self.proj_dir)
                    global_profiles_dir = os.path.join(base_cad_dir, "_Common_Resources", "Profiles")
                    
                    if os.path.exists(global_profiles_dir):
                        # Scanne den globalen Ordner nach echten Master-Skizzen
                        for file in os.listdir(global_profiles_dir):
                            if file.endswith(".FCStd"):
                                clean_name = os.path.splitext(file)[0]
                                combo_field.addItem(clean_name, clean_name)
                
                # Falls der Ordner noch komplett leer ist, einen Hinweis einfügen
                if combo_field.count() == 0:
                    combo_field.addItem("Keine Vorlagen in _Common_Resources gefunden", "None")
                    
                self.dynamic_layout.addWidget(combo_field)
                self.inputs_map[prop_name] = combo_field
            else:
                # Normales Textfeld für alle anderen Eigenschaften (Length, Bezeichnung, Hersteller etc.)
                input_field = QtWidgets.QLineEdit(default_val)
                self.dynamic_layout.addWidget(input_field)
                self.inputs_map[prop_name] = input_field


    def open_material_gui_via_dummy_object(self):
        active_doc = App.ActiveDocument
        if not active_doc:
            QtWidgets.QMessageBox.warning(self, "FCProject", "Bitte öffne zuerst ein Dokument!")
            return

        try:
            dummy_obj = active_doc.addObject("PartDesign::Body", "FCProject_DummyMaterialBody")
            active_doc.recompute()
            
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(active_doc.Name, dummy_obj.Name)
            QtWidgets.QApplication.processEvents()
            
            Gui.runCommand('Std_SetMaterial', 0)
            
            def check_dummy_selection():
                if dummy_obj and hasattr(dummy_obj, "ShapeMaterial") and dummy_obj.ShapeMaterial:
                    detected_mat = dummy_obj.ShapeMaterial.Name
                    if detected_mat and detected_mat != "Default":
                        self.material_input.setText(detected_mat)
                        self.timer.stop()
                        Gui.Control.closeDialog()
                        active_doc.removeObject(dummy_obj.Name)
                        active_doc.recompute()
                        
            self.timer = QtCore.QTimer()
            self.timer.timeout.connect(check_dummy_selection)
            self.timer.start(300)
        except Exception as e:
            App.Console.PrintError(f"FCProject: Fehler beim Material-Dialog: {str(e)}\n")

    def _load_config(self):
        if self.proj_dir:
            # Sucht die JSON, die exakt wie der Projektordner benannt ist
            folder_name = os.path.basename(self.proj_dir)
            json_path = os.path.join(self.proj_dir, f"{folder_name}.json")
            if os.path.exists(json_path):
                with open(json_path, 'r', encoding='utf-8') as f: return json.load(f)
        return {}

    def _get_project_context(self):
        """Ermittelt den Kontext aus dem System-Arbeitsverzeichnis oder dem aktiven Dokument."""
        current_dir = os.getcwd()
        folder_name = os.path.basename(current_dir)
        
        # 1. Versuch: Über den Namen des Arbeitsverzeichnisses gehen
        if folder_name and folder_name.startswith("PROJ_"):
            proj_name = folder_name.replace("PROJ_", "")
            return proj_name, current_dir
            
        # 2. Versuch: Wenn wir im falschen Verzeichnis stehen, nutze das aktive Dokument
        active_doc = App.ActiveDocument
        if active_doc:
            # Falls die Datei auf der Festplatte liegt, nimm das Verzeichnis
            if active_doc.FileName:
                doc_dir = os.path.dirname(active_doc.FileName)
                doc_folder = os.path.basename(doc_dir)
                if doc_folder.startswith("PROJ_"):
                    return doc_folder.replace("PROJ_", ""), doc_dir
            
            # Fallback: Nutze einfach den reinen Namen des Dokuments im RAM (z.B. "U15")
            if active_doc.Name:
                return active_doc.Name, current_dir
                
        # Ultimativer Rettungsanker, damit niemals 'None' übergeben wird
        return "PROJ", current_dir

                
        return None, None

    def on_create_clicked(self):
        if not self.proj_dir: return
        
        comp_type = self.type_combo.currentData()
        comp_num = self.number_input.text().strip()
        
        # In deiner TaskPanel.py -> Innerhalb von on_create_clicked:
        # Werte aus der dynamischen GUI einsammeln (Unterstützt jetzt LineEdit und QComboBox)
        payload_properties = {}
        for prop_name, widget in self.inputs_map.items():
            if isinstance(widget, QtWidgets.QComboBox):
                payload_properties[prop_name] = widget.currentData()
            else:
                payload_properties[prop_name] = widget.text().strip()

            
        if comp_type in ["P", "R", "B"]:
            payload_properties["__TargetMaterialName__"] = self.material_input.text().strip()

        # DYNAMISCHE DATEIAUSWAHL FÜR HALBZEUGE (TYP P)
        if comp_type == "P":
            msg_box = QtWidgets.QMessageBox(self)
            msg_box.setWindowTitle("FCProject: Halbzeug-Kopplung")
            msg_box.setText("Basiert dieses Einzelteil auf einem bestehenden Halbzeug/Profil?")
            msg_box.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
            msg_box.setDefaultButton(QtWidgets.QMessageBox.No)
            
            if msg_box.exec() == QtWidgets.QMessageBox.Yes:
                # Standardmäßig im globalen Ressourcen-Ordner starten
                common_profiles_dir = os.path.join(os.path.dirname(self.proj_dir), "_Common_Resources", "Profiles")
                if not os.path.exists(common_profiles_dir):
                    common_profiles_dir = os.path.dirname(self.proj_dir)
                
                # ECHTER DATEIAUSWAHL-DIALOG auf der Festplatte aufrufen
                selected_file, _ = QtWidgets.QFileDialog.getOpenFileName(
                    self, 
                    "Halbzeug-Rohling auswählen...", 
                    common_profiles_dir, 
                    "FreeCAD Dokumente (*.FCStd)"
                )
                
                if selected_file:
                    # Wir übergeben den ABSOLUTEN PFAD der gewählten Datei an den PartCreator!
                    payload_properties["__LinkedRawProfilePath__"] = selected_file

        try:
            creator = EntityCreator(self.proj_name, self.proj_dir)
            generated_name = creator.create_pdm_document(comp_type, comp_num, payload_properties)
            QtWidgets.QMessageBox.information(self, "FCProject", f"Komponente {generated_name} erfolgreich erstellt!")
            self.number_input.setText(creator.get_next_available_number())
        except Exception as e:
            QtWidgets.QMessageBox.critical(None, "FCProject", f"Fehler: {str(e)}")
