# FCProject: "Interface" - sichtbares Objekt (aehnlich einem Joint), das ein Teil an einer fest
# vorgegebenen Placement haelt.
#
# Hintergrund (2026-08-23, Nutzer-Konzept): der native Assembly-Solver ist bei mehrfach
# verschachtelten flexiblen Baugruppen nachweislich fehlerhaft (siehe patches/README.md,
# "GroundedJoint/RigidGroupJoint verschwindet bei verschachtelter flexibler Baugruppe") - statt
# darauf zu warten/hoffen, dass er die richtige Position selbst findet, wird sie hier einmal
# manuell festgelegt (siehe ManualPlacementCommand.py) und dann durch dieses Objekt aktiv
# GEGEN den Solver verteidigt.
#
# Anders als eine reine "Placement schreibgeschuetzt"-Markierung (die der Solver theoretisch
# durch Auf-/Zusperren waehrend seines eigenen Ablaufs umgehen koennte) erzwingt Interface
# seinen Wert ZUSAETZLICH aktiv ueber DocObserver.py's slotRecomputedDocument()-Hook, der erst
# NACH dem kompletten Dokument-Recompute (inklusive eines eventuell gelaufenen Assembly-Solves)
# feuert - das Interface hat damit garantiert das letzte Wort, unabhaengig von der internen
# Reihenfolge des Solvers.
import os

import FreeCAD as App

try:
    import FreeCADGui as Gui
    _GUI_AVAILABLE = True
except ImportError:
    _GUI_AVAILABLE = False

ICON_DIR = os.path.join(os.path.dirname(__file__), 'resources', 'icons')

# FCPROJECT-FEATURE (2026-08-23, Nutzerwunsch): an genau diesem Tag mehrfach echte Arbeit
# verloren gegangen, weil ein erfolgreicher RestoreRigidGroupCommand/RestoreJointPositionCommand-
# Lauf im Speicher korrekt aussah, aber nicht per Strg+S gespeichert wurde - ein spaeterer
# "Reload partial document"-Vorgang (ausgeloest durch eine ANDERE, separat gespeicherte Datei)
# hat den ungespeicherten Stand dann stillschweigend verworfen und durch die alte Version
# ersetzt. Deshalb speichern make_interface()-basierte Werkzeuge das betroffene Dokument jetzt
# automatisch. ABSCHALTBAR ueber FreeCADs eigenen Parameter-Editor (Werkzeuge -> Parameter
# bearbeiten, oder Bearbeiten -> Einstellungen falls dort verdrahtet) unter:
#   BaseApp/Preferences/Mod/FCProject -> AutoSaveAfterRestore (Bool) -> auf false setzen.
# Default: true (an).
AUTO_SAVE_PARAM_GROUP = "User parameter:BaseApp/Preferences/Mod/FCProject"
AUTO_SAVE_PARAM_NAME = "AutoSaveAfterRestore"


def auto_save_document(doc, reason=""):
    """Speichert 'doc' automatisch, falls AutoSaveAfterRestore nicht explizit auf false gesetzt
    wurde (siehe Modul-Kommentar oben fuer die volle Begruendung) - und nur, wenn das Dokument
    bereits einen Dateinamen hat (neue, nie gespeicherte Dokumente werden nicht automatisch unter
    einem geratenen Namen abgelegt)."""
    enabled = App.ParamGet(AUTO_SAVE_PARAM_GROUP).GetBool(AUTO_SAVE_PARAM_NAME, True)
    if not enabled:
        App.Console.PrintMessage(
            f"FCProject: Auto-Speichern uebersprungen (AutoSaveAfterRestore=false) fuer "
            f"'{doc.Name}'{' - ' + reason if reason else ''}.\n"
        )
        return
    if not doc.FileName:
        App.Console.PrintWarning(
            f"FCProject: Auto-Speichern uebersprungen - '{doc.Name}' wurde noch nie gespeichert "
            "(kein Dateiname bekannt).\n"
        )
        return
    try:
        doc.save()
        App.Console.PrintMessage(
            f"FCProject: '{doc.Name}' automatisch gespeichert"
            f"{' (' + reason + ')' if reason else ''}.\n"
        )
    except Exception as exc:
        App.Console.PrintWarning(f"FCProject: Auto-Speichern von '{doc.Name}' fehlgeschlagen: {exc}\n")


def set_placement_readonly(obj, value):
    """Sperrt/entsperrt Placement (und bei App::Link zusaetzlich LinkPlacement) - dieselbe
    Technik wie JointObject.GroundedJoint.setReadOnly() in FreeCADs eigenem Assembly-Modul.
    Dupliziert (statt importiert) aus ManualPlacementCommand.py, um beide Module unabhaengig
    voneinander benutzbar zu halten."""
    tag = "ReadOnly" if value else "-ReadOnly"
    prop_list = obj.PropertiesList
    if "Placement" in prop_list:
        obj.setPropertyStatus("Placement", tag)
    if "LinkPlacement" in prop_list:
        obj.setPropertyStatus("LinkPlacement", tag)


