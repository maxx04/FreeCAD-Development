# FCProject: "Import"-Befehl fuer Option 2 der strategischen Kehrtwende vom 2026-08-27 (siehe
# project_fcproject_solver_data_fix_and_import_component-Memory).
#
# Kernidee (durch MinimalTestAppLinkImport.FCMacro bestaetigt, siehe
# patches/bugreport-nested-flex-joint-detach/): eine fertige Unterbaugruppe wird NICHT als
# flexible Assembly::AssemblyLink eingebunden (dort sitzt der ganze, diese Woche gefundene
# Verschachtelungs-Bug), sondern als ganz normales App::Link. Die Assembly-Solver-Logik
# unterscheidet nur bei Objekten, die von Assembly::AssemblyLink abstammen, ueberhaupt zwischen
# "flexibel"/"starr" (siehe getMovingPartFromRef() in AssemblyUtils.cpp) - ein simples App::Link
# faellt da komplett raus und wird automatisch wie ein einziger, undurchsichtiger Klotz
# behandelt, unabhaengig von der Verschachtelungstiefe darin. Bewusster Kompromiss: kein
# eigenstaendiges Ziehen/Kinematik-Verhalten fuer so importierte Teile - fuer eine korrekt
# zusammengebaute, STATISCHE Maschine (unser eigentliches Ziel) kein Nachteil.
#
# Zwei Modi je nach Auswahl:
# - Nichts oder etwas anderes ausgewaehlt: neue Import-Komponente anlegen (Datei auswaehlen,
#   App::Link im aktiven Dokument erstellen, Placement erstmal UNGESPERRT - der Nutzer
#   positioniert sie danach ganz normal, z.B. per Drag oder einem temporaeren Joint zu einem
#   bereits korrekten Nachbarn).
# - Eine bereits von uns angelegte Import-Komponente ausgewaehlt: Sperr-Status umschalten
#   (Placement.ReadOnly toggeln) - "fertig positioniert, jetzt einfrieren" bzw. umgekehrt
#   "nochmal neu positionieren wollen".
import os

import FreeCAD as App

try:
    import FreeCADGui as Gui
    _GUI_AVAILABLE = True
except ImportError:
    _GUI_AVAILABLE = False

import IconUtils

ICON_DIR = os.path.join(os.path.dirname(__file__), 'resources', 'icons')

MARKER_PROPERTY = "FCProjectImport"


def is_import_component(obj):
    return obj is not None and obj.TypeId == "App::Link" and hasattr(obj, MARKER_PROPERTY)


def set_placement_readonly(obj, value):
    """Sperrt/entsperrt Placement (und bei App::Link zusaetzlich LinkPlacement) - dieselbe
    Technik wie JointObject.GroundedJoint.setReadOnly() in FreeCADs eigenem Assembly-Modul."""
    tag = "ReadOnly" if value else "-ReadOnly"
    prop_list = obj.PropertiesList
    if "Placement" in prop_list:
        obj.setPropertyStatus("Placement", tag)
    if "LinkPlacement" in prop_list:
        obj.setPropertyStatus("LinkPlacement", tag)


def is_locked(obj):
    return "ReadOnly" in obj.getPropertyStatus("Placement")


def find_import_candidates(doc):
    """Objekte in 'doc', auf die ein Import-Link zeigen kann (alle ohne Elternteil ueber
    getParentGeoFeatureGroup()): zuerst die obersten Assembly::AssemblyObjects (damit die
    komplette Baugruppe mitkommt), sonst die PDM-Objekte (eigene ArticleID), sonst alle
    obersten Geometrie-Objekte (z.B. ein reines Einzelteil-Dokument ohne eigene Assembly).

    FCPROJECT-FIX (2026-11-24): Liste statt nur des ersten Treffers - liegen mehrere Objekte in
    einer Datei (gegen die Regel "in einer Datei nur ein Objekt", z.B. eine fremde Datei mit
    mehreren Koerpern), soll nicht still das erste importiert werden."""
    top = [o for o in doc.Objects if o.getParentGeoFeatureGroup() is None
           and not o.TypeId.startswith("App::Origin")]
    assemblies = [o for o in top if o.TypeId == "Assembly::AssemblyObject"]
    if assemblies:
        return assemblies
    pdm = [o for o in top if o.TypeId != "App::Link" and "ArticleID" in o.PropertiesList
           and getattr(o, "ArticleID", "")]
    if pdm:
        return pdm
    return [o for o in top if o.isDerivedFrom("App::GeoFeature")]


