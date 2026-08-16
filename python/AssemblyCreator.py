# Macro Version: 3.2.0 - FCProject: Spezialisierter AssemblyCreator mit reiner ID-Speicherung
import os
import FreeCAD as App
import Utils as Utils

class AssemblyCreator:
    """Zentrale PDM-Logik für das Erstellen von Baugruppen (Typ A) nach FreeCAD 1.1 Standard."""

    # def _ensure_property(self, obj, prop_type, name, group, desc, default=None):
    #     try:
    #         if not hasattr(obj, name):
    #             obj.addProperty(prop_type, name, group, desc)
    #         if default is not None:
    #             setattr(obj, name, default)
    #     except Exception as e:
    #         App.Console.PrintWarning(f"FCProject: Fehler beim Anlegen/Setzen Property '{name}': {e}\n")

    def create(self, file_path, base_name, trailing_name, config, properties):
        # 1. Parameter aus dem Datenpaket extrahieren
        bezeichnung_val = properties.get("Bezeichnung", "Unterbaugruppe")
        
        # Die reine, isolierte PDM-ID für das ERP-System holen (z.B. U20_0010_A_)
        pure_id = str(properties.get("__PureArticleID__", trailing_name)).strip()

        price_val = Utils.floatGerman(properties.get("Preis", 0.0))
 
        # 2. Neues separates Dokument für die Baugruppe (A) anlegen und im RAM aktivieren
        new_doc = App.newDocument(trailing_name)
        App.setActiveDocument(new_doc.Name)
         
        # Erzeugen des nativen C++ AssemblyObjects für FreeCAD 1.1
        # config.get("FreeCADType") zieht hier "Assembly::AssemblyObject" aus deiner JSON
        core_obj = new_doc.addObject(config.get("FreeCADType", "Assembly::AssemblyObject"), base_name)
 
        # 3. FESTES MATERIAL-BINDING (Als strukturierter Fallback)
        try:
            if hasattr(core_obj, "ShapeMaterial"):
                # Baugruppen haben keine eigene feste Geometrie, bekommen aber
                # die PDM-Texteigenschaft für die BOM-Synchronisation
                Utils._ensure_property(App, core_obj, "App::PropertyString", "MaterialName", "FCProject_PDM", "Material-Textbezeichnung", "-")
        except Exception as mat_err:
            App.Console.PrintWarning(f"FCProject: Fehler bei Material-Initialisierung in Baugruppe: {str(mat_err)}\n")
 
        # 4. REINE PDM-METADATEN AM BAUGRUPPEN-CONTAINER SPEICHERN
        Utils._ensure_property(App, core_obj, "App::PropertyString", "ArticleID", "FCProject", "Eindeutige ID", pure_id)
        Utils._ensure_property(App, core_obj, "App::PropertyString", "Bezeichnung", "FCProject_PDM", "Logische Bauteilbenennung", bezeichnung_val)
        Utils._ensure_property(App, core_obj, "App::PropertyFloat", "Preis", "FCProject_PDM", "Preis für das Halbzeug", price_val)

        # 4b. Echtes LCS ergänzen (siehe CONSTRAINTS.md - Baugruppen haben zwar keine eigene
        # Geometrie, sollen aber trotzdem patternbar sein; der automatische App::Origin-Container
        # zählt dafür bewusst nicht mehr als Referenz).
        Utils.add_local_coordinate_system(core_obj)

        # 5. Datei final auf der Festplatte sichern und berechnen
        try:
            dirpath = os.path.dirname(file_path)
            if dirpath and not os.path.exists(dirpath):
                os.makedirs(dirpath, exist_ok=True)
            # Recompute vor dem Speichern, damit Zustand konsistent ist
            new_doc.recompute()
            new_doc.saveAs(file_path)
            
            # WICHTIG: Nach saveAs() kann FreeCAD den Dokument-Namen aktualisieren
            # oder das Dokument aus der Liste entfernen. Prüfe und re-registriere falls nötig
            current_doc_name = new_doc.Name
            if App.getDocument(current_doc_name) is None:
                # Dokument ist nicht mehr registriert - versuche es neu zu öffnen
                App.openDocument(file_path)
                App.Console.PrintMessage(
                    f"FCProject: Baugruppe-Dokument wurde re-registriert nach saveAs().\n"
                )
            
            App.Console.PrintMessage(f"FCProject: Native PDM-Baugruppe '{trailing_name}' erfolgreich generiert.\n")

        except Exception as save_err:
            App.Console.PrintError(f"FCProject: Fehler beim Speichern der Baugruppe '{file_path}': {save_err}\n")
            import traceback
            App.Console.PrintError(traceback.format_exc())
