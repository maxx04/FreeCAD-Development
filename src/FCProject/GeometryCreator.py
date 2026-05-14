# Macro Version: 2.0.0 - FCProject: Spezialisierter GeometryCreator (Typ G)
import FreeCAD as App

class GeometryCreator:
    def create(self, file_path, base_name, trailing_name, config, properties):
        new_doc = App.newDocument(trailing_name)
        App.setActiveDocument(new_doc.Name)
        
        # Skelette nutzen App::Part als Geometrie-Referenz-Container
        core_obj = new_doc.addObject(config.get("FreeCADType"), base_name)
        core_obj.Label = trailing_name
        
        core_obj.addProperty("App::PropertyString", "ArticleID", "FCProject").ArticleID = trailing_name
        
        new_doc.saveAs(file_path)
        new_doc.recompute()
