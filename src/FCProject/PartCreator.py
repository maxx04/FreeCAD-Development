# Macro Version: 3.7.1 - FCProject: PartCreator mit Doppel-Klon und fixierter Label-Zuweisung
import os
import FreeCAD as App

class PartCreator:
    """PDM-Logik für Einzelteile (Typ P). Erzeugt zwei autarke Klone im App::Part-Container."""

    def create(self, file_path, base_name, trailing_name, config, properties):
        bezeichnung_val = properties.get("Bezeichnung", "Standardteil")
        material_target = properties.get("__TargetMaterialName__", "Steel")
        profile_path = properties.get("__LinkedRawProfilePath__", None)

        import PartDesign  # type: ignore
        
        # 1. Neues separates Dokument für das Einzelteil (P) anlegen
        new_doc = App.newDocument(trailing_name)
        App.setActiveDocument(new_doc.Name)

        # 2. Der übergeordnete App::Part-Container wird als Wurzel angelegt
        part_container = new_doc.addObject("App::Part", base_name)
        part_container.Label = trailing_name

        core_obj = None

        # 3. WENN EIN HALBZEUG GEWÄHLT WURDE: Doppelten physischen Klon (Deep Copy) ausführen
        if profile_path and os.path.exists(profile_path):
            try:
                template_doc = App.openDocument(profile_path)
                source_body = None
                
                for obj in template_doc.Objects:
                    if obj.isDerivedFrom("PartDesign::Body") or obj.isDerivedFrom("App::Part"):
                        source_body = obj
                        break
                        
                if source_body:
                    # KLON 1: Reiner Stücklisten-Klon (Vollständig autark, unsichtbar im Container)
                    bom_clone = new_doc.copyObject(source_body, True)
                    bom_clone.Label = f"BOM-Ref: {os.path.basename(profile_path)}"
                    part_container.addObject(bom_clone)
                    
                    if hasattr(bom_clone, "ViewObject") and bom_clone.ViewObject:
                        bom_clone.ViewObject.Visibility = False
                    
                    # KLON 2: Der Bearbeitungs-Klon (Vollständig autark zum Weiterkonstruieren)
                    core_obj = new_doc.copyObject(source_body, True)
                    
                    # KORREKTUR: Niemals das schreibgeschützte .Name beschreiben! Nur das .Label ändern!
                    core_obj.Label = f"Bearbeitung_{base_name}"
                    part_container.addObject(core_obj)
                    
                    # Custom PDM Link-Eigenschaft für die Stückliste am Hauptcontainer sichern
                    if not hasattr(part_container, "BasiertAufHalbzeug"):
                        part_container.addProperty("App::PropertyString", "BasiertAufHalbzeug", "FCProject_PDM", "Rohmaterial-Kopplung")
                    part_container.BasiertAufHalbzeug = os.path.basename(profile_path)
                    
                    App.Console.PrintMessage(f"FCProject: Doppelte Deep-Copy-Klonierung erfolgreich abgeschlossen.\n")
                
                App.closeDocument(template_doc.Name)
            except Exception as e:
                App.Console.PrintWarning(f"FCProject: Fehler beim doppelten Profil-Klonen: {str(e)}\n")

        # 4. FALLBACK: Wenn kein Halbzeug gewählt wurde, leeren Standard-Body anlegen
        if not core_obj:
            core_obj = new_doc.addObject("PartDesign::Body", f"Body_{base_name}")
            core_obj.Label = f"Bearbeitung_{base_name}"
            part_container.addObject(core_obj)

        # 5. Dynamische Material-Synchronisation via setExpression am Haupt-Body
        try:
            if hasattr(core_obj, "ShapeMaterial"):
                from MaterialUtils import get_native_material_by_name
                cpp_material = get_native_material_by_name(material_target)
                if cpp_material:
                    core_obj.ShapeMaterial = cpp_material
                
                if not hasattr(part_container, "MaterialName"):
                    part_container.addProperty("App::PropertyString", "MaterialName", "FCProject_PDM", "Material-Textbezeichnung")
                
                # Expression koppelt das Container-Attribut dynamisch an den aktiven Bearbeitungs-Körper
                part_container.setExpression('MaterialName', f'{core_obj.Name}.ShapeMaterial.Name')
        except Exception as mat_err:
            App.Console.PrintWarning(f"FCProject: Fehler bei Container-Material-Kopplung: {str(mat_err)}\n")

        # 6. PDM Metadaten am Hauptcontainer spritzen
        if not hasattr(part_container, "ArticleID"):
            part_container.addProperty("App::PropertyString", "ArticleID", "FCProject", "Eindeutige ID")
        
        # KORREKTUR: Wir holen die reine PDM-Nummer aus dem Datenpaket!
        # Falls sie fehlt, nutzen wir den trailing_name als sicheren Fallback.
        pure_pdm_id = properties.get("__PureArticleID__", trailing_name)
        part_container.ArticleID = pure_pdm_id
        
        if not hasattr(part_container, "Bezeichnung"):
            part_container.addProperty("App::PropertyString", "Bezeichnung", "FCProject_PDM", "Logische Bauteilbenennung")
        part_container.Bezeichnung = bezeichnung_val

        # 7. Sichern und Berechnen
        new_doc.saveAs(file_path)
        new_doc.recompute()
        App.Console.PrintMessage(f"FCProject: Gekapseltes PDM-Part '{trailing_name}' mit reiner ID erfolgreich generiert.\n")
