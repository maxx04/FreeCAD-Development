# Macro Version: 3.0.0 - FCProject: PartCreator mit freier Dateiwahl und Material-Kopplung
import os
import FreeCAD as App

class PartCreator:
    """Zentrale PDM-Logik für das Erstellen von Parts basierend auf frei gewählten Halbzeug-Dateien."""

    def create(self, file_path, base_name, trailing_name, config, properties):
        bezeichnung_val = properties.get("Bezeichnung", "Standardteil")
        material_target = properties.get("__TargetMaterialName__", "Steel")
        profile_path = properties.get("__LinkedRawProfilePath__", None) # Der absolute Pfad zur gewählten Datei

        # 1. Neues separates Dokument für das Einzelteil (P) anlegen
        import PartDesign  # type: ignore
        new_doc = App.newDocument(trailing_name)
        App.setActiveDocument(new_doc.Name)

        core_obj = None
        extracted_material = None

        # 2. WENN EIN HALBZEUG GEWÄHLT WURDE: Datei öffnen, Körper klonen & Material extrahieren
        if profile_path and os.path.exists(profile_path):
            try:
                # Die gewählte Datei im Hintergrund öffnen
                template_doc = App.openDocument(profile_path)
                source_body = None
                
                # Wir suchen den ersten vollwertigen geometrischen Körper
                for obj in template_doc.Objects:
                    if obj.isDerivedFrom("PartDesign::Body") or obj.isDerivedFrom("App::Part"):
                        source_body = obj
                        break
                        
                if source_body:
                    # A) Material-Vererbung: Wir greifen das echte C++ Materialobjekt ab, BEVOR wir schließen
                    if hasattr(source_body, "ShapeMaterial") and source_body.ShapeMaterial:
                        extracted_material = source_body.ShapeMaterial
                        # Wenn die Textbezeichnung am Profil existiert, übernehmen wir sie als Namen
                        if hasattr(source_body, "MaterialName"):
                            material_target = source_body.MaterialName
                    
                    # B) Deep-Copy des gesamten 3D-Körpers in das neue Dokument
                    core_obj = new_doc.copyObject(source_body, True)
                    
                    # Den geklonen Körper auf das neue PDM-Muster umbenennen
                    core_obj.Name = base_name
                    core_obj.Label = trailing_name
                    
                    # Verknüpfungspfad zur Dokumentation in den Parametertree schreiben
                    if not hasattr(core_obj, "BasiertAufHalbzeug"):
                        core_obj.addProperty("App::PropertyString", "BasiertAufHalbzeug", "FCProject_PDM", "Rohmaterial-Pfad")
                    core_obj.BasiertAufHalbzeug = os.path.basename(profile_path)
                    
                    App.Console.PrintMessage(f"FCProject: 3D-Körper aus '{os.path.basename(profile_path)}' erfolgreich geklont.\n")
                
                # Vorlage im Hintergrund sauber schließen, um RAM freizugeben
                App.closeDocument(template_doc.Name)
            except Exception as e:
                App.Console.PrintWarning(f"FCProject: Fehler beim Klonen der ausgewählten Datei: {str(e)}\n")

        # 3. FALLBACK: Wenn kein Halbzeug gewählt wurde, leeren Körper anlegen
        if not core_obj:
            core_obj = new_doc.addObject(config.get("FreeCADType", "PartDesign::Body"), base_name)
            core_obj.Label = trailing_name

        # 4. TYPKONFORMES MATERIAL-BINDING MIT AUTOMATISCHER VERERBUNG
        # 4. KORREKTUR: Dynamische Material-Synchronisation via setExpression (.ShapeMaterial.Name)
        try:
            if hasattr(core_obj, "ShapeMaterial"):
                if extracted_material:
                    # Wenn wir aus einem Halbzeug klonen, kopieren wir das C++ Objekt
                    core_obj.ShapeMaterial = extracted_material
                    App.Console.PrintMessage(f"FCProject: Werkstoff erfolgreich vom Basis-Halbzeug geerbt.\n")
                else:
                    # Andernfalls nutzen wir unsere UUID-Suchmaschine
                    from MaterialUtils import get_native_material_by_name
                    cpp_material = get_native_material_by_name(material_target)
                    if cpp_material:
                        core_obj.ShapeMaterial = cpp_material
                
                # PDM-Metadaten-String anlegen, falls noch nicht vorhanden
                if not hasattr(core_obj, "MaterialName"):
                    core_obj.addProperty("App::PropertyString", "MaterialName", "FCProject_PDM", "Material-Textbezeichnung")
                
                # TRICK: Wir schreiben keinen statischen Text, sondern eine C++ Expression!
                # Das koppelt die PDM-Eigenschaft 'MaterialName' permanent an das native 'ShapeMaterial.Name'
                core_obj.setExpression('MaterialName', 'ShapeMaterial.Name')
                App.Console.PrintMessage("FCProject: PDM-MaterialName erfolgreich dynamisch an ShapeMaterial.Name gekoppelt.\n")
                
        except Exception as mat_err:
            App.Console.PrintWarning(f"FCProject: Fehler bei Material-Expression-Kopplung: {str(mat_err)}\n")


        # 5. PDM Metadaten spritzen
        if not hasattr(core_obj, "ArticleID"):
            core_obj.addProperty("App::PropertyString", "ArticleID", "FCProject", "Eindeutige ID")
        core_obj.ArticleID = trailing_name
        
        if not hasattr(core_obj, "Bezeichnung"):
            core_obj.addProperty("App::PropertyString", "Bezeichnung", "FCProject_PDM", "Logische Bauteilbenennung")
        core_obj.Bezeichnung = bezeichnung_val

        # 6. Sichern und Berechnen
        new_doc.saveAs(file_path)
        new_doc.recompute()
