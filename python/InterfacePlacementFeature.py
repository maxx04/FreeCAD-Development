# FCProject: "Interface-Positionierung" - erster Baustein des groesseren Interface-Konzepts
# (Referenzelemente Achse+Flaeche/LCS am Teil + Gegenelemente bei Einbau -> solver-freie
# Ausrichtung, siehe project_fcproject_interface_feature_concept-Memory), aufbauend auf der
# Import-Komponente aus ImportComponentCommand.py (2026-08-28, Nutzerentscheidung: "LCS als
# Interfaces Anfang" - statt eines eigenen Referenzelement-Systems nutzen wir FreeCADs eigenes,
# bewaehrtes Attachment-System (Part::LocalCoordinateSystem) als Referenzelement-Typ).
#
# Ablauf: der Nutzer legt in der QUELLE (dem zu importierenden Dokument) ein LCS an der
# gewuenschten Andock-Stelle an (per normalem FreeCAD-Attachment - Flaeche/Kante waehlen), und in
# der ZIEL-Baugruppe ein zweites LCS an der Gegenstelle. Dieser Befehl waehlt beide (erst Quelle,
# dann Ziel) aus und legt daraus ein ECHTES FeaturePython-Objekt ("InterfacePlacement") an, das
# bei JEDER Neuberechnung die Placement der Import-Komponente automatisch neu aus der aktuellen
# Lage beider LCS berechnet (Nutzerwunsch 2026-08-29: "Interfaces als Features haben die bei
# Neuberechnung auch aktualisiert werden" - Ablösung der fruehren reinen Einmal-Berechnung ohne
# gespeichertes Feature-Objekt). Kein lebendiger Joint, keine Solver-Abhaengigkeit - nur eine
# direkte geometrische Berechnung, die aber (anders als vorher) bei jedem Recompute automatisch
# neu ausgefuehrt wird, falls sich eine der beiden LCS verschoben hat.
import os

import FreeCAD as App

try:
    import FreeCADGui as Gui
    from PySide6 import QtWidgets
    _GUI_AVAILABLE = True
except ImportError:
    _GUI_AVAILABLE = False

ICON_DIR = os.path.join(os.path.dirname(__file__), 'resources', 'icons')

LCS_TYPE = "Part::LocalCoordinateSystem"


def find_import_component_for(active_doc, source_lcs):
    """Findet die (einzige) Import-Komponente in 'active_doc', deren LinkedObject im selben
    Dokument wie 'source_lcs' liegt - siehe ImportComponentCommand.py fuer die
    FCProjectImport-Markierung. Wirft eine aussagekraeftige Meldung statt eines stillen Fehlers,
    falls keine oder mehrere passen (spaetere Ausbaustufe: explizite Auswahl statt Auto-Erkennung)."""
    candidates = []
    for obj in active_doc.Objects:
        if obj.TypeId != "App::Link" or not hasattr(obj, "FCProjectImport"):
            continue
        linked = getattr(obj, "LinkedObject", None)
        if linked is not None and linked.Document is source_lcs.Document:
            candidates.append(obj)

    if not candidates:
        raise RuntimeError(
            f"Keine Import-Komponente in '{active_doc.Name}' gefunden, deren Quelle "
            f"'{source_lcs.Document.Name}' ist. Bitte zuerst per FCProject_ImportComponent "
            "importieren."
        )
    if len(candidates) > 1:
        names = ", ".join(c.Label for c in candidates)
        raise RuntimeError(
            f"Mehrere Import-Komponenten mit derselben Quelle gefunden ({names}) - "
            "Auto-Erkennung ist damit mehrdeutig. Bitte die betroffene Import-Komponente vorerst "
            "manuell eindeutig machen (z.B. umbenennen) oder diesen Befehl erweitern."
        )
    return candidates[0]


def find_interface_placement_for(import_link):
    """Findet ein bereits bestehendes InterfacePlacement-Feature fuer 'import_link', falls
    vorhanden - Nutzer soll beim erneuten Auswaehlen zweier LCS nicht versehentlich ein ZWEITES
    Feature anlegen, das gegen dasselbe Import-Objekt schreibt (zwei Features, die dieselbe
    ImportComponent.Placement setzen, wuerden sich in der Recompute-Reihenfolge gegenseitig
    ueberschreiben - nicht diagnostizierbar, welches zuletzt gewinnt)."""
    for obj in import_link.Document.Objects:
        if isinstance(getattr(obj, "Proxy", None), InterfacePlacementProxy):
            if getattr(obj, "ImportComponent", None) is import_link:
                return obj
    return None


