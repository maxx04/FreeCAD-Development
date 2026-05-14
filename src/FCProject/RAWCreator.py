# Macro Version: 2.6.2 - FCProject: Spezialisierter RAWCreator mit nativer .ShapeMaterial-Speicherung
import os
import FreeCAD as App

class RAWCreator:
    """Zentrale PDM-Logik für das Erstellen von Halbzeugen (Profilen) aus Vorlagen."""

    def create(self, file_path, base_name, trailing_name, config, properties):
        # 1. Parameter aus dem Datenpaket extrahieren
        length_val = float(properties.get("Length", 500.0))
        profile_template = properties.get("ProfilTyp", "None")
        material_target = properties.get("__TargetMaterialName__", "Aluminum")

        # 2. Absoluten Pfad zur Master-Skizzen-Vorlage ermitteln
        addon_dir = os.path.dirname(__file__)
        template_file_path = os.path.join(addon_dir, "Profiles", f"{profile_template}.FCStd")

        if not os.path.exists(template_file_path):
            raise FileNotFoundError(
                f"Die Profilvorlage '{profile_template}.FCStd' wurde nicht gefunden!\n"
                f"Bitte lege die Datei im Ordner: '{os.path.join(addon_dir, 'Profiles')}' ab."
            )

        # 3. Neues separates Dokument anlegen und im RAM aktivieren
        import PartDesign  # type: ignore
        new_doc = App.newDocument(trailing_name)
        App.setActiveDocument(new_doc.Name)
        
        # Den geometrischen Hauptkörper (Body) erzeugen
        core_obj = new_doc.addObject(config.get("FreeCADType"), base_name)
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

         # 6. TYPKONFORMES MATERIAL-BINDING ÜBER CORE UUID UTILS
        try:
            material_target = properties.get("__TargetMaterialName__", "Aluminum")
            
            if hasattr(core_obj, "ShapeMaterial"):
                from MaterialUtils import get_native_material_by_name
                # Das C++ Objekt über die UUID-Schnittstelle laden
                cpp_material = get_native_material_by_name(material_target)
                
                if cpp_material:
                    # Direkte Zuweisung an das Profil
                    core_obj.ShapeMaterial = cpp_material
                    
                    if not hasattr(core_obj, "MaterialName"):
                        core_obj.addProperty("App::PropertyString", "MaterialName", "FCProject_PDM", "Material-Textbezeichnung")
                    core_obj.MaterialName = material_target
                    App.Console.PrintMessage(f"FCProject: Material '{material_target}' erfolgreich via UUID-Objekt im RAW-Körper eingebrannt.\n")
            else:
                App.Console.PrintWarning("FCProject Warnung: Der RAW-Körper besitzt kein .ShapeMaterial Attribut!\n")
        except Exception as mat_err:
            App.Console.PrintWarning(f"FCProject: Fehler bei UUID-Material-Speicherung im RAW-Körper: {str(mat_err)}\n")

        # 7. Reine PDM-Metadaten in den Parametertree spritzen
        if not hasattr(core_obj, "ArticleID"):
            core_obj.addProperty("App::PropertyString", "ArticleID", "FCProject", "Eindeutige ID")
        core_obj.ArticleID = trailing_name
        
        core_obj.addProperty("App::PropertyLength", "Length", "FCProject_PDM", "Zuschnittslänge").Length = length_val
        core_obj.addProperty("App::PropertyString", "ProfilTyp", "FCProject_PDM", "Verwendetes Vorlagenprofil").ProfilTyp = profile_template

        # 8. Datei final auf der Festplatte sichern
        new_doc.saveAs(file_path)
        new_doc.recompute()

