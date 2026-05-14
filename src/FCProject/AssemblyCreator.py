# Macro Version: 2.0.0 - FCProject: Spezialisierter AssemblyCreator (Typ A)
import FreeCAD as App
import UtilsAssembly # type: ignore

class AssemblyCreator:
    def create(self, file_path, base_name, trailing_name, config, properties):
        new_doc = App.newDocument(trailing_name)
        App.setActiveDocument(new_doc.Name)
        
        # Erzeugt das echte AssemblyObject und die implizite JointGroup
        core_obj = new_doc.addObject(config.get("FreeCADType"), base_name)
        new_doc.addObject("Assembly::JointGroup", "Joints")
        
        core_obj.Label = trailing_name
        core_obj.Type = "Assembly"
        
        core_obj.addProperty("App::PropertyString", "ArticleID", "FCProject").ArticleID = trailing_name
        
        if "Bezeichnung" in properties:
            core_obj.addProperty("App::PropertyString", "Bezeichnung", "FCProject_PDM").Bezeichnung = properties["Bezeichnung"]
            
        new_doc.saveAs(file_path)
        new_doc.recompute()
