# Macro Version: 3.2.0 - FCProject: Spezialisierter AssemblyCreator mit reiner ID-Speicherung
import os
import FreeCAD as App

class AssemblyCreator:
    """Zentrale PDM-Logik für das Erstellen von Baugruppen (Typ A) nach FreeCAD 1.1 Standard."""

    def create(self, file_path, base_name, trailing_name, config, properties):
        # 1. Parameter aus dem Datenpaket extrahieren
        bezeichnung_val = properties.get("Bezeichnung", "Unterbaugruppe")
        
        # Die reine, isolierte PDM-ID für das ERP-System holen (z.B. U20_0010_A_)
        pure_id = properties.get("__PureArticleID__", trailing_name)

        # 2. Neues separates Dokument für die Baugruppe (A) anlegen und im RAM aktivieren
        import Assembly  # type: ignore
        new_doc = App.newDocument(trailing_name)
        App.setActiveDocument(new_doc.Name)
        
        # Erzeugen des nativen C++ AssemblyObjects für FreeCAD 1.1
        # config.get("FreeCADType") zieht hier "Assembly::AssemblyObject" aus deiner JSON
        core_obj = new_doc.addObject(config.get("FreeCADType", "Assembly::AssemblyObject"), base_name)
        core_obj.Label = trailing_name

        # 3. FESTES MATERIAL-BINDING (Als strukturierter Fallback)
        try:
            if hasattr(core_obj, "ShapeMaterial"):
                # Baugruppen haben keine eigene feste Geometrie, bekommen aber
                # die PDM-Texteigenschaft für die BOM-Synchronisation
                if not hasattr(core_obj, "MaterialName"):
                    core_obj.addProperty("App::PropertyString", "MaterialName", "FCProject_PDM", "Material-Textbezeichnung")
                core_obj.MaterialName = "-"
        except Exception as mat_err:
            App.Console.PrintWarning(f"FCProject: Fehler bei Material-Initialisierung in Baugruppe: {str(mat_err)}\n")

        # 4. REINE PDM-METADATEN AM BAUGRUPPEN-CONTAINER SPEICHERN
        if not hasattr(core_obj, "ArticleID"):
            core_obj.addProperty("App::PropertyString", "ArticleID", "FCProject", "Eindeutige ID")
        
        # KORREKTUR: Es wird NUR noch die saubere, reine ID eingepflegt (Behebt den Suffix-Fehler!)
        core_obj.ArticleID = pure_id
        
        if not hasattr(core_obj, "Bezeichnung"):
            core_obj.addProperty("App::PropertyString", "Bezeichnung", "FCProject_PDM", "Logische Bauteilbenennung")
        core_obj.Bezeichnung = bezeichnung_val

        # 5. Datei final auf der Festplatte sichern und berechnen
        new_doc.saveAs(file_path)
        new_doc.recompute()
        
        App.Console.PrintMessage(f"FCProject: Native PDM-Baugruppe '{trailing_name}' erfolgreich generiert.\n")
