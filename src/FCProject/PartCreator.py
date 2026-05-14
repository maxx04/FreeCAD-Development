# Macro Version: 1.10.0 - FCProject: Universeller, JSON-gesteuerter CAD-Creator
import os
import re
import json
import FreeCAD as App

class PartCreator:
    def __init__(self, project_name, project_dir):
        self.project_name = project_name
        self.project_dir = project_dir
        self.config_data = self._load_config()

    def _load_config(self):
        json_path = os.path.join(self.project_dir, "FCProject.json")
        if os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def get_next_available_number(self):
        highest_num = 0
        if not os.path.exists(self.project_dir): return "0001"
        pattern = re.compile(rf"^{re.escape(self.project_name)}-(\d{{4}})-[APRG]")
        for filename in os.listdir(self.project_dir):
            match = pattern.match(filename)
            if match:
                num = int(match.group(1))
                if num > highest_num: highest_num = num
        return f"{highest_num + 1:04d}"

    def create_pdm_document(self, comp_type, comp_num, user_properties):
        """Erstellt ein CAD-Dokument und spritzt Eigenschaften voll-dynamisch ein."""
        filename_base = f"{self.project_name}-{comp_num}-{comp_type}"
        new_file_path = os.path.join(self.project_dir, f"{filename_base}.FCStd")
        
        if os.path.exists(new_file_path):
            raise FileExistsError(f"Die Datei {filename_base}.FCStd existiert bereits!")

        # Datenstruktur aus der JSON für diesen Typ auslesen
        entity_config = self.config_data.get("Entities", {}).get(comp_type, {})
        fc_type = entity_config.get("FreeCADType", "App::Part")
        
        # 1. Dokument anlegen
        new_doc = App.newDocument(filename_base)
        App.setActiveDocument(new_doc.Name)
        
        # Extra-Initialisierung für Spezial-Workbench Typen (wie Joints bei Assemblies)
        if fc_type == "Assembly::AssemblyObject":
            import UtilsAssembly # type: ignore
            core_obj = new_doc.addObject(fc_type, filename_base)
            new_doc.addObject("Assembly::JointGroup", "Joints")
        else:
            if "PartDesign" in fc_type: import PartDesign # type: ignore
            core_obj = new_doc.addObject(fc_type, filename_base)

        core_obj.Label = filename_base

        # 2. ArticleID für BOM sichern
        if not hasattr(core_obj, "ArticleID"):
            core_obj.addProperty("App::PropertyString", "ArticleID", "FCProject", "Eindeutige ID")
        core_obj.ArticleID = filename_base

        # 3. VOLL-DYNAMISCHE INJEKTION DER PROPERTIES AUS DER JSON
        properties_schema = entity_config.get("Properties", {})
        for prop_name, raw_value in user_properties.items():
            schema = properties_schema.get(prop_name, {})
            prop_type = schema.get("Type", "App::PropertyString")
            prop_cat = schema.get("Category", "FCProject_PDM")
            
            # Eigenschaft dynamisch am Objekt registrieren
            if not hasattr(core_obj, prop_name):
                core_obj.addProperty(prop_type, prop_name, prop_cat, f"Dynamische PDM Variable: {prop_name}")
            
            # Wert typkonform parsen und zuweisen
            try:
                if "Float" in prop_type or "Length" in prop_type:
                    setattr(core_obj, prop_name, float(raw_value))
                else:
                    setattr(core_obj, prop_name, str(raw_value))
            except ValueError:
                App.Console.PrintError(f"FCProject: Typkonvertierungs-Fehler für {prop_name}\n")

        new_doc.saveAs(new_file_path)
        new_doc.recompute()
        return filename_base
