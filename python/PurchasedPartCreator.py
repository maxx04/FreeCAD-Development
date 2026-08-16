
import FreeCAD as App
import Utils as Utils


def _solids_from_shape(shape):
    """Liefert möglichst echte Volumenkörper aus einem beliebigen Shape - mit zunehmend
    aggressiven Fallbacks, damit auch STEP-Importe ohne fertig verbaute Solids (nur geschlossene
    Schalen oder lose, abgrenzende Flächen) noch zu PartDesign::Body-tauglichen Körpern werden.
    Gibt eine leere Liste zurück, wenn sich wirklich kein Volumen bilden lässt."""
    import Part # type: ignore

    if shape.Solids:
        return list(shape.Solids)

    # Keine fertigen Solids: lose Flächen erst zu Schalen vernähen (auf einer Kopie, damit
    # das Original-Importobjekt unangetastet bleibt)
    work_shape = shape
    if not work_shape.Shells and work_shape.Faces:
        work_shape = shape.copy()
        try:
            work_shape.sewShape()
        except Exception:
            pass

    if work_shape.Shells:
        try:
            solidified = Part.makeSolid(work_shape)
            if solidified.Solids:
                return list(solidified.Solids)
        except Exception:
            pass

    return []


def _build_single_body(new_doc, base_name, trailing_name, solid, src_label, center_origin=True):
    """Baut aus genau einem Solid einen Body direkt als Root-Objekt (kein App::Part-Wrapper) -
    gemeinsam genutzt vom einzelnen STEP-Objekt-Fall und von der Multi-Solid-Baugruppen-Zerlegung
    (dort bekommt jedes Teildokument über EntityCreator._create_step_assembly denselben Weg, nur mit
    einem bereits fertig aufgelösten Solid statt einer Baum-Auswahl).

    center_origin=True (Standard, mit dem User abgesprochen): verschiebt die Geometrie von der
    rohen STEP-Weltkoordinate auf einen lokalen Ursprung (Bounding-Box-Mitte in X/Y, Unterkante in
    Z) - besser fürs spätere Alleine-Bearbeiten/Zeichnungen/Pattern-Features, die von einem
    sinnvollen lokalen Ursprung ausgehen. Der dabei entstehende Versatz wird als
    ImportOriginOffset-Property am Body gespeichert; EntityCreator._link_parts_into_assembly liest
    ihn beim Verlinken in eine Baugruppe wieder aus und kompensiert ihn über das Link-Placement,
    damit sich an der sichtbaren Anordnung der Baugruppe nichts ändert."""
    offset = App.Vector(0, 0, 0)
    work_solid = solid
    if center_origin:
        try:
            bbox = solid.BoundBox
            offset = App.Vector(bbox.Center.x, bbox.Center.y, bbox.ZMin)
            if offset.Length > 1e-7:
                work_solid = solid.copy()
                work_solid.translate(App.Vector(-offset.x, -offset.y, -offset.z))
        except Exception as e:
            App.Console.PrintWarning(
                f"FCProject: Automatische Ursprungs-Zentrierung für '{src_label}' fehlgeschlagen, "
                f"STEP-Koordinate wird beibehalten: {str(e)}\n"
            )
            offset = App.Vector(0, 0, 0)
            work_solid = solid

    import_feat = new_doc.addObject("Part::Feature", f"{base_name}_ImportGeo")
    import_feat.Shape = work_solid
    import_feat.Label = f"{src_label}_Geometrie"
    import_feat.Visibility = False

    body = new_doc.addObject("PartDesign::Body", base_name)
    body.Label = trailing_name
    body.BaseFeature = import_feat

    if offset.Length > 1e-7:
        body.addProperty(
            "App::PropertyVector", "ImportOriginOffset", "FCProject_Import",
            "Versatz zur ursprünglichen STEP-Weltkoordinate (für Kompensation beim Verlinken in eine Baugruppe)"
        )
        body.ImportOriginOffset = offset

    return body


def _collect_solids_from_refs(step_source_refs):
    """Löst (Dokument, Objekt)-Referenzen aus der Baum-Auswahl auf und sammelt alle enthaltenen
    Volumenkörper. Objekte, aus denen sich wirklich kein Volumen bilden lässt, werden mit ihrem
    kompletten Shape als Fallback-Körper übernommen, statt sie stillschweigend zu verwerfen."""
    collected = []  # Liste von (Shape, Quell-Label)
    for doc_name, obj_name in step_source_refs or []:
        src_doc = App.getDocument(doc_name) if doc_name else None
        src_obj = src_doc.getObject(obj_name) if src_doc else None
        if not src_obj or not hasattr(src_obj, "Shape") or src_obj.Shape is None or src_obj.Shape.isNull():
            App.Console.PrintWarning(f"FCProject: STEP-Quellobjekt '{obj_name}' nicht auffindbar oder ohne Shape - übersprungen.\n")
            continue

        solids = _solids_from_shape(src_obj.Shape)
        if solids:
            for solid in solids:
                collected.append((solid, src_obj.Label))
        else:
            App.Console.PrintWarning(
                f"FCProject: '{src_obj.Label}' enthält auch nach dem Vernähen der Flächen keinen "
                f"schließbaren Volumenkörper - Shape wird unverändert als einzelner Körper übernommen.\n"
            )
            collected.append((src_obj.Shape.copy(), src_obj.Label))
    return collected