def find_top_assembly(doc):
    """Erstes Objekt aus find_import_candidates() (bisherige Schnittstelle)."""
    candidates = find_import_candidates(doc)
    return candidates[0] if candidates else None


def get_or_open_document(path):
    abspath = os.path.abspath(path)
    for doc in App.listDocuments().values():
        if doc.FileName and os.path.abspath(doc.FileName) == abspath:
            return doc
    return App.openDocument(abspath)


def find_active_assembly():
    """Liefert die gerade im Bearbeiten-Modus aktive Assembly (Doppelklick im Baum), falls
    vorhanden - sonst None. Nutzerwunsch (2026-08-27): der Import soll dann ALS MITGLIED dieser
    Assembly angelegt werden (wie ein normal eingefuegtes Teil), nicht lose im Dokument-Root
    landen, obwohl gerade eine bestimmte Baugruppe aktiv bearbeitet wird. Nutzt denselben
    nativen Mechanismus wie FreeCADs eigener CommandInsertLink."""
    try:
        import UtilsAssembly
        return UtilsAssembly.activeAssembly()
    except Exception as exc:
        App.Console.PrintWarning(f"FCProject: Aktive Baugruppe konnte nicht ermittelt werden: {exc}\n")
        return None


def make_import_component(active_doc, source_path, choose=None):
    """Erstellt ein neues App::Link, das auf die oberste Assembly von 'source_path' zeigt -
    Placement bleibt UNGESPERRT, der Nutzer positioniert danach selbst. Landet als Mitglied der
    gerade aktiven Assembly (siehe find_active_assembly()), falls eine im Bearbeiten-Modus ist -
    sonst lose im Dokument-Root.

    choose (2026-11-24): bietet die Datei mehrere Kandidaten (find_import_candidates()), waehlt
    choose(kandidaten) einen aus (None = abgebrochen, dann None zurueck). Ohne choose ist das
    ein Fehler mit der Kandidatenliste statt einer stillen Wahl des ersten."""
    # WICHTIG: die aktive Assembly VOR dem Oeffnen des Quelldokuments merken, nicht danach -
    # get_or_open_document()/App.openDocument() wechselt das aktive Dokument, und dieser
    # Dokumentwechsel beendet den Bearbeiten-Modus der gerade editierten Assembly (FreeCAD-
    # Kernverhalten, nicht rueckgaengig zu machen, indem man hinterher nur das Dokument
    # zurueckschaltet - der Bearbeiten-Modus selbst bleibt beendet). Ein erneuter
    # find_active_assembly()-Aufruf NACH dem Dokumentwechsel wuerde deshalb faelschlich None
    # liefern, obwohl der Nutzer gerade noch eine Baugruppe aktiv bearbeitet hat (siehe
    # Regression 2026-08-29: Import landete wieder lose im Dokument-Root).
    active_assembly = find_active_assembly()

    source_doc = get_or_open_document(source_path)

    # Aktives Dokument/Fenster sofort zurueck auf die Ziel-Baugruppe schalten (Nutzerwunsch
    # 2026-08-29): App.openDocument() aktiviert das neu geoeffnete Quelldokument automatisch mit
    # (wechselt auch sichtbar den GUI-Tab dorthin) - ungewollt, der Nutzer soll in der
    # Ziel-Baugruppe bleiben.
    App.setActiveDocument(active_doc.Name)
    if _GUI_AVAILABLE:
        Gui.ActiveDocument = Gui.getDocument(active_doc)

    candidates = find_import_candidates(source_doc)
    if not candidates:
        raise RuntimeError(f"Kein geeignetes Objekt in '{source_doc.Name}' gefunden.")
    target = candidates[0]
    if len(candidates) > 1:
        if choose is None:
            names = ", ".join(c.Label for c in candidates)
            raise RuntimeError(f"'{source_doc.Name}' enthaelt mehrere Objekte ({names}) - bitte eines waehlen.")
        target = choose(candidates)
        if target is None:
            return None

    if active_assembly is not None and active_assembly.Document is active_doc:
        link = active_assembly.newObject("App::Link", "Import")
    else:
        link = active_doc.addObject("App::Link", "Import")
    link.LinkedObject = target
    link.Label = f"Import: {target.Label}"
    link.addProperty(
        "App::PropertyBool", MARKER_PROPERTY, "FCProject",
        "Markiert dieses App::Link als FCProject-Import-Komponente (siehe ImportComponentCommand.py)"
    )
    setattr(link, MARKER_PROPERTY, True)

    active_doc.recompute()
    return link


