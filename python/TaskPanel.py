# Macro Version: 3.0.0 - FCProject: TaskPanel im Aufgabenbereich (Combo View), nicht mehr freischwebend
import os
import json
import FreeCAD as App
import FreeCADGui as Gui
from PySide6 import QtWidgets, QtCore
from EntityCreator import EntityCreator

# Modul-weite Referenz aufs aktuell offene Panel (falls eins offen ist). Ermöglicht z.B.
# FCProjectWorkbench.Deactivated() (InitGui.py), beim Werkbench-Wechsel zuverlässig zu erkennen,
# ob GERADE UNSER Panel im Aufgabenbereich offen ist, statt versehentlich ein fremdes Task-Panel
# (Sketch-Editor o.ä.) zu schließen.
_active_panel = None

class FCProjectTaskPanel:
    """FreeCAD-Task-Panel-Controller (kein QDialog mehr) - wird über Gui.Control.showDialog()
    im Aufgabenbereich (Combo View) angezeigt. self.form ist das eigentliche Inhalts-Widget;
    eigene Erstellen-/Schließen-Buttons statt der Standard-OK/Abbrechen-Buttons, damit sich
    mehrere Komponenten nacheinander erstellen lassen, ohne das Panel jedes Mal neu zu öffnen
    (getStandardButtons() liefert deshalb bewusst keine Standard-Buttons)."""

    # Welche Geometrie-Basis-Radios pro Komponenten-Typ angeboten werden, in dieser Reihenfolge.
    # "Profil" (Katalog+Länge) bleibt exklusiv bei R, "Halbzeug" (auf einem R-Teil basieren)
    # exklusiv bei P, "STEP" gibt es bei R und B - siehe Absprache mit dem User 2026-08-14.
    _SOURCE_OPTIONS_BY_TYPE = {
        "P": ("halbzeug", "empty"),
        "R": ("profile", "step", "empty"),
        "B": ("step", "empty"),
    }

    def __init__(self):
        self.form = QtWidgets.QWidget()
        self.form.setWindowTitle("FCProject: PDM-Creator")

        self.main_layout = QtWidgets.QVBoxLayout(self.form)
        self.main_layout.addWidget(QtWidgets.QLabel("<h3>FCProject: PDM-Creator</h3>"))

        # Kontext direkt aus dem verifizierten System-Arbeitsverzeichnis laden!
        self.proj_name, self.proj_dir = self._get_project_context()
        self.config_data = self._load_config()

        # STEP-Baumauswahl für Kaufteile (Typ B): zuletzt erkannte (Dokument, Objekt)-Referenzen
        self._step_source_refs = []
        self._step_watch_timer = None

        # Wird von Commands.py VOR Gui.Control.showDialog() geprüft - bei ungültiger Projekt-
        # Konfiguration gibt es kein Aufgabenbereich-Panel zum Selbst-Schließen mehr (anders als
        # frueher als freischwebender QDialog per QTimer.singleShot(self.close)).
        self.valid = bool(self.config_data)
        if not self.valid:
            QtWidgets.QMessageBox.critical(
                Gui.getMainWindow(), "FCProject",
                "Keine gültige Projekt-Konfiguration im aktiven Arbeitsverzeichnis gefunden!\n"
                "Bitte nutze zuerst Button 1."
            )
            return

        # 1. Typ-Auswahl
        self.main_layout.addWidget(QtWidgets.QLabel("<b>Komponenten-Typ:</b>"))
        self.type_combo = QtWidgets.QComboBox()
        entities = self.config_data.get("Entities", {})

        # Einträge dynamisch aus der JSON laden (P, R, B, A) und die Labels anzeigen
        for key, entity_data in entities.items():
            self.type_combo.addItem(entity_data.get("Label", key), key)
        self.main_layout.addWidget(self.type_combo)

        # 2. Teilnummer
        suggested_num = "001"
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

        # 4b. GEOMETRIE-BASIS - direkt unter Material, welche Radios sichtbar sind hängt vom Typ ab
        # (siehe _SOURCE_OPTIONS_BY_TYPE): P -> Halbzeug/Leer, R -> Profil/STEP/Leer, B -> STEP/Leer.
        # Alle vier Radios werden hier einmal angelegt (Qt gruppiert sie über den gemeinsamen
        # Eltern-Layout automatisch gegenseitig exklusiv, auch wenn einzelne unsichtbar sind) -
        # rebuild_dynamic_fields() blendet pro Typ nur die passende Teilmenge ein.
        self.source_widget = QtWidgets.QWidget()
        source_layout = QtWidgets.QVBoxLayout(self.source_widget)
        source_layout.setContentsMargins(0, 0, 0, 0)
        source_layout.addWidget(QtWidgets.QLabel("<b>Geometrie-Basis:</b>"))

        radio_row = QtWidgets.QHBoxLayout()
        self.source_halbzeug_radio = QtWidgets.QRadioButton("Halbzeug")  # Typ P: auf einem R-Teil basieren
        self.source_profile_radio = QtWidgets.QRadioButton("Profil")    # Typ R: Katalog-Profil + Länge
        self.source_step_radio = QtWidgets.QRadioButton("STEP")         # Typ R, B
        self.source_empty_radio = QtWidgets.QRadioButton("Leer")        # P, R, B
        self.source_empty_radio.setChecked(True)
        for radio in (self.source_halbzeug_radio, self.source_profile_radio, self.source_step_radio, self.source_empty_radio):
            radio_row.addWidget(radio)
            radio.toggled.connect(self._update_source_sub_visibility)
        source_layout.addLayout(radio_row)

        # Halbzeug-Unterbereich (Typ P): Datei wählen + Anzeige des gewählten Pfads. Mechanisch
        # identisch zur früheren "Profil"-Option bei Kaufteilen - beliebige bestehende .FCStd
        # klonen -, jetzt aber inhaltlich auf "P basiert auf einem R-Halbzeug" gemünzt.
        self.file_sub_widget = QtWidgets.QWidget()
        file_sub_layout = QtWidgets.QHBoxLayout(self.file_sub_widget)
        file_sub_layout.setContentsMargins(0, 0, 0, 0)
        self.profile_path_display = QtWidgets.QLineEdit()
        self.profile_path_display.setReadOnly(True)
        self.profile_path_display.setPlaceholderText("Keine Datei gewählt…")
        self.profile_browse_btn = QtWidgets.QPushButton("Datei wählen…")
        self.profile_browse_btn.clicked.connect(self._on_browse_profile_file)
        file_sub_layout.addWidget(self.profile_path_display)
        file_sub_layout.addWidget(self.profile_browse_btn)
        source_layout.addWidget(self.file_sub_widget)

        # STEP-Unterbereich: reine Live-Anzeige, was gerade im Baum ausgewählt ist
        self.step_sub_widget = QtWidgets.QWidget()
        step_sub_layout = QtWidgets.QVBoxLayout(self.step_sub_widget)
        step_sub_layout.setContentsMargins(0, 0, 0, 0)
        self.step_object_display = QtWidgets.QLineEdit()
        self.step_object_display.setReadOnly(True)
        self.step_object_display.setPlaceholderText("Bitte STEP-Objekt(e) im Baum auswählen…")
        step_sub_layout.addWidget(self.step_object_display)
        source_layout.addWidget(self.step_sub_widget)

        # Profil-Unterbereich (Typ R) braucht kein eigenes Widget - das ProfilTyp-Dropdown +
        # Length-Feld werden von rebuild_dynamic_fields() wie gehabt im dynamic_layout gerendert;
        # _update_source_sub_visibility() blendet die beiden nur je nach Radio-Wahl ein/aus.

        self.main_layout.addWidget(self.source_widget)

        # Timer, der bei aktivem STEP-Radio die Baum-Auswahl beobachtet und den Namen einträgt
        self._step_watch_timer = QtCore.QTimer()
        self._step_watch_timer.timeout.connect(self._poll_step_selection)

        self.inputs_map = {}
        self.timer = None
        self.type_combo.currentIndexChanged.connect(self.rebuild_dynamic_fields)
        self.rebuild_dynamic_fields()

        # 5. Erstellen Button (kein Standard-OK - siehe getStandardButtons())
        self.create_btn = QtWidgets.QPushButton("Neue Komponente & Datei erstellen")
        self.create_btn.clicked.connect(self.on_create_clicked)
        self.main_layout.addWidget(self.create_btn)

        self.close_btn = QtWidgets.QPushButton("Schließen")
        self.close_btn.clicked.connect(self._on_close_clicked)
        self.main_layout.addWidget(self.close_btn)

        self.main_layout.addStretch()

        global _active_panel
        _active_panel = self

    # --- FreeCAD-Task-Panel-Protokoll (Gui.Control) ---

    def getStandardButtons(self):
        """Keine Standard-OK/Abbrechen-Buttons - eigene Erstellen-/Schließen-Buttons oben im
        Formular übernehmen das, damit 'Erstellen' das Panel NICHT automatisch schließt
        (mehrere Komponenten nacheinander erstellen, ohne den Dialog neu zu öffnen)."""
        return QtWidgets.QDialogButtonBox.NoButton

    def accept(self):
        # Wird ohne Standard-OK-Button nie vom Framework aufgerufen; nur der Vollständigkeit
        # halber implementiert (Teil des FreeCAD-Task-Panel-Protokolls).
        return True

    def reject(self):
        """Aufräumen, bevor das Panel aus dem Aufgabenbereich entfernt wird. Teil des FreeCAD-
        Task-Panel-Protokolls, wird aber NICHT automatisch von Gui.Control aufgerufen - anders
        als die C++-Seite (ControlSingleton::reject) ist auf der Python-Seite (Gui.Control) kein
        reject()/accept() exponiert (nur showDialog/activeDialog/activeTaskDialog/closeDialog,
        siehe FreeCADGui._Control.pyi) - deshalb rufen _on_close_clicked() und
        FCProjectWorkbench.Deactivated() (InitGui.py) diese Methode selbst auf, bevor sie
        Gui.Control.closeDialog() zum eigentlichen Schließen aufrufen."""
        global _active_panel
        if _active_panel is self:
            _active_panel = None
        if self._step_watch_timer is not None:
            self._step_watch_timer.stop()
        return True

    def _on_close_clicked(self):
        self.reject()
        Gui.Control.closeDialog()

    # --- Ab hier: unverändert gegenüber der freischwebenden Dialog-Version ---

    @staticmethod
    def _detect_step_source_selection():
        """Filtert die aktuelle Baum-Auswahl auf verwertbare STEP-Import-Quellen: entweder rohe
        Shape-Objekte, oder Struktur-Container (App::Part/Gruppe) mit Unterstruktur - z.B. ein
        strukturiert importiertes STEP mit benannten Baugruppen-Knoten wie "Ze Carrige". Bereits
        fertige FCProject-PDM-Objekte (Body/Assembly) werden ausgeschlossen - es geht nur um
        frische, noch unverarbeitete Import-Geometrie/-Struktur."""
        candidates = []
        for obj in Gui.Selection.getSelection():
            if obj.isDerivedFrom("PartDesign::Body") or obj.isDerivedFrom("Assembly::AssemblyObject"):
                continue
            is_leaf_shape = hasattr(obj, "Shape") and obj.Shape is not None and not obj.Shape.isNull()
            is_structural = obj.isDerivedFrom("App::Part") or obj.isDerivedFrom("App::DocumentObjectGroup")
            if is_leaf_shape or is_structural:
                candidates.append(obj)
        return candidates

    def rebuild_dynamic_fields(self):
        """Baut die dynamischen Felder auf. Erzeugt bei Typ R ein Dropdown für die Profile."""
        while self.dynamic_layout.count():
            item = self.dynamic_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.inputs_map.clear()
        self.field_labels_map = {}  # prop_name -> zugehöriges <b>Label</b>-Widget (fürs Ein-/Ausblenden)
        comp_type = self.type_combo.currentData()

        # Material-Bereich ein- oder ausblenden
        if comp_type in ["P", "R", "B"]:
            self.material_widget.setVisible(True)
        else:
            self.material_widget.setVisible(False)

        # Geometrie-Basis-Bereich: welche Radios angeboten werden, hängt vom Typ ab (siehe
        # _SOURCE_OPTIONS_BY_TYPE); bei Typwechsel immer auf "Leer" zurücksetzen, damit keine
        # unsichtbare Auswahl (z.B. "Profil" von R) beim Wechsel zu B aktiv/angehakt bleibt.
        if hasattr(self, "source_widget"):
            allowed = self._SOURCE_OPTIONS_BY_TYPE.get(comp_type, ())
            self.source_widget.setVisible(bool(allowed))
            radio_by_key = {
                "halbzeug": self.source_halbzeug_radio,
                "profile": self.source_profile_radio,
                "step": self.source_step_radio,
                "empty": self.source_empty_radio,
            }
            for key, radio in radio_by_key.items():
                radio.setVisible(key in allowed)
            self.source_empty_radio.setChecked(True)

        entity_config = self.config_data.get("Entities", {}).get(comp_type, {})
        properties = entity_config.get("Properties", {})

        for prop_name, prop_meta in properties.items():
            label_widget = QtWidgets.QLabel(f"<b>{prop_name}:</b>")
            self.dynamic_layout.addWidget(label_widget)
            self.field_labels_map[prop_name] = label_widget
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

                combo_field.currentIndexChanged.connect(self._update_material_from_profile)
                self.dynamic_layout.addWidget(combo_field)
                self.inputs_map[prop_name] = combo_field
                # Initial: Material aus dem aktuell vorausgewählten Profil laden
                QtCore.QTimer.singleShot(0, self._update_material_from_profile)
            else:
                # Normales Textfeld für alle anderen Eigenschaften (Length, Bezeichnung, Hersteller etc.)
                input_field = QtWidgets.QLineEdit(default_val)
                self.dynamic_layout.addWidget(input_field)
                self.inputs_map[prop_name] = input_field

        # Erst jetzt, wo ProfilTyp/Length (falls Typ R) tatsächlich existieren, die
        # Geometrie-Basis-Sichtbarkeit anwenden (blendet sie ggf. wieder aus, bis "Profil" gewählt ist).
        if hasattr(self, "source_widget"):
            self._update_source_sub_visibility()

    def _update_material_from_profile(self):
        """Liest das ShapeMaterial aus der gewählten Profildatei und trägt es ins Material-Feld ein."""
        profile_combo = self.inputs_map.get("ProfilTyp")
        if not profile_combo or not self.proj_dir:
            return

        profile_name = profile_combo.currentData()
        if not profile_name or profile_name == "None":
            return

        base_cad_dir = os.path.dirname(self.proj_dir)
        profile_path = os.path.join(base_cad_dir, "_Common_Resources", "Profiles", f"{profile_name}.FCStd")

        if not os.path.exists(profile_path):
            return

        # Prüfen ob das Profil-Dokument bereits offen ist (nicht doppelt öffnen)
        already_open_name = None
        for doc_name, doc in App.listDocuments().items():
            if hasattr(doc, 'FileName') and doc.FileName == profile_path:
                already_open_name = doc_name
                break

        try:
            if already_open_name:
                temp_doc = App.getDocument(already_open_name)
                should_close = False
            else:
                temp_doc = App.openDocument(profile_path)
                should_close = True

            material_name = None
            for obj in temp_doc.Objects:
                if obj.isDerivedFrom("PartDesign::Body") and hasattr(obj, "ShapeMaterial"):
                    mat = obj.ShapeMaterial
                    if mat and hasattr(mat, 'Name') and mat.Name and mat.Name != "Default":
                        material_name = mat.Name
                        break

            if should_close:
                App.closeDocument(temp_doc.Name)

            if material_name:
                self.material_input.setText(material_name)
                App.Console.PrintMessage(f"FCProject: Material '{material_name}' aus Profil '{profile_name}' übernommen.\n")

        except Exception as e:
            App.Console.PrintWarning(f"FCProject: Material aus Profil '{profile_name}' konnte nicht gelesen werden: {str(e)}\n")

    def open_material_gui_via_dummy_object(self):
        # ACHTUNG: Gui.runCommand('Std_SetMaterial', 0) öffnet selbst ein Gui.Control-Task-Panel.
        # Solange DIESES Panel (FCProjectTaskPanel) im Aufgabenbereich aktiv ist, belegt es den
        # Task-Panel-Slot des aktiven Dokuments bereits - Std_SetMaterial kann dann sein eigenes
        # Panel nicht öffnen (FreeCAD gibt nur eine Konsolen-Warnung aus, kein Absturz). Bekannter,
        # noch offener Punkt - siehe [[project_fcproject_kaufteil_step_workflow]] Punkt 2.
        active_doc = App.ActiveDocument
        if not active_doc:
            QtWidgets.QMessageBox.warning(self.form, "FCProject", "Bitte öffne zuerst ein Dokument!")
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
        """Lädt die Konfiguration aus der JSON, die exakt wie der Projektordner benannt ist (z.B. PROJ_U20.json)."""
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

    def on_create_clicked(self):
        """Sammelt die Daten aus der GUI und triggert die Erstellung der PDM-Komponente und der zugehörigen CAD-Datei."""
        if not self.proj_dir: return

        comp_type = self.type_combo.currentData()
        comp_num = self.number_input.text().strip()

        # In deiner TaskPanel.py -> Innerhalb von on_create_clicked:
        # Werte aus der dynamischen GUI einsammeln (Unterstützt jetzt LineEdit und QComboBox)
        payload_properties = {}
        #
        for prop_name, widget in self.inputs_map.items():
            if isinstance(widget, QtWidgets.QComboBox):
                payload_properties[prop_name] = widget.currentData()
            else:
                payload_properties[prop_name] = widget.text().strip()


        if comp_type in ["P", "R", "B"]:
            payload_properties["__TargetMaterialName__"] = self.material_input.text().strip()

        # GEOMETRIE-QUELLE: direkt aus der Radio-Auswahl im Dialog lesen - welche Radios es gibt,
        # hängt vom Typ ab (siehe _SOURCE_OPTIONS_BY_TYPE).
        if comp_type == "P":
            if self.source_halbzeug_radio.isChecked():
                selected_path = self.profile_path_display.text().strip()
                if not selected_path:
                    QtWidgets.QMessageBox.warning(self.form, "FCProject", "Bitte zuerst eine Halbzeug-Datei wählen.")
                    return
                payload_properties["__LinkedRawProfilePath__"] = selected_path
            # source_empty_radio -> kein Zusatz, leerer Body zum freien Konstruieren

        elif comp_type == "R":
            if self.source_profile_radio.isChecked():
                # Profil+Länge: ProfilTyp/Length kommen schon aus inputs_map (oben eingesammelt) -
                # hier nur validieren, dass wirklich ein Profil gewählt wurde.
                if not payload_properties.get("ProfilTyp") or payload_properties["ProfilTyp"] == "None":
                    QtWidgets.QMessageBox.warning(self.form, "FCProject", "Bitte zuerst ein Profil wählen.")
                    return
            else:
                # STEP/Leer -> ProfilTyp/Length sind hier irrelevant, nicht mitschicken (sonst
                # würde RAWCreator sie fälschlich als Profil-Auswahl interpretieren).
                payload_properties.pop("ProfilTyp", None)
                payload_properties.pop("Length", None)

                if self.source_step_radio.isChecked():
                    if not self._step_source_refs:
                        QtWidgets.QMessageBox.warning(self.form, "FCProject", "Bitte zuerst ein STEP-Objekt im Baum auswählen.")
                        return
                    payload_properties["__StepSourceRefs__"] = list(self._step_source_refs)
                # source_empty_radio -> kein Zusatz, leerer Platzhalter-Body

        elif comp_type == "B":
            if self.source_step_radio.isChecked():
                if not self._step_source_refs:
                    QtWidgets.QMessageBox.warning(self.form, "FCProject", "Bitte zuerst ein STEP-Objekt im Baum auswählen.")
                    return
                payload_properties["__StepSourceRefs__"] = list(self._step_source_refs)
            # source_empty_radio -> kein Zusatz, normales leeres App::Part

        self._finalize_creation(comp_type, comp_num, payload_properties)

    def _update_source_sub_visibility(self):
        """Blendet je nach gewähltem Radio-Button den passenden Unterbereich ein/aus (Halbzeug-
        Datei-Auswahl, STEP-Live-Anzeige, bei Typ R die ProfilTyp/Length-Felder) und
        startet/stoppt die Baum-Auswahl-Beobachtung."""
        if not hasattr(self, "file_sub_widget"):
            return
        comp_type = self.type_combo.currentData()

        self.file_sub_widget.setVisible(self.source_halbzeug_radio.isChecked())
        self.step_sub_widget.setVisible(self.source_step_radio.isChecked())

        # Bei Typ R gehören ProfilTyp/Length zu "Profil" - nur zeigen, wenn das auch die aktive
        # Geometrie-Basis ist (die Felder selbst leben im dynamic_layout, siehe rebuild_dynamic_fields).
        if comp_type == "R":
            show_profile_fields = self.source_profile_radio.isChecked()
            for name in ("ProfilTyp", "Length"):
                field = self.inputs_map.get(name)
                label = self.field_labels_map.get(name)
                if field is not None:
                    field.setVisible(show_profile_fields)
                if label is not None:
                    label.setVisible(show_profile_fields)

        is_step_active = comp_type in ("R", "B") and self.source_step_radio.isChecked()
        if is_step_active:
            main_win = Gui.getMainWindow()
            if main_win:
                main_win.statusBar().showMessage(
                    "FCProject: Bitte das importierte STEP-Objekt (bzw. mehrere) im Baum auswählen…", 0
                )
            if not self._step_watch_timer.isActive():
                self._step_watch_timer.start(300)
        else:
            self._step_watch_timer.stop()

    def _poll_step_selection(self):
        """Läuft alle 300ms, solange STEP als Geometrie-Basis aktiv ist: übernimmt eine gültige
        Baum-Auswahl live in die Anzeige, ohne selbst irgendetwas zu erstellen."""
        candidates = self._detect_step_source_selection()
        if not candidates:
            return  # Alte Auswahl (falls vorhanden) bewusst stehen lassen, nicht löschen
        self._step_source_refs = [(obj.Document.Name, obj.Name) for obj in candidates]
        self.step_object_display.setText(", ".join(obj.Label for obj in candidates))

    def _on_browse_profile_file(self):
        """Öffnet den Dateidialog für die 'Halbzeug'-Geometrie-Basis eines Einzelteils (Typ P)."""
        start_dir = self.proj_dir if self.proj_dir and os.path.exists(self.proj_dir) else os.getcwd()
        selected_file, _ = QtWidgets.QFileDialog.getOpenFileName(
            self.form,
            "Halbzeug für Einzelteil auswählen...",
            start_dir,
            "FreeCAD Dokumente (*.FCStd)"
        )
        if selected_file:
            self.profile_path_display.setText(selected_file)

    def _finalize_creation(self, comp_type, comp_num, payload_properties):
        """Letzter Schritt: PDM-Komponente inkl. CAD-Datei tatsächlich erstellen und Feedback geben."""
        try:
            creator = EntityCreator(self.proj_name, self.proj_dir)
            generated_name = creator.create_pdm_document(comp_type, comp_num, payload_properties)
            self._fit_and_isometric_view(generated_name)
            # Bewusst kein modaler Dialog mehr hier - beim Erstellen mehrerer Komponenten
            # nacheinander (der Normalfall) musste sonst jedes Mal weggeklickt werden. Erfolg
            # reicht als Log-Eintrag in der Report-Ansicht; Fehler bleiben unten ein echter Dialog.
            App.Console.PrintMessage(f"FCProject: Komponente '{generated_name}' erfolgreich erstellt.\n")
            self.number_input.setText(creator.get_next_available_number())
            self._reset_source_selection()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self.form, "FCProject", f"Fehler: {str(e)}")

    @staticmethod
    def _fit_and_isometric_view(doc_name):
        """Nach dem Erstellen die neue Komponente direkt sichtbar machen: Alles einpassen + Isometrisch.

        Bewusst NICHT über Gui.runCommand('Std_ViewFitAll'/'Std_ViewIsometric'): deren isActive()
        prüft intern die aktuell als 'aktiv' registrierte 3D-View, und die frisch erzeugte
        Dokument-View ist das im selben Python-Aufruf oft noch nicht - der Befehl tut dann
        (fehlerfrei!) einfach gar nichts. Stattdessen direkt über das View-Objekt der neuen
        Dokument-View, die immer existiert."""
        try:
            gui_doc = Gui.getDocument(doc_name) if doc_name else None
            view = gui_doc.ActiveView if gui_doc else None
            if view is None and Gui.ActiveDocument:
                view = Gui.ActiveDocument.ActiveView
            if view:
                view.fitAll()
                view.viewIsometric()
        except Exception as e:
            App.Console.PrintWarning(f"FCProject: Ansicht konnte nicht automatisch angepasst werden: {str(e)}\n")

    def _reset_source_selection(self):
        """Setzt die Geometrie-Basis nach erfolgreicher Erstellung zurück, damit nicht versehentlich
        dieselbe STEP-Auswahl/Vorlagendatei für die nächste Komponente wiederverwendet wird."""
        if not hasattr(self, "source_empty_radio"):
            return
        self.source_empty_radio.setChecked(True)
        self.profile_path_display.clear()
        self.step_object_display.clear()
        self._step_source_refs = []
