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


def find_top_assembly(doc):
    """Findet das oberste Assembly::AssemblyObject in 'doc' (kein Elternteil ueber
    getParentGeoFeatureGroup()) - das ist das Objekt, auf das das neue App::Link zeigen soll,
    damit die komplette Baugruppe (nicht nur ein einzelnes Teil daraus) mitkommt. Faellt auf das
    erste Top-Level-Objekt zurueck, falls kein Assembly-Objekt gefunden wird (z.B. ein reines
    Einzelteil-Dokument ohne eigene Assembly)."""
    for obj in doc.Objects:
        if obj.TypeId == "Assembly::AssemblyObject" and obj.getParentGeoFeatureGroup() is None:
            return obj
    for obj in doc.Objects:
        if obj.getParentGeoFeatureGroup() is None and not obj.TypeId.startswith("App::Origin"):
            return obj
    return None


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


def make_import_component(active_doc, source_path):
    """Erstellt ein neues App::Link, das auf die oberste Assembly von 'source_path' zeigt -
    Placement bleibt UNGESPERRT, der Nutzer positioniert danach selbst. Landet als Mitglied der
    gerade aktiven Assembly (siehe find_active_assembly()), falls eine im Bearbeiten-Modus ist -
    sonst lose im Dokument-Root."""
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

    target = find_top_assembly(source_doc)
    if target is None:
        raise RuntimeError(f"Kein geeignetes Objekt in '{source_doc.Name}' gefunden.")

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
                'Pixmap': os.path.join(ICON_DIR, 'import_component.svg'),
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

            try:
                link = make_import_component(active_doc, path)
            except Exception as exc:
                QtWidgets.QMessageBox.warning(main_win, "FCProject", f"Import fehlgeschlagen: {exc}")
                return

            App.Console.PrintMessage(
                f"FCProject: '{link.Label}' importiert (App::Link, noch UNGESPERRT) - "
                "jetzt positionieren, danach mit demselben Knopf sperren.\n"
            )
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(link)

        def IsActive(self):
            return App.ActiveDocument is not None

    Gui.addCommand('FCProject_ImportComponent', CommandImportComponent())
