#FCProject: PartCreator mit sauber getrenntem Standard-Fallback
import os
import Utils
import FreeCAD as App


class PartCreator:
    """PDM-Logik für Einzelteile (Typ P). Unterstützt Klonierung und leere Standard-Erstellung."""

    def create(self, file_path, base_name, trailing_name, config, properties):
        bezeichnung_val = properties.get("Bezeichnung", "Standardteil")
        material_target = properties.get("__TargetMaterialName__", "Steel")
        try:
            price_val = float(properties.get("Preis", 0.0))
        except (ValueError, TypeError):
            App.Console.PrintWarning("FCProject: Ungültiger Preis-Wert. Verwende Standardwert 0.0.\n")
            price_val = 0.0
        
        # Der absolute Pfad zur gewählten Halbzeug-Datei (wird nur gesetzt, wenn im Dialog 'Ja' geklickt wurde)
        profile_path = properties.get("__LinkedRawProfilePath__", None)

        import PartDesign  # type: ignore
        
        # 1. Neues separates Dokument für das Einzelteil (P) anlegen
        new_doc = App.newDocument(trailing_name)
        App.setActiveDocument(new_doc.Name)

        # 2. Der übergeordnete App::Part-Container wird als Wurzel angelegt
        part_container = new_doc.addObject("App::Part", base_name)
        part_container.Label = trailing_name

        core_obj = None

        # 3. STRATEGIE-WEICHE: Nur klonen, wenn wir WIRKLICH einen gültigen Pfad vom Dateidialog haben!
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
                    core_obj.Label = f"Bearbeitung_{base_name}"
                    part_container.addObject(core_obj)
                    
                    # Custom PDM Link-Eigenschaft für die Stückliste am Hauptcontainer sichern
                    if not hasattr(part_container, "BasiertAufHalbzeug"):
                        part_container.addProperty("App::PropertyString", "BasiertAufHalbzeug", "FCProject_PDM", "Rohmaterial-Kopplung")
                    part_container.BasiertAufHalbzeug = os.path.basename(profile_path)
                    
                    App.Console.PrintMessage(f"FCProject: Doppel-Klon für Halbzeug erfolgreich durchgeführt.\n")
                
                App.closeDocument(template_doc.Name)
            except Exception as e:
                App.Console.PrintWarning(f"FCProject: Fehler beim Profil-Klonen: {str(e)}\n")

        # 4. DAS IST DIE KORREKTUR: Wenn KEIN Halbzeug ausgewählt wurde (Klassischer, leerer Body)
        if not core_obj:
            # Wir erzeugen einen komplett leeren, nativen PartDesign::Body im Container
            core_obj = new_doc.addObject("PartDesign::Body", f"Body_{base_name}")
            core_obj.Label = f"Bearbeitung_{base_name}"
            part_container.addObject(core_obj)
            
            # Da es kein Halbzeug gibt, setzen wir das PDM-Attribut auf den Standard-Strich
            if not hasattr(part_container, "BasiertAufHalbzeug"):
                part_container.addProperty("App::PropertyString", "BasiertAufHalbzeug", "FCProject_PDM", "Rohmaterial-Kopplung")
            part_container.BasiertAufHalbzeug = "-"
            
            App.Console.PrintMessage("FCProject: Normales, leeres Einzelteil ohne Halbzeug-Basis erfolgreich initialisiert.\n")

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

        # 6. PDM Metadaten am Hauptcontainer spritzen (Mit der reinen ArtikelID)
        pure_id = properties.get("__PureArticleID__", trailing_name)
        
        Utils._ensure_property(App, part_container, "App::PropertyString", "ArticleID", "FCProject", "Eindeutige ID", pure_id)
        Utils._ensure_property(App, part_container, "App::PropertyString", "Bezeichnung", "FCProject_PDM", "Logische Bauteilbenennung", bezeichnung_val)
        Utils._ensure_property(App, part_container, "App::PropertyFloat", "Preis", "FCProject_PDM", "Preis für das Halbzeug", price_val)

        # 7. Sichern und Berechnen
        new_doc.saveAs(file_path)
        new_doc.recompute()
