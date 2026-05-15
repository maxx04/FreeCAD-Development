# Macro Version: 2.9.0 - FCProject: Spezialisierter PurchasedPartCreator (Typ B)
import FreeCAD as App

class PurchasedPartCreator:
    """Zentrale PDM-Logik für das Erstellen von Kaufteilen (Purchased Components)."""

    def create(self, file_path, base_name, trailing_name, config, properties):
        # 1. Parameter aus dem Datenpaket extrahieren
        bezeichnung_val = properties.get("Bezeichnung", "Kaufteil")
        hersteller_val = properties.get("Hersteller", "TraceParts")
        bestell_val = properties.get("Bestellnummer", "000-000")
        material_target = properties.get("__TargetMaterialName__", "Steel")

        # 2. Neues separates Dokument anlegen und im RAM aktivieren
        new_doc = App.newDocument(trailing_name)
        App.setActiveDocument(new_doc.Name)
        
        # Kaufteile nutzen App::Part als sauberen Import-Container für Step/Iges-Dateien
        core_obj = new_doc.addObject(config.get("FreeCADType", "App::Part"), base_name)
        core_obj.Label = trailing_name

        # 3. TYPKONFORMES MATERIAL-BINDING ÜBER CORE UUID UTILS
        try:
            if hasattr(core_obj, "ShapeMaterial"):
                from MaterialUtils import get_native_material_by_name
                cpp_material = get_native_material_by_name(material_target)
                if cpp_material:
                    core_obj.ShapeMaterial = cpp_material
                    
                if not hasattr(core_obj, "MaterialName"):
                    core_obj.addProperty("App::PropertyString", "MaterialName", "FCProject_PDM", "Material-Textbezeichnung")
                core_obj.MaterialName = material_target
                App.Console.PrintMessage(f"FCProject: Werkstoff '{material_target}' erfolgreich im Kaufteil verankert.\n")
        except Exception as mat_err:
            App.Console.PrintWarning(f"FCProject: Fehler bei Material-Speicherung im Kaufteil: {str(mat_err)}\n")

        # 4. Reine PDM-Metadaten in den Parametertree spritzen (Hersteller, Bestellnummer)
        if not hasattr(core_obj, "ArticleID"):
            core_obj.addProperty("App::PropertyString", "ArticleID", "FCProject", "Eindeutige ID")
        core_obj.ArticleID = trailing_name
        
        if not hasattr(core_obj, "Bezeichnung"):
            core_obj.addProperty("App::PropertyString", "Bezeichnung", "FCProject_PDM", "Logische Benennung")
        core_obj.Bezeichnung = bezeichnung_val

        if not hasattr(core_obj, "Hersteller"):
            core_obj.addProperty("App::PropertyString", "Hersteller", "FCProject_PDM", "Zukauf-Hersteller")
        core_obj.Hersteller = hersteller_val

        if not hasattr(core_obj, "Bestellnummer"):
            core_obj.addProperty("App::PropertyString", "Bestellnummer", "FCProject_PDM", "Hersteller-Bestellschlüssel")
        core_obj.Bestellnummer = bestell_val

        # 5. Datei final auf der Festplatte sichern
        new_doc.saveAs(file_path)
        new_doc.recompute()
        App.Console.PrintMessage(f"FCProject: Kaufteil '{trailing_name}' erfolgreich als Container generiert.\n")