def enforce_all_interfaces(doc):
    """Setzt fuer JEDES Interface-Objekt in 'doc' die gespeicherte LockedPlacement erneut auf
    dessen TargetObject durch - aufgerufen aus DocObserver.slotRecomputedDocument(), also nach
    jedem vollstaendigen Recompute. Reine Eigenschaftszuweisung, kein weiterer recompute()-Aufruf
    hier (sonst Rekursionsgefahr ueber signalRecomputed erneut)."""
    for obj in doc.Objects:
        if obj.TypeId != "App::FeaturePython" or not hasattr(obj, "LockedPlacement"):
            continue
        target = getattr(obj, "TargetObject", None)
        if target is None:
            continue
        try:
            if target.Placement != obj.LockedPlacement:
                set_placement_readonly(target, False)
                target.Placement = obj.LockedPlacement
                # FreeCAD kennt die Rueckwaerts-Abhaengigkeit Interface->Ziel nicht (ein
                # PropertyLink bedeutet fuer FreeCADs Abhaengigkeitsgraph normalerweise "ich
                # haenge vom Ziel ab", nicht umgekehrt) - das Ziel bleibt nach dieser Zuweisung
                # "touched" haengen und FreeCAD meldet "still touched after recompute"
                # (Document.cpp), obwohl der Wert korrekt gesetzt wurde. purgeTouched() raeumt das
                # explizit auf - gleiche Technik wie im FreeCAD-eigenen Assembly-Code beim
                # Durchsetzen von geerdeten Placements.
                target.purgeTouched()
            set_placement_readonly(target, True)
        except Exception as exc:
            App.Console.PrintWarning(
                f"FCProject: Interface '{obj.Label}' konnte nicht durchgesetzt werden: {exc}\n"
            )


class InterfaceProxy:
    """Proxy fuer ein Interface-Objekt (App::FeaturePython)."""

    def __init__(self, obj):
        self._add_properties(obj)
        obj.Proxy = self

    def _add_properties(self, obj):
        if not hasattr(obj, 'TargetObject'):
            # App::PropertyLinkGlobal statt PropertyLink (2026-08-23-Fix): das Interface-Objekt
            # liegt meist im Top-Level-Dokument, das Zielobjekt aber innerhalb einer geerdeten
            # Unterbaugruppe (anderer Scope) - mit einfachem PropertyLink meldet FreeCAD "links
            # are out of scope" und die betroffenen Objekte bleiben nach dem Recompute dauerhaft
            # "touched". Gleiche Ursache/Loesung wie bei ObjectToGround/ObjectsToRigidGroup im
            # FreeCAD-Kern (siehe patches/README.md).
            obj.addProperty(
                "App::PropertyLinkGlobal", "TargetObject", "Interface",
                "Das Teil, dessen Placement hier fest vorgegeben wird"
            )
        if not hasattr(obj, 'LockedPlacement'):
            obj.addProperty(
                "App::PropertyPlacement", "LockedPlacement", "Interface",
                "Die fest vorgegebene Placement - wird nach jeder Neuberechnung erneut auf "
                "TargetObject angewendet, unabhaengig davon, was der Assembly-Solver berechnet"
            )
        if not hasattr(obj, 'Note'):
            obj.addProperty(
                "App::PropertyString", "Note", "Interface",
                "Freitext, z.B. woher die Placement uebernommen wurde"
            )

    def execute(self, obj):
        # Erster, "normaler" Durchsetzungsversuch im regulaeren Recompute-Ablauf - reicht
        # alleine NICHT (der Assembly-Solve kann je nach Abhaengigkeitsreihenfolge NACH diesem
        # Aufruf laufen und die Placement wieder ueberschreiben), deshalb zusaetzlich
        # enforce_all_interfaces() ueber den DocObserver-Hook nach dem GESAMTEN Recompute.
        target = obj.TargetObject
        if target is None:
            App.Console.PrintWarning(f"FCProject: Interface '{obj.Label}' hat kein TargetObject.\n")
            return
        set_placement_readonly(target, False)
        target.Placement = obj.LockedPlacement
        target.purgeTouched()  # siehe enforce_all_interfaces() fuer die Begruendung
        set_placement_readonly(target, True)

    def onDocumentRestored(self, obj):
        self._add_properties(obj)
        obj.Proxy = self

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


if _GUI_AVAILABLE:
    class ViewProviderInterface:
        def __init__(self, vobj):
            vobj.Proxy = self

        def attach(self, vobj):
            self.Object = vobj.Object

        def getIcon(self):
            return os.path.join(ICON_DIR, 'interface.svg')

        def doubleClicked(self, vobj):
            target = getattr(vobj.Object, "TargetObject", None)
            if target is not None:
                Gui.Selection.clearSelection()
                Gui.Selection.addSelection(target)
            return True

        def __getstate__(self):
            return None

        def __setstate__(self, state):
            return None


