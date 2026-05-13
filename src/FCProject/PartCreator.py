# Macro Version: 1.7.8 - FCProject: Native Assembly & Document Name Fix
import os
import FreeCAD as App

class PartCreator:
    """Zentrale PDM-Logik für das Erstellen von nativen FreeCAD 1.1 Objekten."""
    
    def __init__(self, project_name, project_dir):
        self.project_name = project_name
        self.project_dir = project_dir

    def create_pdm_document(self, comp_type, comp_num):
        """Erstellt eine neue .FCStd-Datei mit den exakten FreeCAD 1.1 Core-Objekten."""
        filename_base = f"{self.project_name}-{comp_num}-{comp_type}"
        new_file_path = os.path.join(self.project_dir, f"{filename_base}.FCStd")
        
        if os.path.exists(new_file_path):
            raise FileExistsError(f"Die Datei {filename_base}.FCStd existiert bereits!")

        # 1. Neues separates Dokument anlegen und sicher aktivieren
        new_doc = App.newDocument(filename_base)
        App.setActiveDocument(new_doc.Name)  # <-- FIX: Nutzt den verifizierten Namen
        
        # 2. Die exakten Objekte basierend auf dem Typ erzeugen
        if comp_type == "A":
            import UtilsAssembly  # type: ignore
            
            # Erzeugt das echte Assembly-Wurzelobjekt
            core_obj = new_doc.addObject("Assembly::AssemblyObject", filename_base)
            core_obj.Label = f"ASM_{filename_base}"
            core_obj.Type = "Assembly"
            
            # Fügt die standardmäßige Gelenk-Gruppe hinzu
            new_doc.addObject("Assembly::JointGroup", "Joints")
            
        elif comp_type == "G":
            core_obj = new_doc.addObject("App::Part", filename_base)
            core_obj.Label = f"SKEL_{filename_base}"
            
        else:
            import PartDesign  # type: ignore
            
            core_obj = new_doc.addObject("PartDesign::Body", filename_base)
            core_obj.Label = f"BODY_{filename_base}" if comp_type == "P" else f"RAW_{filename_base}"

        # 3. Custom ArticleID zur Sicherheit für die spätere BOM behalten
        if not hasattr(core_obj, "ArticleID"):
            core_obj.addProperty("App::PropertyString", "ArticleID", "FCProject", "Eindeutige ID")
        core_obj.ArticleID = filename_base

        # 4. Speichern und berechnen
        new_doc.saveAs(new_file_path)
        new_doc.recompute()
        
        App.Console.PrintMessage(f"FCProject: {comp_type}-Komponente erfolgreich als natives 1.1-Objekt erstellt.\n")
        return filename_base
