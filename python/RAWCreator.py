import os
import FreeCAD as App
import Utils as Utils

class RAWCreator:
    """Zentrale PDM-Logik für Halbzeuge (Typ R): Norm-Rohmaterial/-halbzeuge unterschiedlichster
    Art. Drei Wege zur Geometrie:
    - Profil+Länge (Standardfall, unverändert): Cross-Section-Skizze aus
      _Common_Resources/Profiles klonen und um die angegebene Länge padden - für einfache
      Profile/Stangenware.
    - STEP: importierte Geometrie aus dem Baum übernehmen (z.B. Blechzuschnitt, Gussrohling,
      Rundstahl-Sonderform - alles, was sich nicht als simples Profil+Länge abbilden lässt).
      Gleicher Mechanismus wie bei Kaufteilen (Typ B, siehe PurchasedPartCreator).
    - Leer: Platzhalter-Body ohne Geometrie.
    """

    def create(self, file_path, base_name, trailing_name, config, properties):
        profile_template = properties.get("ProfilTyp", "None")
        length_val = 0.0  # nur im Profil-Zweig unten befüllt, sonst PDM-Default
        material_target = properties.get("__TargetMaterialName__", "Aluminum")
        step_source_refs = properties.get("__StepSourceRefs__", None)
        # Optional: bereits fertig aufgelöstes Einzel-Solid (STEP-Struktur-Zerlegung über
        # EntityCreator._create_step_structure - "ein Körper pro Dokument")
        single_solid_shape = properties.get("__SingleSolidShape__", None)
        single_solid_label = properties.get("__SingleSolidLabel__", trailing_name)

        price_val = Utils.floatGerman(properties.get("Preis", 0.0))

        # Die reine, isolierte PDM-ID für das ERP-System holen (z.B. U20_0005_R_)
        pure_id = properties.get("__PureArticleID__", trailing_name)

        import PartDesign  # type: ignore
        new_doc = App.newDocument(trailing_name)
        App.setActiveDocument(new_doc.Name)

        core_obj = None  # wird unten je nach Geometrie-Quelle bestimmt

        # STRATEGIE-WEICHE 1: fertig aufgelöstes Einzel-Solid (aus einer STEP-Struktur-Zerlegung,
        # die EntityCreator vorher schon erledigt hat) - höchste Priorität.
        if single_solid_shape is not None:
            try:
                from PurchasedPartCreator import _build_single_body
                core_obj = _build_single_body(new_doc, base_name, trailing_name, single_solid_shape, single_solid_label)
            except Exception as e:
                App.Console.PrintWarning(f"FCProject: Fehler beim direkten Solid-Aufbau (Halbzeug): {str(e)}\n")

        # STRATEGIE-WEICHE 2: direkte STEP-Baumauswahl. Mehrfach-Solid-Strukturen fängt
        # EntityCreator.create_pdm_document bereits vorher ab (siehe dortiges _create_step_structure) -
        # hier kommt bei Typ R normalerweise nur noch der Einzel-Solid-Fall an.
        elif step_source_refs:
            try:
                from PurchasedPartCreator import _collect_solids_from_refs, _build_single_body
                solids = _collect_solids_from_refs(step_source_refs)
                if len(solids) == 1:
                    solid, src_label = solids[0]
                    core_obj = _build_single_body(new_doc, base_name, trailing_name, solid, src_label)
                elif len(solids) > 1:
                    App.Console.PrintWarning(
                        "FCProject: Mehrere Volumenkörper in der STEP-Auswahl für ein Halbzeug - "
                        "das wird hier nicht unterstützt, bitte ein einzelnes Objekt auswählen.\n"
                    )
                else:
                    App.Console.PrintWarning("FCProject: Keine gültige Geometrie in der STEP-Auswahl gefunden.\n")
            except Exception as e:
                App.Console.PrintWarning(f"FCProject: Fehler bei STEP-Geometrie-Übernahme (Halbzeug): {str(e)}\n")

        # STRATEGIE-WEICHE 3: klassisches Profil+Länge (Katalog-Skizze aus _Common_Resources/Profiles)
        elif profile_template and profile_template != "None":
            length_val = float(properties.get("Length", 500.0))

            # Absoluten Pfad zur Master-Skizzen-Vorlage ermitteln
            common_dir = os.path.join(os.path.dirname(file_path), "..", "_Common_Resources")
            template_file_path = os.path.join(common_dir, "Profiles", f"{profile_template}.FCStd")

            if not os.path.exists(template_file_path):
                raise FileNotFoundError(
                    f"Die Profilvorlage '{profile_template}.FCStd' wurde nicht gefunden!\n"
                    f"Bitte lege die Datei im Ordner: '{os.path.join(common_dir, 'Profiles')}' ab."
                )

            # Den geometrischen Hauptkörper (Body) erzeugen
            core_obj = new_doc.addObject(config.get("FreeCADType", "PartDesign::Body"), base_name)
            core_obj.Label = f"{trailing_name} | L={length_val}mm"

            # TEMPLATE-SKIZZE KLONEN (Mit striktem RAM-Schutz)
            template_doc = App.openDocument(template_file_path)
            copied_sketch = None
            for obj in template_doc.Objects:
                if obj.isDerivedFrom("Sketcher::SketchObject"):
                    copied_sketch = new_doc.copyObject(obj, False)
                    break
            App.closeDocument(template_doc.Name)

            if not copied_sketch:
                raise ValueError(f"Die Vorlage '{profile_template}' enthält keine gültige Skizze!")

            # Geometrie im neuen Body zusammensetzen und extrudieren (Pad)
            core_obj.addObject(copied_sketch)
            pad_obj = new_doc.addObject("PartDesign::Pad", f"Pad_{base_name}")
            pad_obj.Profile = copied_sketch
            pad_obj.Length = length_val
            core_obj.addObject(pad_obj)

        # STRATEGIE-WEICHE 4: Leer (oder alle vorherigen Versuche fehlgeschlagen) -> Platzhalter-Body
        if core_obj is None:
            core_obj = new_doc.addObject(config.get("FreeCADType", "PartDesign::Body"), base_name)
            core_obj.Label = trailing_name

        # TYPKONFORMES MATERIAL-BINDING MIT EXPRESSION-KOPPLUNG
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

        # REINE PDM-METADATEN AM HALBZEUG SPEICHERN
        Utils._ensure_property(App, core_obj, "App::PropertyString", "ArticleID", "FCProject", "Eindeutige ID", pure_id)
        Utils._ensure_property(App, core_obj, "App::PropertyLength", "Length", "FCProject_PDM", "Zuschnittslänge", length_val)
        Utils._ensure_property(App, core_obj, "App::PropertyString", "ProfilTyp", "FCProject_PDM", "Verwendetes Vorlagenprofil", profile_template)
        Utils._ensure_property(App, core_obj, "App::PropertyFloat", "Preis", "FCProject_PDM", "Preis für das Halbzeug", price_val)

        # Datei final auf der Festplatte sichern
        new_doc.saveAs(file_path)
        new_doc.recompute()

        App.Console.PrintMessage(f"FCProject: RAW-Halbzeug '{trailing_name}' erfolgreich mit reiner ID generiert.\n")