def find_interface_for(doc, target):
    """Findet das bestehende Interface-Objekt fuer 'target' in 'doc', falls vorhanden - sonst
    None. Fuer Werkzeuge, die ein bereits gesperrtes Teil NICHT ungefragt ueberschreiben wollen
    (siehe RestoreJointPositionCommand.py: ein Anker kann ueber mehrere Joints gleichzeitig an
    bereits korrekt positionierte Teile grenzen - ohne diese Pruefung wuerde ein spaeterer,
    weniger autoritativer Anker ein zuvor korrekt gesetztes Teil wieder ueberschreiben)."""
    for obj in doc.Objects:
        if obj.TypeId == "App::FeaturePython" and hasattr(obj, "TargetObject") and hasattr(obj, "LockedPlacement"):
            if obj.TargetObject is target:
                return obj
    return None


def make_interface(doc, target, placement, note=""):
    """Erstellt ein neues Interface-Objekt fuer 'target' mit der gegebenen Placement. Falls fuer
    'target' bereits ein Interface existiert, wird DIESES aktualisiert statt ein zweites
    anzulegen (ein Teil soll nicht durch mehrere Interfaces gleichzeitig 'verteidigt' werden -
    das waere ein Widerspruch in sich)."""
    for obj in doc.Objects:
        if obj.TypeId == "App::FeaturePython" and hasattr(obj, "TargetObject") and hasattr(obj, "LockedPlacement"):
            if obj.TargetObject is target:
                obj.LockedPlacement = placement
                if note:
                    obj.Note = note
                doc.recompute()
                return obj

    obj = doc.addObject("App::FeaturePython", "Interface")
    obj.Label = f"Interface: {target.Label}"
    InterfaceProxy(obj)
    obj.TargetObject = target
    obj.LockedPlacement = placement
    obj.Note = note

    if _GUI_AVAILABLE and obj.ViewObject:
        ViewProviderInterface(obj.ViewObject)

    doc.recompute()
    return obj


if _GUI_AVAILABLE:
    class CommandCreateInterface:
        """Befehl: sperrt das AKTUELLE Placement des ausgewaehlten Teils per Interface-Objekt -
        ohne erst das Placement-Panel (ManualPlacementCommand.py) zu oeffnen. Fuer den Fall, dass
        die Position schon stimmt und nur noch gegen den (bei verschachtelten flexiblen
        Baugruppen fehlerhaften) Assembly-Solver abgesichert werden soll."""

        def GetResources(self):
            return {
                'Pixmap': os.path.join(ICON_DIR, 'interface.svg'),
                'MenuText': 'FCProject: Interface (Placement sperren)',
                'ToolTip': (
                    'Sperrt das aktuelle Placement des ausgewaehlten Teils dauerhaft per '
                    'sichtbarem Interface-Objekt - haelt es auch gegen einen fehlerhaften '
                    'Assembly-Solver fest, ohne das Placement-Panel oeffnen zu muessen.'
                )
            }

        def Activated(self):
            from PySide6 import QtWidgets
            main_win = Gui.getMainWindow()
            sel = Gui.Selection.getSelection()
            if len(sel) != 1:
                QtWidgets.QMessageBox.warning(main_win, "FCProject", "Bitte genau ein Teil auswaehlen.")
                return
            obj = sel[0]

            active_doc = App.ActiveDocument
            if active_doc is not None:
                # Gleiche Mirror-Aufloesung wie in ManualPlacementCommand.py - siehe dort fuer
                # die volle Begruendung (rohes Quellobjekt vs. lokales Mirror-Objekt).
                try:
                    import ManualPlacementCommand
                    mirror = ManualPlacementCommand._find_local_mirror(active_doc, obj)
                    if mirror is not None and mirror is not obj:
                        App.Console.PrintMessage(
                            f"FCProject: Auswahl '{obj.Label}' gehoert zum Quelldokument von "
                            f"Mirror-Objekt '{mirror.Label}' in '{active_doc.Name}' - verwende "
                            "dieses.\n"
                        )
                        obj = mirror
                except Exception as exc:
                    App.Console.PrintWarning(f"FCProject: Mirror-Aufloesung fehlgeschlagen: {exc}\n")

            if not hasattr(obj, "Placement"):
                QtWidgets.QMessageBox.warning(
                    main_win, "FCProject", f"'{obj.Label}' hat keine Placement-Eigenschaft."
                )
                return

            make_interface(
                obj.Document, obj, App.Placement(obj.Placement),
                note="Aktuelles Placement gesperrt ueber FCProject_CreateInterface"
            )
            auto_save_document(obj.Document, reason=f"Interface fuer '{obj.Label}' gesperrt")

        def IsActive(self):
            return App.ActiveDocument is not None

    Gui.addCommand('FCProject_CreateInterface', CommandCreateInterface())
