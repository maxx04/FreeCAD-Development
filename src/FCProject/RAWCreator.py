# Macro Version: 2.0.0 - FCProject: Spezialisierter RAWCreator (Typ R)
import FreeCAD as App
import PartDesign # type: ignore

class RAWCreator:
    def create(self, file_path, base_name, trailing_name, config, properties):
        new_doc = App.newDocument(trailing_name)
        App.setActiveDocument(new_doc.Name)
        
        core_obj = new_doc.addObject(config.get("FreeCADType"), base_name)
        
        # Hier nutzen wir deine zusammengesetzte Label-Optik für Halbzeuge
        length_str = properties.get("Length", "0")
        core_obj.Label = f"{trailing_name} | L={length_str}mm"
        
        core_obj.addProperty("App::PropertyString", "ArticleID", "FCProject").ArticleID = trailing_name
        
        # Typsicheres Injizieren der geometrischen PDM-Eigenschaften
        if "Length" in properties:
            core_obj.addProperty("App::PropertyLength", "Length", "FCProject_PDM").Length = float(properties["Length"])
        if "ProfilTyp" in properties:
            core_obj.addProperty("App::PropertyString", "ProfilTyp", "FCProject_PDM").ProfilTyp = properties["ProfilTyp"]
            
        new_doc.saveAs(file_path)
        new_doc.recompute()
