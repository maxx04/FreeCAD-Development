# Macro Version: 2.5.2 - FCProject: Reiner Geometrie-RAWCreator ohne GUI-Einfluss
import os
import FreeCAD as App

class RAWCreator:
    def create(self, file_path, base_name, trailing_name, config, properties):
        length_val = float(properties.get("Length", 500.0))
        profile_template = properties.get("ProfilTyp", "None")

        addon_dir = os.path.dirname(__file__)
        template_file_path = os.path.join(addon_dir, "Profiles", f"{profile_template}.FCStd")

        if not os.path.exists(template_file_path):
            raise FileNotFoundError(f"Die Profilvorlage '{profile_template}.FCStd' wurde nicht gefunden!")

        import PartDesign  # type: ignore
        new_doc = App.newDocument(trailing_name)
        App.setActiveDocument(new_doc.Name)
        
        core_obj = new_doc.addObject(config.get("FreeCADType"), base_name)
        core_obj.Label = f"{trailing_name} | L={length_val}mm"

        # Template laden und Skizze klonen
        template_doc = App.openDocument(template_file_path)
        copied_sketch = None
        for obj in template_doc.Objects:
            if obj.isDerivedFrom("Sketcher::SketchObject"):
                copied_sketch = new_doc.copyObject(obj, False)
                break
        App.closeDocument(template_doc.Name)

        if not copied_sketch:
            raise ValueError(f"Die Vorlage '{profile_template}' enthält keine gültige Skizze!")

        # Extrusion aufbauen
        core_obj.addObject(copied_sketch)
        pad_obj = new_doc.addObject("PartDesign::Pad", f"Pad_{base_name}")
        pad_obj.Profile = copied_sketch
        pad_obj.Length = length_val
        core_obj.addObject(pad_obj)

        # PDM Metadaten spritzen
        core_obj.addProperty("App::PropertyString", "ArticleID", "FCProject").ArticleID = trailing_name
        core_obj.addProperty("App::PropertyLength", "Length", "FCProject_PDM").Length = length_val
        core_obj.addProperty("App::PropertyString", "ProfilTyp", "FCProject_PDM").ProfilTyp = profile_template

        # Datei speichern und Berechnen absichern
        new_doc.saveAs(file_path)
        new_doc.recompute()
