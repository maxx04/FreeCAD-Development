# In deiner EntityCreator.py
import os
import re

class EntityCreator:
    """Zentrale PDM-Fabrik, die Anfragen an spezialisierte Creatoren verteilt."""
    
    def __init__(self, project_name, project_dir):
        # KORREKTUR: Zwingenden String-Fallback sicherstellen, falls project_name None ist
        self.project_name = project_name if project_name else "PROJ"
        self.project_dir = project_dir if project_dir else os.getcwd()
        self.config_data = self._load_config()

    def _load_config(self):
        """Lädt die JSON Konfigurationsdatei mit integrierter Absturzsicherung."""
        import json
        if not self.project_dir:
            return {}
        
        # Sicherstellen, dass wir im korrekten PROJ_X Ordner suchen
        folder_name = os.path.basename(self.project_dir)
        json_path = os.path.join(self.project_dir, f"{folder_name}.json")
        
        if os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def get_next_available_number(self):
        """Scannt den Ordner nach Mustern wie 'PROJ_XXXX_*' und gibt die nächste Nummer zurück."""
        highest_num = 0
        if not self.project_dir or not os.path.exists(self.project_dir): 
            return "0001"

        # KORREKTUR: Escapesicherer Schutz, falls project_name ungültige Zeichen enthält
        clean_proj_name = str(self.project_name)
        pattern = re.compile(rf"^{re.escape(clean_proj_name)}_(\d{{4}})_[APRGB]")
        
        try:
            for filename in os.listdir(self.project_dir):
                match = pattern.match(filename)
                if match:
                    num = int(match.group(1))
                    if num > highest_num: 
                        highest_num = num
        except Exception as e:
            import FreeCAD as App
            App.Console.PrintWarning(f"FCProject: Fehler beim Ordner-Scan für Auto-Nummer: {str(e)}\n")
                    
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
         # In deiner EntityCreator.py -> Methode create_pdm_document:
        
        entity_config = self.config_data.get("Entities", {}).get(comp_type, {})
        
        # 2. STRATEGY-DELEGATION: Modernes, sauberes match-case statt if-elif-Wüste
        match comp_type:
            case "P":
                from PartCreator import PartCreator
                creator = PartCreator()
            case "A":
                from AssemblyCreator import AssemblyCreator
                creator = AssemblyCreator()
            case "G":
                from GeometryCreator import GeometryCreator
                creator = GeometryCreator()
            case "R":
                from RAWCreator import RAWCreator
                creator = RAWCreator()
            case "B":
                from PurchasedPartCreator import PurchasedPartCreator
                creator = PurchasedPartCreator()
            case _:
                raise ValueError(f"Unbekannter PDM-Komponenten-Typ: {comp_type}")

        # 3. Den spezialisierten Creator ausführen
        creator.create(new_file_path, pdm_base_name, filename_with_trailing, entity_config, user_properties)
        
        return filename_with_trailing
