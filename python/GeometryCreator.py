# Macro Version: 3.2.0 - FCProject: Spezialisierter GeometryCreator mit Assembly-Crash-Schutz
import os
import FreeCAD as App
import Utils as Utils

class GeometryCreator:
    """Zentrale PDM-Logik für das Erstellen von Geometrie-Skeletten (Typ G) / Referenzen."""

    def create(self, file_path, base_name, trailing_name, config, properties):
        # Die reine, isolierte PDM-ID für das ERP-System holen (z.B. U20_0004_G_)
        pure_id = properties.get("__PureArticleID__", trailing_name)

        # 1. Neues separates Dokument für das Geometrie-Skelett (G) anlegen und aktivieren
        new_doc = App.newDocument(trailing_name)
        App.setActiveDocument(new_doc.Name)
        
        # Erzeugen des Containers (App::Part laut deiner JSON) [20:07]
        core_obj = new_doc.addObject(config.get("FreeCADType", "App::Part"), base_name)
        core_obj.Label = trailing_name

        # 2. KORREKTUR/CRASH-SCHUTZ: Unsichtbares Element für die Assembly-Workbench anlegen!
        # Wir fügen einen leeren PartDesign-Body in das Skelett ein.
        # Dadurch besitzt das Objekt für den C++ Kern eine gültige Struktur und .Shape,
        # was den BoundBox-Absturz in 'CommandInsertLink.py' restlos beseitigt.
        import PartDesign # type: ignore
        dummy_body = new_doc.addObject("PartDesign::Body", f"Skelett_Body_{base_name}")
        dummy_body.Label = "Konstruktions_Ebene"
        core_obj.addObject(dummy_body) # Dem App::Part Container unterordnen [20:07]

        # 3. REINE PDM-METADATEN AM GEOMETRIE-CONTAINER SPEICHERN
        if not hasattr(core_obj, "ArticleID"):
            core_obj.addProperty("App::PropertyString", "ArticleID", "FCProject", "Eindeutige ID")
        
        # KORREKTUR: Es wird NUR noch die saubere, textfreie ID eingepflegt! [20:10]
        core_obj.ArticleID = pure_id

        # 3b. Echtes LCS ergänzen (siehe CONSTRAINTS.md - Pattern/Joints brauchen eine verlässliche
        # Referenz, der automatische App::Origin-Container zählt dafür bewusst nicht mehr).
        Utils.add_local_coordinate_system(core_obj)

        # 4. Datei final auf der Festplatte sichern und berechnen
        new_doc.saveAs(file_path)
        new_doc.recompute()
        
        App.Console.PrintMessage(f"FCProject: Geometrie-Skelett '{trailing_name}' erfolgreich und crash-sicher generiert.\n")
