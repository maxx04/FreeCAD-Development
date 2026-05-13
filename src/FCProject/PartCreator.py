# Macro Version: 1.6.0 - FCProject: Reines PDM Logik-Modul (Ohne Qt)
import os
import FreeCAD as App
import FreeCADGui as Gui

class PartCreator:
    """Zentrale PDM-Logik für das Erstellen von strukturierten CAD-Dokumenten."""
    
    def __init__(self, project_name, project_dir):
        self.project_name = project_name
        self.project_dir = project_dir

    def create_pdm_document(self, comp_type, comp_num):
        """Erstellt eine neue .FCStd-Datei nach dem PDM-Nummernschlüssel."""
        # 1. Namen nach Schema bauen: Projekt-Teilnummer-Typ
        filename_base = f"{self.project_name}-{comp_num}-{comp_type}"
        new_file_path = os.path.join(self.project_dir, f"{filename_base}.FCStd")
        
        # Sicherheitsprüfung
        if os.path.exists(new_file_path):
            raise FileExistsError(f"Die Datei {filename_base}.FCStd existiert bereits!")

        # 2. Neues separates Dokument anlegen
        new_doc = App.newDocument(filename_base)
        
        # 3. Das entsprechende Core-Objekt basierend auf dem Typ erzeugen
        if comp_type == "A":
            core_obj = new_doc.addObject("App::Part", "AssemblyContainer")
            core_obj.Label = f"ASM_{filename_base}"
        elif comp_type == "G":
            core_obj = new_doc.addObject("App::Part", "GeometrySkelett")
            core_obj.Label = f"SKEL_{filename_base}"
        else:
            # Für Einzelteile (P) und Halbzeuge (R)
            core_obj = new_doc.addObject("App::Part", "PartContainer")
            core_obj.Label = f"PART_{filename_base}"

        # 4. Custom ArticleID zur Sicherheit für die spätere BOM behalten
        if not hasattr(core_obj, "ArticleID"):
            core_obj.addProperty("App::PropertyString", "ArticleID", "FCProject", "Eindeutige ID")
        core_obj.ArticleID = filename_base

        # 5. Dokument physisch speichern und berechnen
        new_doc.saveAs(new_file_path)
        new_doc.recompute()
        
        App.Console.PrintMessage(f"PDM SUCCESS: Datei '{new_file_path}' generiert.\n")
        return filename_base
