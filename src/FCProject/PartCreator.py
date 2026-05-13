# Macro Version: 1.8.1 - FCProject: Bereinigte Labels ohne Präfixe (ASM, RAW, SKEL)
import os
import re
import FreeCAD as App

class PartCreator:
    """Zentrale PDM-Logik für native FreeCAD 1.1 Objekte mit reinen PDM-Labels."""
    
    def __init__(self, project_name, project_dir):
        self.project_name = project_name
        self.project_dir = project_dir

    def get_next_available_number(self):
        """Scannt den Ordner nach Mustern wie 'PROJ-XXXX-*' und gibt die nächste Nummer zurück."""
        highest_num = 0
        if not os.path.exists(self.project_dir):
            return "0001"

        pattern = re.compile(rf"^{re.escape(self.project_name)}-(\d{{4}})-[APRG]")
        
        for filename in os.listdir(self.project_dir):
            match = pattern.match(filename)
            if match:
                num = int(match.group(1))
                if num > highest_num:
                    highest_num = num
                    
        next_num = highest_num + 1
        return f"{next_num:04d}"

    def create_pdm_document(self, comp_type, comp_num):
        """Erstellt eine neue .FCStd-Datei mit reinen, unverfälschten PDM-Labels."""
        filename_base = f"{self.project_name}-{comp_num}-{comp_type}"
        new_file_path = os.path.join(self.project_dir, f"{filename_base}.FCStd")
        
        if os.path.exists(new_file_path):
            raise FileExistsError(f"Die Datei {filename_base}.FCStd existiert bereits!")

        # 1. Neues separates Dokument anlegen und sicher aktivieren
        new_doc = App.newDocument(filename_base)
        App.setActiveDocument(new_doc.Name)
        
        # 2. Die exakten Objekte basierend auf dem Typ erzeugen
        # KORREKTUR: Alle Objekte bekommen das Label 'filename_base' ohne Zusätze!
        if comp_type == "A":
            import UtilsAssembly # type: ignore
            core_obj = new_doc.addObject("Assembly::AssemblyObject", filename_base)
            core_obj.Label = filename_base
            core_obj.Type = "Assembly"
            
        elif comp_type == "G":
            core_obj = new_doc.addObject("App::Part", filename_base)
            core_obj.Label = filename_base
            
        else:
            import PartDesign # type: ignore
            core_obj = new_doc.addObject("PartDesign::Body", filename_base)
            core_obj.Label = filename_base

        # 3. Custom ArticleID für die Stückliste (BOM)
        if not hasattr(core_obj, "ArticleID"):
            core_obj.addProperty("App::PropertyString", "ArticleID", "FCProject", "Eindeutige ID")
        core_obj.ArticleID = filename_base

        # 4. Speichern und berechnen
        new_doc.saveAs(new_file_path)
        new_doc.recompute()
        
        App.Console.PrintMessage(f"FCProject: Komponente '{filename_base}' erfolgreich erstellt.\n")
        return filename_base
