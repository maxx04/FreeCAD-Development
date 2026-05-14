# Macro Version: 2.6.2 - FCProject: Spezialisierter PartCreator mit nativer .ShapeMaterial-Speicherung
import os
import FreeCAD as App

class PartCreator:
    """Zentrale PDM-Logik für das Erstellen von Standard-Einzelteilen (Typ P)."""

    def create(self, file_path, base_name, trailing_name, config, properties):
        # 1. Parameter aus dem Datenpaket extrahieren
        bezeichnung_val = properties.get("Bezeichnung", "Standardteil")
        material_target = properties.get("__TargetMaterialName__", "Steel")

        # 2. Neues separates Dokument anlegen und im RAM aktivieren
        import PartDesign  # type: ignore
        import Materials
        new_doc = App.newDocument(trailing_name)
        App.setActiveDocument(new_doc.Name)
        
        # Den geometrischen Hauptkörper (Body) erzeugen
        core_obj = new_doc.addObject(config.get("FreeCADType"), base_name)
        core_obj.Label = trailing_name

         # 3. TYPKONFORMES MATERIAL-BINDING ÜBER CORE UUID UTILS
        try:
            material_target = properties.get("__TargetMaterialName__", "Steel")
            
            if hasattr(core_obj, "ShapeMaterial"):
                from MaterialUtils import get_native_material_by_name
                # Wir holen das verifizierte C++ Objekt über unser Unterprogramm
                cpp_material = get_native_material_by_name(material_target)
                
                if cpp_material:
                    # Direkte, C++ typsichere Zuweisung an den Körper!
                    core_obj.ShapeMaterial = cpp_material
                    
                    if not hasattr(core_obj, "MaterialName"):
                        core_obj.addProperty("App::PropertyString", "MaterialName", "FCProject_PDM", "Material-Textbezeichnung")
                    core_obj.MaterialName = material_target
                    App.Console.PrintMessage(f"FCProject: Material '{material_target}' erfolgreich via UUID-Objekt eingebrannt.\n")
                else:
                    App.Console.PrintWarning("FCProject: Nutzen Standard-Fallback, da C++ Objekt leer war.\n")
            else:
                App.Console.PrintWarning("FCProject Warnung: Der Einzelteil-Körper besitzt kein .ShapeMaterial Attribut!\n")
        except Exception as mat_err:
            App.Console.PrintWarning(f"FCProject: Fehler bei UUID-Material-Speicherung: {str(mat_err)}\n")

        # 4. Reine PDM-Metadaten in den Parametertree spritzen
        if not hasattr(core_obj, "ArticleID"):
            core_obj.addProperty("App::PropertyString", "ArticleID", "FCProject", "Eindeutige ID")
        core_obj.ArticleID = trailing_name
        
        if not hasattr(core_obj, "Bezeichnung"):
            core_obj.addProperty("App::PropertyString", "Bezeichnung", "FCProject_PDM", "Logische Bauteilbenennung")
        core_obj.Bezeichnung = bezeichnung_val

        # 5. Datei final auf der Festplatte sichern
        new_doc.saveAs(file_path)
        new_doc.recompute()