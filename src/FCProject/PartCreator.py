# Macro Version: 3.3.2 - FCProject: PartCreator mit expliziter PartDesign Module-Initialisierung
import os
import FreeCAD as App

class PartCreator:
    """PDM-Logik für Einzelteile (Typ P). Initialisiert PartDesign vor der Injektion."""

    def create(self, file_path, base_name, trailing_name, config, properties):
        bezeichnung_val = properties.get("Bezeichnung", "Standardteil")
        material_target = properties.get("__TargetMaterialName__", "Steel")
        profile_path = properties.get("__LinkedRawProfilePath__", None)

        # 1. ZWINGEND: Das PartDesign-Modul importieren, um die C++ Typen im Kern zu registrieren!
        import PartDesign  # type: ignore
        
        # 2. Neues separates Dokument für das Einzelteil (P) anlegen
        new_doc = App.newDocument(trailing_name)
        App.setActiveDocument(new_doc.Name)

        # 3. Das primäre Zielobjekt anlegen (Jetzt kennt der Kern den Typ garantiert!)
        core_obj = new_doc.addObject("PartDesign::Body", base_name)
        core_obj.Label = trailing_name

        # 4. WENN EIN HALBZEUG GEWÄHLT WURDE: Sicherer Klon-Mechanismus
        if profile_path and os.path.exists(profile_path):
            try:
                template_doc = App.openDocument(profile_path)
                source_body = None
                
                for obj in template_doc.Objects:
                    if obj.isDerivedFrom("PartDesign::Body") or obj.isDerivedFrom("App::Part"):
                        source_body = obj
                        break
                        
                if source_body:
                    # Vollständiger Klon als lokaler Speicher-Anker
                    local_geometry_anchor = new_doc.copyObject(source_body, True)
                    local_geometry_anchor.Label = f"Stücklisten-Referenz: {os.path.basename(profile_path)}"
                    
                    if hasattr(local_geometry_anchor, "ViewObject") and local_geometry_anchor.ViewObject:
                        local_geometry_anchor.ViewObject.Visibility = False
                    
                    if hasattr(local_geometry_anchor, "Shape") and local_geometry_anchor.Shape:
                        # Durch den Import oben fliegt hier kein 'not a document object type' Fehler mehr!
                        base_feature = new_doc.addObject("PartDesign::BaseFeature", f"Rohling_{base_name}")
                        base_feature.Label = f"Rohling: {os.path.basename(profile_path)}"
                        
                        base_feature.Shape = local_geometry_anchor.Shape
                        core_obj.addObject(base_feature)
                        App.Console.PrintMessage(f"FCProject: C++ Festkörper erfolgreich als BaseFeature injiziert.\n")
                    
                    if not hasattr(core_obj, "BasiertAufHalbzeug"):
                        core_obj.addProperty("App::PropertyString", "BasiertAufHalbzeug", "FCProject_PDM", "Rohmaterial-Kopplung")
                    core_obj.BasiertAufHalbzeug = os.path.basename(profile_path)
                
                App.closeDocument(template_doc.Name)
            except Exception as e:
                App.Console.PrintWarning(f"FCProject: Fehler bei BaseFeature-Injektion: {str(e)}\n")

        # 5. Dynamische Material-Synchronisation via setExpression
        try:
            if hasattr(core_obj, "ShapeMaterial"):
                from MaterialUtils import get_native_material_by_name
                cpp_material = get_native_material_by_name(material_target)
                if cpp_material:
                    core_obj.ShapeMaterial = cpp_material
                
                if not hasattr(core_obj, "MaterialName"):
                    core_obj.addProperty("App::PropertyString", "MaterialName", "FCProject_PDM", "Material-Textbezeichnung")
                
                core_obj.setExpression('MaterialName', 'ShapeMaterial.Name')
        except Exception as mat_err:
            App.Console.PrintWarning(f"FCProject: Fehler bei Material-Kopplung: {str(mat_err)}\n")

        # 6. PDM Metadaten spritzen
        if not hasattr(core_obj, "ArticleID"):
            core_obj.addProperty("App::PropertyString", "ArticleID", "FCProject", "Eindeutige ID")
        core_obj.ArticleID = trailing_name
        
        if not hasattr(core_obj, "Bezeichnung"):
            core_obj.addProperty("App::PropertyString", "Bezeichnung", "FCProject_PDM", "Logische Bauteilbenennung")
        core_obj.Bezeichnung = bezeichnung_val

        # 7. Sichern und Berechnen
        new_doc.saveAs(file_path)
        new_doc.recompute()