class InterfacePlacementProxy:
    """Proxy fuer das InterfacePlacement-Feature (App::FeaturePython). Haelt Quell-/Ziel-LCS und
    die zu positionierende Import-Komponente als Eigenschaften und berechnet bei jeder
    Neuberechnung (execute()) die passende Placement neu - lebendig, nicht mehr nur einmalig."""

    def __init__(self, obj):
        self._add_properties(obj)
        obj.Proxy = self

    def _add_properties(self, obj):
        if not hasattr(obj, 'SourceLCS'):
            # PropertyXLink statt PropertyLink: die Quell-LCS liegt im PDM-Standardfall in einem
            # eigenen, per App::Link importierten Quelldokument (siehe SourceElement in
            # PatternFeatures.py/ReferencePlane in SectionSketchFeature.py - gleicher Grund).
            obj.addProperty(
                "App::PropertyXLink", "SourceLCS", "Interface",
                "LCS in der Quelle (Andock-Stelle am importierten Teil)"
            )
        if not hasattr(obj, 'TargetLCS'):
            obj.addProperty(
                "App::PropertyXLink", "TargetLCS", "Interface",
                "LCS im Ziel (Gegenstelle in der Baugruppe)"
            )
        if not hasattr(obj, 'ImportComponent'):
            # Hidden, wie Sketch in SectionSketchFeature.py: dieser Link ist rein informativ
            # ("wen positioniere ich") und darf NICHT in FreeCADs Abhaengigkeitsgraph auftauchen -
            # obj SCHREIBT in ImportComponent.Placement, haengt aber inhaltlich nicht von ihm ab.
            obj.addProperty(
                "App::PropertyLinkHidden", "ImportComponent", "Interface",
                "Zu positionierende Import-Komponente (App::Link, siehe ImportComponentCommand.py)",
                locked=True
            )
        if not hasattr(obj, 'Active'):
            obj.addProperty(
                "App::PropertyBool", "Active", "Interface",
                "Bei Bedarf abschalten, um die Neuberechnung bei jeder Baugruppen-Aktualisierung zu sparen"
            )
            obj.Active = True

    def onChanged(self, obj, prop):
        pass

    def execute(self, obj):
        if not obj.Active:
            return

        source_lcs = obj.SourceLCS
        target_lcs = obj.TargetLCS
        import_link = obj.ImportComponent

        if source_lcs is None or target_lcs is None:
            App.Console.PrintWarning(
                f"FCProject: InterfacePlacement '{obj.Label}' hat keine vollstaendigen "
                "LCS-Referenzen.\n"
            )
            return
        if import_link is None:
            App.Console.PrintWarning(
                f"FCProject: InterfacePlacement '{obj.Label}' hat keine ImportComponent.\n"
            )
            return

        # newImportPlacement * sourceLcsLocal = targetLcsGlobal
        # sourceLcsLocal ist die Placement der Quell-LCS OHNE die (noch zu berechnende) neue
        # Import-Placement - da source_lcs im Quelldokument selbst liegt (nicht gespiegelt durch
        # den Import-Link), ist ihre .Placement bereits genau das: die Placement relativ zum
        # Ursprung des Quelldokuments, unbeeinflusst von import_link.Placement.
        source_local = App.Placement(source_lcs.Placement)
        target_global = App.Placement(target_lcs.Placement)
        new_placement = target_global.multiply(source_local.inverse())

        if not import_link.Placement.isSame(new_placement, 1e-7, 1e-7):
            import_link.Placement = new_placement

    def onDocumentRestored(self, obj):
        self._add_properties(obj)
        obj.Proxy = self

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


if _GUI_AVAILABLE:
    class ViewProviderInterfacePlacement:
        def __init__(self, vobj):
            vobj.Proxy = self

        def attach(self, vobj):
            self.Object = vobj.Object

        def getIcon(self):
            return os.path.join(ICON_DIR, 'interface_position.svg')

        def doubleClicked(self, vobj):
            # Kein eigenes TaskPanel bisher - Doppelklick markiert zumindest die beiden
            # verwendeten LCS, damit man sie im Modellbaum wiederfindet.
            Gui.Selection.clearSelection()
            obj = vobj.Object
            if obj.SourceLCS is not None:
                Gui.Selection.addSelection(obj.SourceLCS)
            if obj.TargetLCS is not None:
                Gui.Selection.addSelection(obj.TargetLCS)
            return True

        def __getstate__(self):
            return None

        def __setstate__(self, state):
            return None


