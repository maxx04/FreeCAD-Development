import os
import FreeCAD as App
import Utils

class RAWCreator:
    """Zentrale PDM-Logik für das Erstellen von Halbzeugen (Profilen) aus Vorlagen."""

    def create(self, file_path, base_name, trailing_name, config, properties):
        # 1. Parameter aus dem Datenpaket extrahieren
        length_val = float(properties.get("Length", 500.0))
        profile_template = properties.get("ProfilTyp", "None")
        material_target = properties.get("__TargetMaterialName__", "Aluminum")

        try:
            price_val = float(properties.get("Preis", 0.0))
        except (ValueError, TypeError):
            App.Console.PrintWarning("FCProject: Ungültiger Preis-Wert. Verwende Standardwert 0.0.\n")
            price_val = 0.0

        # Die reine, isolierte PDM-ID für das ERP-System holen (z.B. U20_0005_R_)
        pure_id = properties.get("__PureArticleID__", trailing_name)

        # 2. Absoluten Pfad zur Master-Skizzen-Vorlage ermitteln
        #TODO Kaufteile Verzeichnis mit passenden Vorlagen für z.B. Schrauben, Muttern, etc. anlegen
        common_dir = os.path.join(os.path.dirname(file_path), "..", "_Common_Resources")
        template_file_path = os.path.join(common_dir, "Profiles", f"{profile_template}.FCStd")

        if not os.path.exists(template_file_path):
            raise FileNotFoundError(
                f"Die Profilvorlage '{profile_template}.FCStd' wurde nicht gefunden!\n"
                f"Bitte lege die Datei im Ordner: '{os.path.join(common_dir, 'Profiles')}' ab."
            )

        # 3. Neues separates Dokument anlegen und im RAM aktivieren
        import PartDesign  # type: ignore
        new_doc = App.newDocument(trailing_name)
        App.setActiveDocument(new_doc.Name)
        
        # Den geometrischen Hauptkörper (Body) erzeugen
        core_obj = new_doc.addObject(config.get("FreeCADType", "PartDesign::Body"), base_name)
        core_obj.Label = f"{trailing_name} | L={length_val}mm"

        # 4. TEMPLATE-SKIZZE KLONEN (Mit striktem RAM-Schutz)
        template_doc = App.openDocument(template_file_path)
        copied_sketch = None
        for obj in template_doc.Objects:
            if obj.isDerivedFrom("Sketcher::SketchObject"):
                copied_sketch = new_doc.copyObject(obj, False)
                break
        App.closeDocument(template_doc.Name)

        if not copied_sketch:
            raise ValueError(f"Die Vorlage '{profile_template}' enthält keine gültige Skizze!")

        # 5. Geometrie im neuen Body zusammensetzen und extrudieren (Pad)
        core_obj.addObject(copied_sketch)
        pad_obj = new_doc.addObject("PartDesign::Pad", f"Pad_{base_name}")
        pad_obj.Profile = copied_sketch
        pad_obj.Length = length_val
        core_obj.addObject(pad_obj)

        # 6. TYPKONFORMES MATERIAL-BINDING MIT EXPRESSION-KOPPLUNG
        try:
            if hasattr(core_obj, "ShapeMaterial"):
                from MaterialUtils import get_native_material_by_name
                cpp_material = get_native_material_by_name(material_target)
                if cpp_material:
                    core_obj.ShapeMaterial = cpp_material
                
                if not hasattr(core_obj, "MaterialName"):
                    core_obj.addProperty("App::PropertyString", "MaterialName", "FCProject_PDM", "Material-Textbezeichnung")
                
                # Expression koppelt das Feld permanent an den C++ Kern für synchrone Updates im Baum
                core_obj.setExpression('MaterialName', 'ShapeMaterial.Name')
        except Exception as mat_err:
            App.Console.PrintWarning(f"FCProject: Fehler bei der Material-Speicherung im RAW-Körper: {str(mat_err)}\n")

        # 7. REINE PDM-METADATEN AM HALBZEUG SPEICHERN
        if not hasattr(core_obj, "ArticleID"):
            core_obj.addProperty("App::PropertyString", "ArticleID", "FCProject", "Eindeutige ID")
            
        # KORREKTUR: Es wird NUR noch die saubere, textfreie ID eingepflegt (z.B. U20_0005_R_)!
        core_obj.ArticleID = pure_id
        
        #core_obj.addProperty("App::PropertyLength", "Length", "FCProject_PDM", "Zuschnittslänge").Length = length_val
        Utils._ensure_property(App, core_obj, "App::PropertyLength", "Length", "FCProject_PDM", "Zuschnittslänge", length_val)
        #core_obj.addProperty("App::PropertyString", "ProfilTyp", "FCProject_PDM", "Verwendetes Vorlagenprofil").ProfilTyp = profile_template
        Utils._ensure_property(App, core_obj, "App::PropertyString", "ProfilTyp", "FCProject_PDM", "Verwendetes Vorlagenprofil", profile_template)

        Utils._ensure_property(App, core_obj, "App::PropertyFloat", "Preis", "FCProject_PDM", "Preis für das Halbzeug", price_val)

        # 8. Datei final auf der Festplatte sichern
        new_doc.saveAs(file_path)
        new_doc.recompute()
        
        App.Console.PrintMessage(f"FCProject: RAW-Halbzeug '{trailing_name}' erfolgreich mit reiner ID generiert.\n")
