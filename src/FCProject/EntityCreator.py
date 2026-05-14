# Macro Version: 2.0.0 - FCProject: EntityCreator Fabrik-Modul
import os
import re

class EntityCreator:
    """Zentrale PDM-Fabrik, die Anfragen an spezialisierte Creatoren verteilt."""
    
    def __init__(self, project_name, project_dir):
        self.project_name = project_name
        self.project_dir = project_dir
        self.config_data = self._load_config()

    def _load_config(self):
        """Lädt die JSON Konfigurationsdatei mit integrierter Absturzsicherung."""
        import json
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
        """Generiert den Basisnamen und delegiert die Erstellung an die Ziel-Klasse."""
        # 1. Suffix-Bezeichnung bestimmen
        bezeichnung_suffix = ""
        if comp_type in ["P", "A"] and "Bezeichnung" in user_properties and user_properties["Bezeichnung"]:
            bezeichnung_suffix = f"_{user_properties['Bezeichnung']}"
        elif comp_type == "R" and "ProfilTyp" in user_properties and user_properties["ProfilTyp"]:
            bezeichnung_suffix = f"_{user_properties['ProfilTyp']}"

        pdm_base_name = f"{self.project_name}_{comp_num}_{comp_type}{bezeichnung_suffix}"
        filename_with_trailing = f"{pdm_base_name}_"
        new_file_path = os.path.join(self.project_dir, f"{filename_with_trailing}.FCStd")
        
        if os.path.exists(new_file_path):
            raise FileExistsError(f"Die Datei {filename_with_trailing}.FCStd existiert bereits!")

        entity_config = self.config_data.get("Entities", {}).get(comp_type, {})
        
        # 2. STRATEGY-DELEGATION: Dynamischer Import des spezialisierten Creators
        if comp_type == "P":
            from PartCreator import PartCreator
            creator = PartCreator()
        elif comp_type == "A":
            from AssemblyCreator import AssemblyCreator
            creator = AssemblyCreator()
        elif comp_type == "G":
            from GeometryCreator import GeometryCreator
            creator = GeometryCreator()
        elif comp_type == "R":
            from RAWCreator import RAWCreator
            creator = RAWCreator()
        else:
            raise ValueError(f"Unbekannter Komponenten-Typ: {comp_type}")

        # 3. Den spezialisierten Creator die Datei und das Objekt bauen lassen
        creator.create(new_file_path, pdm_base_name, filename_with_trailing, entity_config, user_properties)
        
        return filename_with_trailing
