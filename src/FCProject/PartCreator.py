# Macro Version: 1.12.1 - FCProject: PDM-Creator Variablen-Fix (trailing)
import os
import re

class PartCreator:
    """Zentrale PDM-Logik für native FreeCAD 1.1 Objekte mit Unterstrich-Schema."""
    
    def __init__(self, project_name, project_dir):
        self.project_name = project_name
        self.project_dir = project_dir
        self.config_data = self._load_config()

    def _load_config(self):
        """Lädt die JSON Konfigurationsdatei mit integrierter Absturzsicherung."""
        import json # Inline-Import gegen NameError
        json_path = os.path.join(self.project_dir, "FCProject.json")
        if os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def get_next_available_number(self):
        """Scannt den Ordner nach Mustern wie 'PROJ_XXXX_*' und gibt die nächste Nummer zurück."""
        highest_num = 0
        if not os.path.exists(self.project_dir): 
            return "0001"

        pattern = re.compile(rf"^{re.escape(self.project_name)}_(\d{{4}})_[APRG]")
        
        for filename in os.listdir(self.project_dir):
            match = pattern.match(filename)
            if match:
                num = int(match.group(1))
                if num > highest_num: 
                    highest_num = num
                    
        return f"{highest_num + 1:04d}"

    def create_pdm_document(self, comp_type, comp_num, user_properties):
        """Erstellt eine neue .FCStd-Datei und benennt sie und das Label nach dem PDM-Muster."""
        import FreeCAD as App # Inline-Import zur Sicherheit
        
                # 1. Optionale Bezeichnung aus der GUI holen für das Suffix
        bezeichnung_suffix = ""
        # ERWEITERUNG: Jetzt greift die Logik für P (Part) UND A (Assembly)!
        if comp_type in ["P", "A"] and "Bezeichnung" in user_properties and user_properties["Bezeichnung"]:
            bezeichnung_suffix = f"_{user_properties['Bezeichnung']}"
        elif comp_type == "R" and "ProfilTyp" in user_properties and user_properties["ProfilTyp"]:
            bezeichnung_suffix = f"_{user_properties['ProfilTyp']}"


        # 2. Struktur: Reines Unterstrich-Schema (z.B. U10_0002_P_Block)
        pdm_base_name = f"{self.project_name}_{comp_num}_{comp_type}{bezeichnung_suffix}"
        
        # ACHTUNG: Der abschließende Unterstrich im Dateinamen (z.B. U10_0002_P_Block_)
        filename_with_trailing = f"{pdm_base_name}_"
        new_file_path = os.path.join(self.project_dir, f"{filename_with_trailing}.FCStd")
        
        if os.path.exists(new_file_path):
            raise FileExistsError(f"Die Datei {filename_with_trailing}.FCStd existiert bereits!")

        entity_config = self.config_data.get("Entities", {}).get(comp_type, {})
        fc_type = entity_config.get("FreeCADType", "App::Part")
        
        # 3. Neues separates Dokument anlegen (KORREKTUR: Variablenname fixiert!)
        new_doc = App.newDocument(filename_with_trailing)
        App.setActiveDocument(new_doc.Name)
        
        # 4. Core-Objekt erzeugen (Nutzt den sauberen Namen als interne ID)
        if fc_type == "Assembly::AssemblyObject":
            import UtilsAssembly # type: ignore
            core_obj = new_doc.addObject(fc_type, pdm_base_name)
        else:
            if "PartDesign" in fc_type: import PartDesign # type: ignore
            core_obj = new_doc.addObject(fc_type, pdm_base_name)

        # 5. DYNAMISCHES VISUELLES LABEL FÜR DEN BAUM INKLUSIVE ZUSATZ-SPALTEN
        if comp_type in ["P", "A"]:
            # Schreibt den sauberen Namen inklusive Bezeichnung ins Baum-Label
            core_obj.Label = f"{pdm_base_name}_"
        elif comp_type == "R" and "Length" in user_properties:
            core_obj.Label = f"{pdm_base_name}_ | L={user_properties['Length']}mm"
        else:
            core_obj.Label = f"{filename_with_trailing}"


        # 6. ArticleID für die Stückliste (BOM) injizieren
        if not hasattr(core_obj, "ArticleID"):
            core_obj.addProperty("App::PropertyString", "ArticleID", "FCProject", "Eindeutige ID")
        core_obj.ArticleID = filename_with_trailing

        # 7. Dynamische Injektion aller restlichen Eigenschaften aus der JSON
        properties_schema = entity_config.get("Properties", {})
        for prop_name, raw_value in user_properties.items():
            schema = properties_schema.get(prop_name, {})
            prop_type = schema.get("Type", "App::PropertyString")
            prop_cat = schema.get("Category", "FCProject_PDM")
            
            if not hasattr(core_obj, prop_name):
                core_obj.addProperty(prop_type, prop_name, prop_cat, f"PDM: {prop_name}")
            
            try:
                if "Float" in prop_type or "Length" in prop_type:
                    setattr(core_obj, prop_name, float(raw_value))
                else:
                    setattr(core_obj, prop_name, str(raw_value))
            except ValueError:
                pass

        # 8. Physisch speichern und berechnen
        new_doc.saveAs(new_file_path)
        new_doc.recompute()
        return filename_with_trailing
