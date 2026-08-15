# In deiner EntityCreator.py
import os
import re

class EntityCreator:
    """Zentrale PDM-Fabrik, die Anfragen an spezialisierte Creatoren verteilt."""
    
    def __init__(self, project_name, project_dir):
        # KORREKTUR: Zwingenden String-Fallback sicherstellen, falls project_name None ist
        self.project_name = project_name if project_name else "PROJ"
        self.project_dir = project_dir if project_dir else os.getcwd()
        self.config_data = self._load_config()

    def _load_config(self):
        """Lädt die JSON Konfigurationsdatei mit integrierter Absturzsicherung."""
        import json
        if not self.project_dir:
            return {}
        
        # Sicherstellen, dass wir im korrekten PROJ_X Ordner suchen
        folder_name = os.path.basename(self.project_dir)
        json_path = os.path.join(self.project_dir, f"{folder_name}.json")
        
        if os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def get_next_available_number(self):
        """Scannt den Ordner nach Mustern wie 'PROJ_XXXX_*' und gibt die nächste Nummer zurück."""
        highest_num = 0
        if not self.project_dir or not os.path.exists(self.project_dir): 
            return "001"

        # KORREKTUR: Escapesicherer Schutz, falls project_name ungültige Zeichen enthält
        clean_proj_name = str(self.project_name)
        pattern = re.compile(rf"^{re.escape(clean_proj_name)}_(\d{{3}})_[APRGB]")
        
        try:
            for filename in os.listdir(self.project_dir):
                match = pattern.match(filename)
                if match:
                    num = int(match.group(1))
                    if num > highest_num: 
                        highest_num = num
        except Exception as e:
            import FreeCAD as App
            App.Console.PrintWarning(f"FCProject: Fehler beim Ordner-Scan für Auto-Nummer: {str(e)}\n")
                    
        return f"{highest_num + 1:03d}"

    def create_pdm_document(self, comp_type, comp_num, user_properties):
        """Generiert den Basisnamen und delegiert die Erstellung an die Ziel-Klasse."""

        # SONDERFALL Typ B/R mit STEP-Struktur-Auswahl: "ein Körper pro Dokument" einhalten - statt
        # alle Bodies flach in einem Dokument zu sammeln, wird daraus eine echte (ggf. verschachtelte)
        # Baugruppen-Hierarchie aus mehreren Kaufteil-Dokumenten + verlinkenden Assembly-Dokumenten.
        # Bei einem einzelnen Objekt mit genau 1 Solid fällt das unten unverändert in den normalen
        # Einzel-Dokument-Pfad durch (der bei Typ R übliche Fall - ein Halbzeug ist meist ein
        # einzelner Rohling, keine Mehrteil-Struktur). Kommt der seltene Mehrteil-Fall doch bei R
        # vor, werden die Einzelteile - wie bei B - als Kaufteil-Dokumente angelegt; eine eigene
        # "Halbzeug-Baugruppe"-Semantik gibt es dafür (noch) nicht.
        if comp_type in ("B", "R") and user_properties.get("__StepSourceRefs__"):
            from StepStructureImporter import build_step_tree, resolve_refs_to_objects
            objs = resolve_refs_to_objects(user_properties["__StepSourceRefs__"])
            nodes = build_step_tree(objs)
            needs_structure = (
                len(nodes) > 1
                or (len(nodes) == 1 and nodes[0]["kind"] == "group")
                or (len(nodes) == 1 and nodes[0]["kind"] == "leaf" and len(nodes[0]["solids"]) > 1)
            )
            if needs_structure:
                return self._create_step_structure(nodes, comp_num, user_properties)

        # 1. Die REINE PDM-ID ohne jeglichen Text berechnen (Der Kern für die BOM!)
        base_pdm_id = f"{self.project_name}_{comp_num}_{comp_type}"

        # 2. Das Suffix für den physischen Dateinamen ermitteln
        bezeichnung_suffix = ""
        if comp_type in ["P", "A", "B"] and "Bezeichnung" in user_properties and user_properties["Bezeichnung"]:
            bezeichnung_suffix = f"_{user_properties['Bezeichnung']}"
        elif comp_type == "R" and "ProfilTyp" in user_properties and user_properties["ProfilTyp"]:
            bezeichnung_suffix = f"_{user_properties['ProfilTyp']}"

        # Dateiname bleibt für das Auge lang und beschreibend
        # KORREKTUR: Kein angehängter Unterstrich mehr - FreeCAD darf jetzt gleiche
        # Labels haben (Option aktiviert), das automatische 001/002-Suffix entfällt,
        # daher war der künstliche Trenn-Unterstrich am Ende nicht mehr nötig.
        pdm_base_name = f"{self.project_name}_{comp_num}_{comp_type}{bezeichnung_suffix}"
        new_file_path = os.path.join(self.project_dir, f"{pdm_base_name}.FCStd")

        if os.path.exists(new_file_path):
            raise FileExistsError(f"Die Datei {pdm_base_name}.FCStd existiert bereits!")

        # Wir packen die reine, saubere ID als Steuerungs-Variable in die Properties!
        user_properties["__PureArticleID__"] = base_pdm_id

        entity_config = self.config_data.get("Entities", {}).get(comp_type, {})
        
        # 3. Match-case für die Delegation an die spezifischen Creator-Klassen
        match comp_type:
            case "P":
                from PartCreator import PartCreator
                creator = PartCreator()
            case "A":
                from AssemblyCreator import AssemblyCreator
                creator = AssemblyCreator()
            case "G":
                from GeometryCreator import GeometryCreator
                creator = GeometryCreator()
            case "R":
                from RAWCreator import RAWCreator
                creator = RAWCreator()
            case "B":
                from PurchasedPartCreator import PurchasedPartCreator
                creator = PurchasedPartCreator()
            case _:
                raise ValueError(f"Unbekannter PDM-Komponenten-Typ: {comp_type}")

        # Den Creator ausführen
        creator.create(new_file_path, pdm_base_name, pdm_base_name, entity_config, user_properties)

        # WICHTIG: FreeCAD sanitisiert Sonderzeichen (Leerzeichen, Bindestriche, ...) im internen
        # Document-Namen automatisch weg (z.B. "...M4x14-Schraube" -> "..._M4x14_Schraube" als
        # echter .Name) - der angefragte pdm_base_name spiegelt das nicht wider. Gäbe man ihn
        # unverändert zurück, würden nachgelagerte App.getDocument(name)-Aufrufe (z.B.
        # TaskPanel._fit_and_isometric_view) mit "Unknown document" fehlschlagen, sobald eine
        # Bezeichnung/ein ProfilTyp ein solches Zeichen enthält (Bezeichnungen mit Bindestrich sind
        # im Maschinenbau eher die Regel als die Ausnahme). Stattdessen robust über die immer
        # saubere ArticleID nach dem echten Namen suchen.
        real_doc, _real_obj = self._find_by_article_id(base_pdm_id)
        return real_doc.Name if real_doc else pdm_base_name

    def _create_step_structure(self, nodes, comp_num, user_properties):
        """Baut aus einer (ggf. mehrstufigen) STEP-Struktur-Beschreibung (siehe StepStructureImporter)
        die passende PDM-Hierarchie: Leaf-Solids werden zu Kaufteilen (Typ B, "ein Körper pro
        Dokument"), Struktur-Gruppen (App::Part-Container) zu Baugruppen (Typ A) mit Links auf ihre
        Kind-Elemente - beliebig tief verschachtelt. Die absolute STEP-Position bleibt in der
        jeweiligen Teil-Geometrie erhalten, Links bekommen Identity-Placement (die Anordnung stimmt
        dadurch automatisch, ohne dass Platzierungen einzeln nachgerechnet werden müssen)."""
        import FreeCAD as App

        base_bezeichnung = user_properties.get("Bezeichnung", "Kaufteil")
        # __StepSourceRefs__/__PureArticleID__/Bezeichnung gehören nur zum obersten Aufruf, nicht
        # unverändert an jedes Kind weiterreichen (jedes Kind bekommt seine eigene Bezeichnung)
        shared_props = {
            k: v for k, v in user_properties.items()
            if k not in ("__StepSourceRefs__", "__PureArticleID__", "Bezeichnung")
        }

        if len(nodes) == 1 and nodes[0]["kind"] == "group":
            # Direkt eine Struktur-Gruppe ausgewählt (z.B. "Ze Carrige") -> deren eigener STEP-Name
            # wird zur Baugruppen-Bezeichnung, das Dialogfeld wird hier bewusst ignoriert.
            doc, root, comp_num = self._create_step_group(nodes[0], comp_num, shared_props)

        elif len(nodes) == 1 and nodes[0]["kind"] == "leaf" and len(nodes[0]["solids"]) > 1:
            # EIN Compound-Objekt ohne echte Unterstruktur/-namen -> die Dialog-Bezeichnung bildet
            # die Basis, durchnummeriert (bewährtes Verhalten für den einfachen Multi-Solid-Fall).
            part_infos = []
            for idx, (solid, src_label) in enumerate(nodes[0]["solids"], start=1):
                info, comp_num = self._create_step_part(
                    solid, f"{base_bezeichnung}_{idx:02d}", src_label, comp_num, shared_props
                )
                if info:
                    part_infos.append(info)
            doc, root, comp_num = self._wrap_as_assembly(part_infos, base_bezeichnung, comp_num, shared_props)

        else:
            # Mehrere Top-Level-Elemente (Leaves und/oder Gruppen gemischt, kein gemeinsamer
            # STEP-Gruppenname vorhanden) -> jedes Kind behält seinen eigenen Namen, die
            # Dialog-Bezeichnung dient nur als äußere Klammer, falls mehr als 1 Kind übrig bleibt.
            child_infos = []
            for node in nodes:
                child_doc, child_root, comp_num = self._create_step_node(node, comp_num, shared_props)
                if child_root is not None:
                    child_infos.append((child_doc, child_root))

            if not child_infos:
                raise RuntimeError("FCProject: Aus der STEP-Auswahl konnte keine verwertbare Geometrie erzeugt werden.")
            if len(child_infos) == 1:
                doc, root = child_infos[0]
            else:
                doc, root, comp_num = self._wrap_as_assembly(child_infos, base_bezeichnung, comp_num, shared_props)

        App.Console.PrintMessage(f"FCProject: STEP-Struktur als '{root.Label}' erfolgreich erstellt.\n")
        return doc.Name

    def _create_step_node(self, node, comp_num, shared_props):
        """Rekursiv: erzeugt aus einem Struktur-Knoten (Leaf-Objekt oder Gruppe) das passende
        PDM-Dokument - verwendet dabei IMMER den eigenen STEP-Namen des Knotens (im Gegensatz zum
        Sonderfall in _create_step_structure für ein einzelnes namenloses Compound-Objekt).
        Gibt (Dokument, Root-Objekt, nächste Teilnummer) zurück."""
        if node["kind"] == "group":
            return self._create_step_group(node, comp_num, shared_props)

        solids = node["solids"]
        if len(solids) == 1:
            solid, src_label = solids[0]
            info, comp_num = self._create_step_part(solid, node["label"], src_label, comp_num, shared_props)
            return (info[0], info[1], comp_num) if info else (None, None, comp_num)

        part_infos = []
        for idx, (solid, src_label) in enumerate(solids, start=1):
            info, comp_num = self._create_step_part(
                solid, f"{node['label']}_{idx:02d}", src_label, comp_num, shared_props
            )
            if info:
                part_infos.append(info)
        return self._wrap_as_assembly(part_infos, node["label"], comp_num, shared_props)

    def _create_step_group(self, node, comp_num, shared_props):
        """Erzeugt rekursiv alle Kinder einer Struktur-Gruppe und verlinkt sie in eine neue Baugruppe
        (Typ A) mit dem eigenen STEP-Namen der Gruppe als Bezeichnung."""
        children = node["children"]

        # SONDERFALL: Genau ein Kind, und das ist ein Blatt (kein Unter-Assembly). In strukturierten
        # STEP-Importen trägt oft die umschließende Gruppe den aussagekräftigen Namen, während ihr
        # einzelnes Geometrie-Kind nur einen generischen/internen Namen hat - z.B. Gruppe "Fixed Motor
        # Coupler 5x8 Y-Axis" mit einzigem Kind "Motor Coupler". Der Gruppen-Name gewinnt dann, statt
        # ihn beim Zusammenfalten (kein unnötiger Zwischen-Container) zu verlieren.
        if len(children) == 1 and children[0]["kind"] == "leaf":
            solids = children[0]["solids"]
            if len(solids) == 1:
                solid, src_label = solids[0]
                info, comp_num = self._create_step_part(solid, node["label"], src_label, comp_num, shared_props)
                return (info[0], info[1], comp_num) if info else (None, None, comp_num)

            part_infos = []
            for idx, (solid, src_label) in enumerate(solids, start=1):
                info, comp_num = self._create_step_part(
                    solid, f"{node['label']}_{idx:02d}", src_label, comp_num, shared_props
                )
                if info:
                    part_infos.append(info)
            return self._wrap_as_assembly(part_infos, node["label"], comp_num, shared_props)

        child_infos = []
        for child in children:
            child_doc, child_root, comp_num = self._create_step_node(child, comp_num, shared_props)
            if child_root is not None:
                child_infos.append((child_doc, child_root))

        if not child_infos:
            return None, None, comp_num
        if len(child_infos) == 1:
            # Übrig gebliebenes Einzel-Kind ist selbst schon ein fertiges (Unter-)Assembly/Teil ->
            # keine unnötige weitere Zwischen-Baugruppe.
            return child_infos[0][0], child_infos[0][1], comp_num

        return self._wrap_as_assembly(child_infos, node["label"], comp_num, shared_props)

    def _create_step_part(self, solid, bezeichnung, src_label, comp_num, shared_props):
        """Erzeugt ein einzelnes Kaufteil-Dokument (Typ B) aus einem fertig aufgelösten Solid.
        Gibt ((Dokument, Root-Objekt) oder None, nächste Teilnummer) zurück."""
        import FreeCAD as App

        part_props = dict(shared_props)
        part_props["Bezeichnung"] = bezeichnung
        part_props["__SingleSolidShape__"] = solid
        part_props["__SingleSolidLabel__"] = src_label

        # WICHTIG: Bezeichnungen aus echten STEP-Labels (z.B. "Motor Coupler") enthalten oft
        # Leerzeichen. FreeCAD sanitisiert Leerzeichen im internen Document-/Objekt-Name automatisch
        # weg, OHNE dass der von create_pdm_document zurückgegebene Anzeigename das widerspiegelt.
        # Ein direktes App.getDocument(anzeigename) würde deshalb mit "Unknown document" fehlschlagen -
        # stattdessen wird hier über die immer saubere ArticleID (PROJ_NNN_TYP) gesucht.
        expected_article_id = f"{self.project_name}_{comp_num}_B"
        self.create_pdm_document("B", comp_num, part_props)
        doc, root = self._find_by_article_id(expected_article_id)
        next_comp_num = self.get_next_available_number()

        if root is None:
            App.Console.PrintWarning(
                f"FCProject: Teil '{bezeichnung}' (ArticleID '{expected_article_id}') nach dem Anlegen "
                f"nicht gefunden - wird beim Verlinken übersprungen.\n"
            )
            return None, next_comp_num
        return (doc, root), next_comp_num

    def _wrap_as_assembly(self, part_infos, bezeichnung, comp_num, shared_props):
        """Erzeugt eine neue Baugruppe (Typ A) und verlinkt die übergebenen Teile/Unterbaugruppen hinein.
        Gibt (Dokument, Root-Objekt, nächste Teilnummer) zurück."""
        import FreeCAD as App

        asm_props = dict(shared_props)
        asm_props["Bezeichnung"] = bezeichnung

        expected_article_id = f"{self.project_name}_{comp_num}_A"
        self.create_pdm_document("A", comp_num, asm_props)
        asm_doc, asm_root = self._find_by_article_id(expected_article_id)
        next_comp_num = self.get_next_available_number()

        if asm_root is None:
            raise RuntimeError(f"FCProject: Baugruppe '{bezeichnung}' (ArticleID '{expected_article_id}') nach dem Anlegen nicht auffindbar.")

        self._link_parts_into_assembly(asm_doc, asm_root, part_infos)
        return asm_doc, asm_root, next_comp_num

    @staticmethod
    def _find_by_article_id(article_id):
        """Findet Dokument + Root-Objekt zu einer ArticleID robust über alle offenen Dokumente -
        unabhängig davon, ob FreeCAD den internen Document-/Objekt-Namen wegen Sonderzeichen in der
        Bezeichnung (z.B. Leerzeichen) automatisch umbenannt hat."""
        import FreeCAD as App

        for doc in App.listDocuments().values():
            for obj in doc.Objects:
                if getattr(obj, "ArticleID", None) == article_id:
                    return doc, obj
        return None, None

    @staticmethod
    def _link_parts_into_assembly(asm_doc, asm_root, part_infos):
        """Hängt die Root-Objekte der übergebenen Teil-Dokumente per App::Link in die Baugruppe ein.

        Wurde die Teil-Geometrie beim Anlegen auf einen lokalen Ursprung zentriert (Standard, siehe
        PurchasedPartCreator._build_single_body), trägt das Root-Objekt eine ImportOriginOffset-
        Property mit dem dabei entstandenen Versatz zur ursprünglichen STEP-Weltkoordinate - der
        Link bekommt genau diesen Versatz als Placement, damit die Baugruppe trotz zentrierter
        Einzelteile weiterhin an der richtigen Stelle zusammengesetzt erscheint."""
        import FreeCAD as App

        for part_doc, part_root in part_infos:
            link = asm_doc.addObject("App::Link", f"{part_root.Name}_Link")
            link.Label = part_root.Label
            link.LinkedObject = part_root
            offset = getattr(part_root, "ImportOriginOffset", None)
            if offset is not None:
                link.Placement = App.Placement(offset, App.Rotation())
            asm_root.addObject(link)

        asm_doc.recompute()
        asm_doc.save()
