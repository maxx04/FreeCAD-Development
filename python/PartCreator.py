#FCProject: PartCreator - Body direkt als Root-Objekt (ohne App::Part-Wrapper)
import os
import Utils as Utils
import FreeCAD as App


class PartCreator:
    """PDM-Logik für Einzelteile (Typ P). Unterstützt Klonierung und leere Standard-Erstellung."""

    def create(self, file_path, base_name, trailing_name, config, properties):
        bezeichnung_val = properties.get("Bezeichnung", "Standardteil")
        material_target = properties.get("__TargetMaterialName__", "Steel")
        price_val = Utils.floatGerman(properties.get("Preis", 0.0))

        # Der absolute Pfad zur gewählten Halbzeug-Datei (wird nur gesetzt, wenn im Dialog 'Ja' geklickt wurde)
        profile_path = properties.get("__LinkedRawProfilePath__", None)

        import PartDesign # type: ignore

        # 1. Neues separates Dokument für das Einzelteil (P) anlegen
        new_doc = App.newDocument(trailing_name)
        App.setActiveDocument(new_doc.Name)

        core_obj = None

        # 2. STRATEGIE-WEICHE: Nur klonen, wenn wir WIRKLICH einen gültigen Pfad vom Dateidialog haben!
        if profile_path and os.path.exists(profile_path):
            try:
                template_doc = App.openDocument(profile_path)
                source_body = None

                for obj in template_doc.Objects:
                    if obj.isDerivedFrom("PartDesign::Body") or obj.isDerivedFrom("App::Part"):
                        source_body = obj
                        break

                if source_body:
                    # Der Klon (Vollständig autark zum Weiterkonstruieren) wird direkt als Root-Body übernommen
                    core_obj = new_doc.copyObject(source_body, True)
                    core_obj.Label = trailing_name

                    # Custom PDM Link-Eigenschaft für die Stückliste direkt am Body sichern
                    Utils._ensure_property(App, core_obj, "App::PropertyString", "BasiertAufHalbzeug", "FCProject_PDM", "Rohmaterial-Kopplung", os.path.basename(profile_path))

                    App.Console.PrintMessage(f"FCProject: Klon für Halbzeug erfolgreich durchgeführt.\n")

                App.closeDocument(template_doc.Name)
            except Exception as e:
                App.Console.PrintWarning(f"FCProject: Fehler beim Profil-Klonen: {str(e)}\n")

        # 3. Wenn KEIN Halbzeug ausgewählt wurde (Klassischer, leerer Body)
        if not core_obj:
            # Wir erzeugen einen komplett leeren, nativen PartDesign::Body als Root-Objekt
            core_obj = new_doc.addObject(config.get("FreeCADType", "PartDesign::Body"), base_name)
            core_obj.Label = trailing_name

            # Da es kein Halbzeug gibt, setzen wir das PDM-Attribut auf den Standard-Strich
            Utils._ensure_property(App, core_obj, "App::PropertyString", "BasiertAufHalbzeug", "FCProject_PDM", "Rohmaterial-Kopplung", "-")

            App.Console.PrintMessage("FCProject: Normales, leeres Einzelteil ohne Halbzeug-Basis erfolgreich initialisiert.\n")

        # 4. Dynamische Material-Synchronisation direkt am Body
        try:
            if hasattr(core_obj, "ShapeMaterial"):
                from MaterialUtils import get_native_material_by_name
                cpp_material = get_native_material_by_name(material_target)
                if cpp_material:
                    core_obj.ShapeMaterial = cpp_material

                if not hasattr(core_obj, "MaterialName"):
                    core_obj.addProperty("App::PropertyString", "MaterialName", "FCProject_PDM", "Material-Textbezeichnung")

                # Expression koppelt das Feld direkt und synchron an den nativen Kern des Bodys
                core_obj.setExpression('MaterialName', 'ShapeMaterial.Name')
        except Exception as mat_err:
            App.Console.PrintWarning(f"FCProject: Fehler bei Material-Kopplung: {str(mat_err)}\n")

        # 5. PDM Metadaten direkt am Body spritzen (Mit der reinen ArtikelID)
        pure_id = properties.get("__PureArticleID__", trailing_name)

        Utils._ensure_property(App, core_obj, "App::PropertyString", "ArticleID", "FCProject", "Eindeutige ID", pure_id)
        Utils._ensure_property(App, core_obj, "App::PropertyString", "Bezeichnung", "FCProject_PDM", "Logische Bauteilbenennung", bezeichnung_val)
        Utils._ensure_property(App, core_obj, "App::PropertyFloat", "Preis", "FCProject_PDM", "Preis für das Halbzeug", price_val)

        # 5b. Echtes LCS ergänzen (siehe CONSTRAINTS.md - Pattern/Joints brauchen eine verlässliche
        # Referenz, der automatische App::Origin-Container zählt dafür bewusst nicht mehr).
        Utils.add_local_coordinate_system(core_obj)

        # 6. Sichern und Berechnen
        new_doc.saveAs(file_path)
        new_doc.recompute()