def find_active_assembly():
    try:
        import UtilsAssembly
        return UtilsAssembly.activeAssembly()
    except Exception as exc:
        App.Console.PrintWarning(f"FCProject: Aktive Baugruppe konnte nicht ermittelt werden: {exc}\n")
        return None


def make_interface_placement(active_doc, import_link, source_lcs, target_lcs):
    """Erstellt (oder aktualisiert, falls fuer 'import_link' schon eines existiert) das
    InterfacePlacement-Feature und stoesst danach ein Recompute an, das execute() sofort einmal
    ausfuehrt."""
    existing = find_interface_placement_for(import_link)
    if existing is not None:
        existing.SourceLCS = source_lcs
        existing.TargetLCS = target_lcs
        active_doc.recompute()
        return existing, True

    active_doc.openTransaction("FCProject Interface Placement")
    try:
        obj = active_doc.addObject("App::FeaturePython", "InterfacePlacement")
        obj.Label = f"Interface: {import_link.Label}"
        InterfacePlacementProxy(obj)
        obj.SourceLCS = source_lcs
        obj.TargetLCS = target_lcs
        obj.ImportComponent = import_link

        active_assembly = find_active_assembly()
        if active_assembly is not None and active_assembly.Document is active_doc:
            active_assembly.addObject(obj)

        if _GUI_AVAILABLE and obj.ViewObject:
            ViewProviderInterfacePlacement(obj.ViewObject)

        active_doc.recompute()
        active_doc.commitTransaction()
        return obj, False
    except Exception:
        active_doc.abortTransaction()
        raise


if _GUI_AVAILABLE:
    class CommandPositionByInterface:
        def GetResources(self):
            return {
                'Pixmap': os.path.join(ICON_DIR, 'interface_position.svg'),
                'MenuText': 'FCProject: Nach Interface positionieren',
                'ToolTip': (
                    'Legt ein InterfacePlacement-Feature an, das eine Import-Komponente anhand '
                    'zweier lokaler Koordinatensysteme (LCS) ausrichtet - erst das LCS in der '
                    'Quelle (Andock-Stelle am importierten Teil), dann das LCS im Ziel '
                    '(Gegenstelle in der Baugruppe) auswaehlen. Aktualisiert sich bei jeder '
                    'Neuberechnung automatisch mit, falls sich eine der beiden LCS verschiebt '
                    '(ueber "Active" abschaltbar) - keine laufende Solver-Abhaengigkeit sonst.'
                )
            }

        def Activated(self):
            main_win = Gui.getMainWindow()
            sel = Gui.Selection.getSelection()

            if len(sel) != 2:
                QtWidgets.QMessageBox.warning(
                    main_win, "FCProject",
                    "Bitte genau zwei LCS auswaehlen: erst die Quell-LCS (am zu importierenden "
                    "Teil), dann die Ziel-LCS (in der Baugruppe)."
                )
                return

            source_lcs, target_lcs = sel[0], sel[1]
            for obj, role in ((source_lcs, "Quell"), (target_lcs, "Ziel")):
                if obj.TypeId != LCS_TYPE:
                    QtWidgets.QMessageBox.warning(
                        main_win, "FCProject",
                        f"'{obj.Label}' ist kein Local Coordinate System (erwartet als "
                        f"{role}-LCS)."
                    )
                    return

            active_doc = App.ActiveDocument
            if active_doc is None:
                QtWidgets.QMessageBox.warning(main_win, "FCProject", "Kein aktives Dokument geoeffnet.")
                return

            try:
                import_link = find_import_component_for(active_doc, source_lcs)
                feature, was_update = make_interface_placement(
                    active_doc, import_link, source_lcs, target_lcs
                )
            except Exception as exc:
                QtWidgets.QMessageBox.warning(main_win, "FCProject", str(exc))
                return

            verb = "aktualisiert" if was_update else "angelegt"
            App.Console.PrintMessage(
                f"FCProject: InterfacePlacement '{feature.Label}' {verb} "
                f"('{source_lcs.Label}' -> '{target_lcs.Label}'), '{import_link.Label}' neu "
                f"positioniert: {import_link.Placement}.\n"
            )

        def IsActive(self):
            return App.ActiveDocument is not None

    Gui.addCommand('FCProject_PositionByInterface', CommandPositionByInterface())
