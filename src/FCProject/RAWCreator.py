# Macro Version: 2.2.0 - FCProject: Template-basierter Profil-Creator mit Material-Injektion
import os
import FreeCAD as App
import FreeCADGui as Gui

class RAWCreator:
    def create(self, file_path, base_name, trailing_name, config, properties):
        # 1. Parameter aus dem Datenpaket holen
        length_val = float(properties.get("Length", 500.0))
        profile_template = properties.get("ProfilTyp", "None")
        material_selected = properties.get("MaterialCard", "Steel")

        # 2. Pfad zur Master-Skizzen-Datei ermitteln
        addon_dir = os.path.dirname(__file__)
        template_file_path = os.path.join(addon_dir, "Profiles", f"{profile_template}.FCStd")

        if not os.path.exists(template_file_path):
            raise FileNotFoundError(f"Die Profilvorlage '{profile_template}.FCStd' wurde im Profiles-Ordner nicht gefunden!")

        # 3. Neues Ziel-Dokument für das PDM-Teil anlegen
        import PartDesign # type: ignore
        new_doc = App.newDocument(trailing_name)
        App.setActiveDocument(new_doc.Name)
        
        # Neuen nativen Körper (Body) erzeugen
        core_obj = new_doc.addObject(config.get("FreeCADType"), base_name)
        core_obj.Label = f"{trailing_name} | L={length_val}mm"

        # 4. SKIZZEN-KLONEN: Template-Datei im Hintergrund öffnen und Skizze kopieren
        template_doc = App.open(template_file_path)
        copied_sketch = None
        
        # Suche nach der ersten verfügbaren Skizze in der Vorlage
        for obj in template_doc.Objects:
            if obj.isDerivedFrom("Sketcher::SketchObject"):
                # Skizze in das neue PDM-Dokument kopieren
                copied_sketch = new_doc.copyObject(obj, False)
                break
                
        # Template-Dokument sofort wieder im Hintergrund schließen (RAM freigeben)
        App.closeDocument(template_doc.Name)

        if not copied_sketch:
            raise ValueError(f"Die Vorlage '{profile_template}' enthält keine gültige Skizze!")

        # 5. Geometrie im neuen Body zusammensetzen
        # Skizze dem neuen Körper unterordnen
        core_obj.addObject(copied_sketch)
        
        # Die Skizze auf die gewünschte PDM-Länge extrudieren (Pad)
        pad_obj = new_doc.addObject("PartDesign::Pad", f"Pad_{base_name}")
        pad_obj.Profile = copied_sketch
        pad_obj.Length = length_val
        core_obj.addObject(pad_obj) # Pad dem Körper zuordnen

        # 6. NATIVES FREECAD MATERIAL INJIZIEREN
        # Wir erzeugen eine standardmäßige Materialkarte, die mit der FreeCAD MaterialWorkbench kompatibel ist
        try:
            import Material # type: ignore
            # Erzeuge die native Material-Eigenschaft, falls nicht vorhanden
            if not hasattr(core_obj, "Material"):
                core_obj.addProperty("App::PropertyMaterial", "Material", "FCProject_PDM", "Natives CAD Material")
            
            # Nutze FreeCADs eingebauten Material-Katalog im Hintergrund
            # Sucht nach z.B. Aluminum.FCMat oder Steel.FCMat im FreeCAD-System
            material_file = f"{material_selected}.FCMat"
            core_obj.Material = Material.getMaterial(material_file)
            App.Console.PrintMessage(f"FCProject: Material '{material_selected}' erfolgreich zugewiesen.\n")
        except Exception as mat_err:
            App.Console.PrintWarning(f"FCProject: Natives Material-Binding fehlgeschlagen (Nutze String-Fallback): {str(mat_err)}\n")
            # Fallback als einfacher Text, falls die Material-Erweiterung nicht geladen ist
            if not hasattr(core_obj, "MaterialName"):
                core_obj.addProperty("App::PropertyString", "MaterialName", "FCProject_PDM", "Material-Text")
            core_obj.MaterialName = material_selected

        # 7. PDM Metadaten spritzen
        core_obj.addProperty("App::PropertyString", "ArticleID", "FCProject").ArticleID = trailing_name
        core_obj.addProperty("App::PropertyLength", "Length", "FCProject_PDM").Length = length_val
        core_obj.addProperty("App::PropertyString", "ProfilTyp", "FCProject_PDM").ProfilTyp = profile_template

        # Speichern und visuell neu aufbauen
        new_doc.saveAs(file_path)
        new_doc.recompute()
        
        # Aktiviert das Dokument im UI, damit du das Profil sofort siehst
        Gui.setActiveDocument(new_doc.Name)