class PurchasedPartCreator:
    """
    FCProject: Spezialisierter PurchasedPartCreator für Kaufteile (Typ B)
    PDM-Logik für Kaufteile (Typ B). Integriert CAD-Imports als Basis-Komponente
    mit CAD-Import als Basis. Integriert Material-Expressions und PDM-Metadaten.

    Zwei Wege zur Basis-Geometrie (kein Vorlagen-Klonen mehr - "Profil" ist konzeptionell Sache
    von Halbzeugen/Typ R, ein Kaufteil kommt entweder importiert oder wird leer angelegt):
    - __SingleSolidShape__/__SingleSolidLabel__: ein bereits fertig aufgelöstes Einzel-Solid, direkt
      als Body übernommen. Wird von EntityCreator._create_step_assembly für "ein Körper pro Dokument"
      genutzt (Multi-Solid-STEP -> mehrere Kaufteil-Dokumente + 1 verlinkendes Assembly-Dokument).
    - __StepSourceRefs__: direkt aus dem Baum übernommene, bereits importierte STEP-Objekte. Bei genau
      1 Solid identisch zum obigen Weg; bei mehreren Solids historischer Fallback (alle Bodies flach
      in einem Dokument unter einem App::Part) - wird für Typ B inzwischen von EntityCreator schon vor
      dem Aufruf abgefangen und in einzelne Dokumente + Assembly aufgelöst.

    Der App::Part-Behälter wird NUR angelegt, wenn er wirklich gebraucht wird (mehrere Bodies,
    oder gar keine Geometrie-Quelle). Ergibt sich am Ende genau EIN Körper (1 Solid, oder ein
    einzelnes geklontes Objekt aus der Vorlage), wird dieser direkt als Root-PDM-Objekt verwendet -
    analog zu PartCreator.py (Typ P), das für Einzelteile aus demselben Grund auf den Wrapper
    verzichtet ("Body direkt als Root-Objekt").
    """

    def create(self, file_path, base_name, trailing_name, config, properties):
        bezeichnung_val = properties.get("Bezeichnung", "Kaufteil")
        hersteller_val = properties.get("Hersteller", "TraceParts")
        bestell_val = properties.get("Bestellnummer", "000-000")
        material_target = properties.get("__TargetMaterialName__", "Steel")
        step_source_refs = properties.get("__StepSourceRefs__", None)   # Optional: Baum-Auswahl aus STEP-Import
        # Optional: bereits fertig aufgelöstes Einzel-Solid (Multi-Solid-Baugruppen-Zerlegung, siehe
        # EntityCreator._create_step_assembly - "ein Körper pro Dokument")
        single_solid_shape = properties.get("__SingleSolidShape__", None)
        single_solid_label = properties.get("__SingleSolidLabel__", trailing_name)
        # Ob importierte STEP-Geometrie auf einen lokalen Ursprung zentriert wird (Standard: ja,
        # siehe _build_single_body) - vom User im STEP-Bereich des TaskPanels umschaltbar.
        center_origin = properties.get("__CenterOrigin__", True)
        price_val = Utils.floatGerman(properties.get("Preis", 0.0))

        new_doc = App.newDocument(trailing_name)
        App.setActiveDocument(new_doc.Name)

        core_obj = None  # wird unten je nach Geometrie-Quelle bestimmt

        # STRATEGIE-WEICHE 0: Fertig aufgelöstes Einzel-Solid direkt übergeben - höchste Priorität,
        # da dieser Weg gezielt von EntityCreator für "ein Teil pro Dokument" genutzt wird.
        if single_solid_shape is not None:
            try:
                import PartDesign # type: ignore
                core_obj = _build_single_body(new_doc, base_name, trailing_name, single_solid_shape, single_solid_label, center_origin=center_origin)
            except Exception as e:
                App.Console.PrintWarning(f"FCProject: Fehler beim direkten Solid-Aufbau: {str(e)}\n")

        # STRATEGIE-WEICHE 1: Aus dem Baum übernommene STEP-Geometrie - hat Vorrang, da konkreter
        # und aktueller als eine generische Halbzeug-Vorlagendatei.
        elif step_source_refs:
            try:
                import PartDesign # type: ignore
                solids = _collect_solids_from_refs(step_source_refs)

                if len(solids) == 1:
                    # Genau ein Volumenkörper -> der Body IST das Kaufteil, kein zusätzlicher
                    # App::Part-Behälter drumherum nötig.
                    solid, src_label = solids[0]
                    core_obj = _build_single_body(new_doc, base_name, trailing_name, solid, src_label, center_origin=center_origin)

                    App.Console.PrintMessage(
                        f"FCProject: 1 Volumenkörper aus {len(step_source_refs)} STEP-Objekt(en) direkt "
                        f"als Body übernommen (ohne App::Part-Behälter).\n"
                    )

                elif len(solids) > 1:
                    # Mehrere Volumenkörper -> "Assembly"-artige Struktur: App::Part-Behälter mit
                    # je einem eigenen Body pro Solid - hier braucht es den Container wirklich.
                    core_obj = new_doc.addObject(config.get("FreeCADType", "App::Part"), base_name)
                    core_obj.Label = trailing_name

                    for idx, (solid, src_label) in enumerate(solids, start=1):
                        suffix = f"_{idx:02d}"
                        import_feat = new_doc.addObject("Part::Feature", f"{base_name}_ImportGeo{suffix}")
                        import_feat.Shape = solid
                        import_feat.Label = f"{src_label}_Geometrie{suffix}"
                        import_feat.Visibility = False

                        body = new_doc.addObject("PartDesign::Body", f"{base_name}_Body{suffix}")
                        body.Label = f"{trailing_name}{suffix}"
                        body.BaseFeature = import_feat
                        core_obj.addObject(body)

                    App.Console.PrintMessage(
                        f"FCProject: {len(solids)} Volumenkörper aus {len(step_source_refs)} STEP-Objekt(en) "
                        f"als PartDesign::Body-Struktur übernommen.\n"
                    )
                else:
                    App.Console.PrintWarning("FCProject: Keine gültige Geometrie in der STEP-Auswahl gefunden.\n")
            except Exception as e:
                App.Console.PrintWarning(f"FCProject: Fehler bei STEP-Geometrie-Übernahme: {str(e)}\n")

        # STRATEGIE-WEICHE 2: Keine Geometrie-Quelle (Radio "Leer") oder der STEP-Versuch ist
        # fehlgeschlagen -> leerer App::Part-Behälter als Platzhalter, wie bisher.
        if core_obj is None:
            core_obj = new_doc.addObject(config.get("FreeCADType", "App::Part"), base_name)
            core_obj.Label = trailing_name

        # Material-Expression setzen
        try:
            if hasattr(core_obj, "ShapeMaterial"):
                from MaterialUtils import get_native_material_by_name
                cpp_material = get_native_material_by_name(material_target)
                if cpp_material:
                    core_obj.ShapeMaterial = cpp_material
                if not hasattr(core_obj, "MaterialName"):
                    core_obj.addProperty("App::PropertyString", "MaterialName", "FCProject_PDM", "Material-Textbezeichnung")
                core_obj.setExpression('MaterialName', 'ShapeMaterial.Name')
        except Exception as mat_err:
            App.Console.PrintWarning(f"FCProject: Fehler bei Material-Kopplung im Kaufteil: {str(mat_err)}\n")

        # Wir holen uns die reine, saubere PDM-ID aus dem Fabrik-Paket
        pure_id = properties.get("__PureArticleID__", trailing_name)

        Utils._ensure_property(App, core_obj, "App::PropertyString", "ArticleID", "FCProject", "Eindeutige ID", pure_id)
        Utils._ensure_property(App, core_obj, "App::PropertyString", "Bezeichnung", "FCProject_PDM", "Logische Benennung", bezeichnung_val)
        Utils._ensure_property(App, core_obj, "App::PropertyString", "Hersteller", "FCProject_PDM", "Herstellerbezeichnung", hersteller_val)
        Utils._ensure_property(App, core_obj, "App::PropertyString", "Bestellnummer", "FCProject_PDM", "Bestellnummer", bestell_val)
        Utils._ensure_property(App, core_obj, "App::PropertyFloat", "Preis", "FCProject_PDM", "Preis für das Halbzeug", price_val)

        # Echtes LCS ergänzen (siehe CONSTRAINTS.md - Pattern/Joints brauchen eine verlässliche
        # Referenz, der automatische App::Origin-Container zählt dafür bewusst nicht mehr). Deckt
        # hier alle drei Geometrie-Wege ab (Einzel-Solid/Multi-Solid/leer), da core_obj an dieser
        # Stelle in jedem Fall schon final feststeht.
        Utils.add_local_coordinate_system(core_obj)

        new_doc.saveAs(file_path)
        new_doc.recompute()
