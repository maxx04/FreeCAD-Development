# Macro Version: 3.2.0 - FCProject: Spezialisierter PurchasedPartCreator (Typ B)
import os
import FreeCAD as App

class PurchasedPartCreator:
    """PDM-Logik für Kaufteile (Typ B). Integriert CAD-Imports als Basis-Komponente."""

    def create(self, file_path, base_name, trailing_name, config, properties):
        bezeichnung_val = properties.get("Bezeichnung", "Kaufteil")
        hersteller_val = properties.get("Hersteller", "TraceParts")
        bestell_val = properties.get("Bestellnummer", "000-000")
        material_target = properties.get("__TargetMaterialName__", "Steel")
        profile_path = properties.get("__LinkedRawProfilePath__", None) # Optional gewählte Basis-Datei

        new_doc = App.newDocument(trailing_name)
        App.setActiveDocument(new_doc.Name)
        
        # Kaufteile nutzen App::Part als sauberen Container
        core_obj = new_doc.addObject(config.get("FreeCADType", "App::Part"), base_name)
        core_obj.Label = trailing_name

        # Falls ein Basis-Kaufteil (z.B. ein roher Zylinder-Rohling) geladen werden soll
        if profile_path and os.path.exists(profile_path):
            try:
                template_doc = App.openDocument(profile_path)
                for obj in template_doc.Objects:
                    if obj.isDerivedFrom("PartDesign::Body") or obj.isDerivedFrom("App::Part"):
                        cloned_obj = new_doc.copyObject(obj, True)
                        core_obj.addObject(cloned_obj) # In den App::Part Container schieben
                        break
                App.closeDocument(template_doc.Name)
            except Exception as e:
                App.Console.PrintWarning(f"FCProject: Fehler bei Kaufteil-Klonierung: {str(e)}\n")

        # Material-Expression setzen
        try:
            if hasattr(core_obj, "ShapeMaterial"):
                from FCProject.MaterialUtils import get_native_material_by_name
                cpp_material = get_native_material_by_name(material_target)
                if cpp_material:
                    core_obj.ShapeMaterial = cpp_material
                if not hasattr(core_obj, "MaterialName"):
                    core_obj.addProperty("App::PropertyString", "MaterialName", "FCProject_PDM", "Material-Textbezeichnung")
                core_obj.setExpression('MaterialName', 'ShapeMaterial.Name')
        except Exception as mat_err:
            App.Console.PrintWarning(f"FCProject: Fehler bei Material-Kopplung im Kaufteil: {str(mat_err)}\n")

        # Metadaten spritzen
        # In deiner PurchasedPartCreator.py -> Ganz unten beim Metadaten-Spritzen:

        # Wir holen uns die reine, saubere PDM-ID aus dem Fabrik-Paket
        pure_id = properties.get("__PureArticleID__", trailing_name)

        if not hasattr(core_obj, "ArticleID"):
            core_obj.addProperty("App::PropertyString", "ArticleID", "FCProject", "Eindeutige ID")
        
        # KORREKTUR: Jetzt schreiben wir auch hier NUR die reine ID (z.B. U20_0001_B_) rein!
        core_obj.ArticleID = pure_id
        
        if not hasattr(core_obj, "Bezeichnung"):
            core_obj.addProperty("App::PropertyString", "Bezeichnung", "FCProject_PDM", "Logische Benennung")
        core_obj.Bezeichnung = bezeichnung_val


        new_doc.saveAs(file_path)
        new_doc.recompute()