if _GUI_AVAILABLE:
    class CommandImportComponent:
        """Siehe Modul-Kommentar oben fuer die volle Begruendung."""

        def GetResources(self):
            return {
                'Pixmap': IconUtils.icon_path(ICON_DIR, 'import_component.svg'),
                'MenuText': 'FCProject: Import-Komponente',
                'ToolTip': (
                    'Bindet eine fertige Unterbaugruppe als normales App::Link ein (statt einer '
                    'flexiblen Assembly::AssemblyLink) - dadurch komplett immun gegen den '
                    'verschachtelten-Baugruppen-Solver-Bug, weil der Solver ein App::Link '
                    'grundsaetzlich wie einen einzigen, starren Klotz behandelt.\n\n'
                    'Ohne Auswahl: neue Import-Komponente anlegen (Datei auswaehlen).\n'
                    'Mit einer bereits importierten Komponente ausgewaehlt: Sperr-Status '
                    '(Placement.ReadOnly) umschalten.'
                )
            }

        def Activated(self):
            from PySide6 import QtWidgets
            main_win = Gui.getMainWindow()
            sel = Gui.Selection.getSelection()

            if len(sel) == 1 and is_import_component(sel[0]):
                obj = sel[0]
                locked = is_locked(obj)
                set_placement_readonly(obj, not locked)
                obj.Document.recompute()
                state = "entsperrt - Position kann jetzt wieder geaendert werden" if locked else "gesperrt"
                App.Console.PrintMessage(f"FCProject: Import-Komponente '{obj.Label}' {state}.\n")
                return

            active_doc = App.ActiveDocument
            if active_doc is None:
                QtWidgets.QMessageBox.warning(main_win, "FCProject", "Kein aktives Dokument geoeffnet.")
                return

            # Startverzeichnis: das Projektverzeichnis der aktiven Datei (Nutzerwunsch,
            # 2026-08-29) statt des von Qt selbst gemerkten letzten Verzeichnisses - importierte
            # Unterbaugruppen liegen so gut wie immer im selben Projektordner.
            start_dir = os.path.dirname(active_doc.FileName) if active_doc.FileName else ""
            path, _ = QtWidgets.QFileDialog.getOpenFileName(
                main_win, "FCProject: Unterbaugruppe importieren", start_dir, "FreeCAD-Dateien (*.FCStd)"
            )
            if not path:
                return

            def choose(candidates):
                labels = [f"{c.Label} ({c.TypeId})" for c in candidates]
                item, ok = QtWidgets.QInputDialog.getItem(
                    main_win, "FCProject: Import-Komponente",
                    "Die Datei enthaelt mehrere Objekte. Welches soll eingebunden werden?",
                    labels, 0, False,
                )
                return candidates[labels.index(item)] if ok and item in labels else None

            try:
                link = make_import_component(active_doc, path, choose)
            except Exception as exc:
                QtWidgets.QMessageBox.warning(main_win, "FCProject", f"Import fehlgeschlagen: {exc}")
                return
            if link is None:
                return  # Auswahl abgebrochen

            App.Console.PrintMessage(
                f"FCProject: '{link.Label}' importiert (App::Link, noch UNGESPERRT) - "
                "jetzt positionieren, danach mit demselben Knopf sperren.\n"
            )
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(link)

        def IsActive(self):
            return App.ActiveDocument is not None

    Gui.addCommand('FCProject_ImportComponent', CommandImportComponent())
