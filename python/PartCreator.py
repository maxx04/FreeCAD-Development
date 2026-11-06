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
        # FCPROJECT-FIX (2026-11-06, Nutzerwunsch "Halbzeug soll auch als STEP-Datei uebernommen
        # werden koennen, wie beim B gekauften Teil"): alternative Halbzeug-Quelle direkt aus dem
        # Baum uebernommener STEP-Geometrie, analog zu PurchasedPartCreator (Typ B).
        step_source_refs = properties.get("__StepSourceRefs__", None)
        center_origin = properties.get("__CenterOrigin__", True)

        import PartDesign # type: ignore

        # 1. Neues separates Dokument für das Einzelteil (P) anlegen
        new_doc = App.newDocument(trailing_name)
        App.setActiveDocument(new_doc.Name)

        core_obj = None

        # FCPROJECT-FIX (2026-11-06, Nutzerwunsch "beim Halbzeugauswahl (Datei) gibt es nur
        # .FCStd Filter"): derselbe "Datei wählen…"-Dialog akzeptiert jetzt auch STEP-Dateien
        # direkt - Endung entscheidet, welcher der beiden Wege unten greift.
        profile_path_lower = profile_path.lower() if profile_path else ""
        is_fcstd_profile = bool(profile_path) and os.path.exists(profile_path) and profile_path_lower.endswith(".fcstd")
        is_step_profile = bool(profile_path) and os.path.exists(profile_path) and profile_path_lower.endswith((".step", ".stp"))

        # 2. STRATEGIE-WEICHE: Nur klonen, wenn wir WIRKLICH einen gültigen .FCStd-Pfad vom Dateidialog haben!
        if is_fcstd_profile:
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

        # 2a. STRATEGIE-WEICHE: direkt eine rohe STEP-Datei als Halbzeug importieren - bequemerer
        # Direktweg zum darunter stehenden Baum-Auswahl-Zweig (2b): hier wird die Datei selbst
        # noch importiert, statt bereits im Baum stehende Objekte auszuwählen. Import erfolgt in
        # ein SEPARATES Temp-Dokument (wie beim .FCStd-Klon-Zweig oben, Variable `template_doc`)
        # statt direkt in new_doc - ein STEP-Import kann je nach Datei zusätzliche Struktur
        # (eigene Origin/Achsen/Ebenen, ggf. App::Part-Wrapper) miterzeugen, die sich dort nicht
        # zuverlässig wieder sauber entfernen ließ (erster Versuch: einzelne Rohimport-Objekte
        # nach dem Bauen des Bodys direkt in new_doc wieder löschen - blieb bei verschachtelter
        # Import-Struktur teilweise hängen, live bestätigt). Das Temp-Dokument wird danach
        # komplett verworfen - _build_single_body() hat das benötigte Solid schon als eigene
        # Kopie übernommen, der Rest wird nicht mehr gebraucht.
        elif is_step_profile:
            try:
                import Import  # FreeCAD-Kernmodul für STEP/IGES-Import
                from PurchasedPartCreator import _collect_solids_from_refs, _build_single_body

                temp_doc = App.newDocument("FCProject_StepImportTemp")
                try:
                    Import.insert(profile_path, temp_doc.Name)
                    temp_doc.recompute()

                    refs = [
                        (temp_doc.Name, obj.Name) for obj in temp_doc.Objects
                        if hasattr(obj, "Shape") and obj.Shape is not None and not obj.Shape.isNull()
                    ]
                    solids = _collect_solids_from_refs(refs)

                    if solids:
                        if len(solids) > 1:
                            App.Console.PrintWarning(
                                f"FCProject: {len(solids)} Volumenkörper in "
                                f"'{os.path.basename(profile_path)}' gefunden - als Halbzeug für "
                                f"ein Einzelteil (Typ P) wird nur der erste direkt als Body "
                                f"übernommen (ein P-Teil hat genau einen Körper).\n"
                            )
                        solid, src_label = solids[0]
                        App.setActiveDocument(new_doc.Name)
                        core_obj = _build_single_body(
                            new_doc, base_name, trailing_name, solid, src_label, center_origin=center_origin
                        )
                        Utils._ensure_property(
                            App, core_obj, "App::PropertyString", "BasiertAufHalbzeug", "FCProject_PDM",
                            "Rohmaterial-Kopplung", os.path.basename(profile_path)
                        )
                        App.Console.PrintMessage("FCProject: Halbzeug direkt aus STEP-Datei importiert.\n")
                    else:
                        App.Console.PrintWarning(
                            f"FCProject: Keine gültige Geometrie in '{profile_path}' gefunden.\n"
                        )
                finally:
                    App.closeDocument(temp_doc.Name)
                    App.setActiveDocument(new_doc.Name)
            except Exception as e:
                App.Console.PrintWarning(f"FCProject: Fehler beim STEP-Datei-Import: {str(e)}\n")

        # 2b. STRATEGIE-WEICHE: Halbzeug direkt aus einer STEP-Auswahl im Baum übernehmen - wie
        # bei PurchasedPartCreator (Typ B), aber bewusst auf GENAU EINEN Körper beschränkt: ein
        # Einzelteil (P) hat per CONSTRAINTS.md immer genau einen Body, kein App::Part-Behälter
        # mit mehreren Bodies wie bei einem mehrteiligen Kaufteil.
        elif step_source_refs:
            try:
                from PurchasedPartCreator import _collect_solids_from_refs, _build_single_body
                solids = _collect_solids_from_refs(step_source_refs)
                if solids:
                    if len(solids) > 1:
                        App.Console.PrintWarning(
                            f"FCProject: {len(solids)} Volumenkörper in der STEP-Auswahl gefunden - "
                            f"als Halbzeug für ein Einzelteil (Typ P) wird nur der erste direkt als "
                            f"Body übernommen (ein P-Teil hat genau einen Körper).\n"
                        )
                    solid, src_label = solids[0]
                    core_obj = _build_single_body(
                        new_doc, base_name, trailing_name, solid, src_label, center_origin=center_origin
                    )
                    Utils._ensure_property(
                        App, core_obj, "App::PropertyString", "BasiertAufHalbzeug", "FCProject_PDM",
                        "Rohmaterial-Kopplung", src_label
                    )
                    App.Console.PrintMessage("FCProject: Halbzeug-Geometrie aus STEP-Import als Body übernommen.\n")
                else:
                    App.Console.PrintWarning("FCProject: Keine gültige Geometrie in der STEP-Auswahl gefunden.\n")
            except Exception as e:
                App.Console.PrintWarning(f"FCProject: Fehler bei STEP-Halbzeug-Übernahme: {str(e)}\n")

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
