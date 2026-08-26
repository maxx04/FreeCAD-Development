# FCProject: "PlacementGuard" - sichtbares Objekt (aehnlich einem Joint), das ein Teil an einer
# fest vorgegebenen Placement haelt.
#
# Umbenannt (2026-08-24) von "Interface" - der Nutzer hat ein groesseres, eigenes "Interface"-
# Konzept vor (Referenzelemente Achse+Flaeche am Teil + Gegenelemente bei Einbau -> solver-freie
# Einmal-Ausrichtung, siehe project_fcproject_interface_feature_concept-Memory), das den Namen
# "Interface" eigentlich fuer sich beansprucht. Diese Klasse hier macht etwas Kleineres/Anderes:
# sie "bewacht" (guard) eine bereits bekannte Placement aktiv gegen den Solver, verteidigt sie
# also, statt eine neue zu berechnen.
#
# Kein Kompatibilitaets-Stub (Nutzerentscheidung 2026-08-24): die alte Datei InterfaceFeature.py
# wurde ersatzlos geloescht statt als Alias-Stub weitergefuehrt - bereits gespeicherte
# "Interface"-Objekte in echten Projektdateien werden vom Nutzer manuell geloescht/neu angelegt,
# statt sie ueber einen Kompat-Layer weiter zu unterstuetzen.
#
# Hintergrund (2026-08-23, Nutzer-Konzept): der native Assembly-Solver ist bei mehrfach
# verschachtelten flexiblen Baugruppen nachweislich fehlerhaft (siehe patches/README.md,
# "GroundedJoint/RigidGroupJoint verschwindet bei verschachtelter flexibler Baugruppe") - statt
# darauf zu warten/hoffen, dass er die richtige Position selbst findet, wird sie hier einmal
# manuell festgelegt (siehe ManualPlacementCommand.py) und dann durch dieses Objekt aktiv
# GEGEN den Solver verteidigt.
#
# Anders als eine reine "Placement schreibgeschuetzt"-Markierung (die der Solver theoretisch
# durch Auf-/Zusperren waehrend seines eigenen Ablaufs umgehen koennte) erzwingt PlacementGuard
# seinen Wert ZUSAETZLICH aktiv ueber DocObserver.py's slotRecomputedDocument()-Hook, der erst
# NACH dem kompletten Dokument-Recompute (inklusive eines eventuell gelaufenen Assembly-Solves)
# feuert - der Guard hat damit garantiert das letzte Wort, unabhaengig von der internen
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
# ersetzt. Deshalb speichern make_placement_guard()-basierte Werkzeuge das betroffene Dokument
# jetzt automatisch. ABSCHALTBAR ueber FreeCADs eigenen Parameter-Editor (Werkzeuge -> Parameter
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


def enforce_all_placement_guards(doc):
    """Setzt fuer JEDES PlacementGuard-Objekt in 'doc' die gespeicherte LockedPlacement erneut
    auf dessen TargetObject durch - aufgerufen aus DocObserver.slotRecomputedDocument(), also
    nach jedem vollstaendigen Recompute. Reine Eigenschaftszuweisung, kein weiterer
    recompute()-Aufruf hier (sonst Rekursionsgefahr ueber signalRecomputed erneut)."""
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
                # FreeCAD kennt die Rueckwaerts-Abhaengigkeit PlacementGuard->Ziel nicht (ein
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
                f"FCProject: PlacementGuard '{obj.Label}' konnte nicht durchgesetzt werden: {exc}\n"
            )


class PlacementGuardProxy:
    """Proxy fuer ein PlacementGuard-Objekt (App::FeaturePython)."""

    def __init__(self, obj):
        self._add_properties(obj)
        obj.Proxy = self

    def _add_properties(self, obj):
        if not hasattr(obj, 'TargetObject'):
            # App::PropertyLinkGlobal statt PropertyLink (2026-08-23-Fix): das PlacementGuard-
            # Objekt liegt meist im Top-Level-Dokument, das Zielobjekt aber innerhalb einer
            # geerdeten Unterbaugruppe (anderer Scope) - mit einfachem PropertyLink meldet
            # FreeCAD "links are out of scope" und die betroffenen Objekte bleiben nach dem
            # Recompute dauerhaft "touched". Gleiche Ursache/Loesung wie bei
            # ObjectToGround/ObjectsToRigidGroup im FreeCAD-Kern (siehe patches/README.md).
            obj.addProperty(
                "App::PropertyLinkGlobal", "TargetObject", "PlacementGuard",
                "Das Teil, dessen Placement hier fest vorgegeben wird"
            )
        if not hasattr(obj, 'LockedPlacement'):
            obj.addProperty(
                "App::PropertyPlacement", "LockedPlacement", "PlacementGuard",
                "Die fest vorgegebene Placement - wird nach jeder Neuberechnung erneut auf "
                "TargetObject angewendet, unabhaengig davon, was der Assembly-Solver berechnet"
            )
        if not hasattr(obj, 'Note'):
            obj.addProperty(
                "App::PropertyString", "Note", "PlacementGuard",
                "Freitext, z.B. woher die Placement uebernommen wurde"
            )

    def execute(self, obj):
        # Erster, "normaler" Durchsetzungsversuch im regulaeren Recompute-Ablauf - reicht
        # alleine NICHT (der Assembly-Solve kann je nach Abhaengigkeitsreihenfolge NACH diesem
        # Aufruf laufen und die Placement wieder ueberschreiben), deshalb zusaetzlich
        # enforce_all_placement_guards() ueber den DocObserver-Hook nach dem GESAMTEN Recompute.
        target = obj.TargetObject
        if target is None:
            App.Console.PrintWarning(f"FCProject: PlacementGuard '{obj.Label}' hat kein TargetObject.\n")
            return
        set_placement_readonly(target, False)
        target.Placement = obj.LockedPlacement
        target.purgeTouched()  # siehe enforce_all_placement_guards() fuer die Begruendung
        set_placement_readonly(target, True)

    def onDocumentRestored(self, obj):
        self._add_properties(obj)
        obj.Proxy = self

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


if _GUI_AVAILABLE:
    class ViewProviderPlacementGuard:
        def __init__(self, vobj):
            vobj.Proxy = self

        def attach(self, vobj):
            self.Object = vobj.Object

        def getIcon(self):
            return os.path.join(ICON_DIR, 'placement_guard.svg')

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


def ensure_placement_guard_group(doc):
    """Liefert die (bei Bedarf neu angelegte) 'PlacementGuards'-Gruppe in 'doc' - fasst alle neu
    erstellten PlacementGuard-Objekte an einer Stelle im Baum zusammen, analog zur nativen
    'Joints'-Gruppe einer Assembly (Nutzerwunsch 2026-08-26). Bereits VOR dieser Aenderung
    angelegte Guards bleiben dort stehen, wo sie sind - find_placement_guard_for()/
    enforce_all_placement_guards() suchen ohnehin ueber alle doc.Objects, unabhaengig von der
    Gruppenzugehoerigkeit."""
    for obj in doc.Objects:
        if obj.TypeId == "App::DocumentObjectGroup" and obj.Name == "PlacementGuards":
            return obj
    group = doc.addObject("App::DocumentObjectGroup", "PlacementGuards")
    group.Label = "PlacementGuards"
    return group


def find_placement_guard_for(doc, target):
    """Findet das bestehende PlacementGuard-Objekt fuer 'target' in 'doc', falls vorhanden -
    sonst None. Fuer Werkzeuge, die ein bereits gesperrtes Teil NICHT ungefragt ueberschreiben
    wollen (siehe RestoreJointPositionCommand.py: ein Anker kann ueber mehrere Joints
    gleichzeitig an bereits korrekt positionierte Teile grenzen - ohne diese Pruefung wuerde ein
    spaeterer, weniger autoritativer Anker ein zuvor korrekt gesetztes Teil wieder
    ueberschreiben)."""
    for obj in doc.Objects:
        if obj.TypeId == "App::FeaturePython" and hasattr(obj, "TargetObject") and hasattr(obj, "LockedPlacement"):
            if obj.TargetObject is target:
                return obj
    return None


def make_placement_guard(doc, target, placement, note=""):
    """Erstellt ein neues PlacementGuard-Objekt fuer 'target' mit der gegebenen Placement. Falls
    fuer 'target' bereits ein PlacementGuard existiert, wird DIESER aktualisiert statt ein
    zweiter angelegt (ein Teil soll nicht durch mehrere Guards gleichzeitig 'verteidigt' werden -
    das waere ein Widerspruch in sich)."""
    existing = find_placement_guard_for(doc, target)
    if existing is not None:
        existing.LockedPlacement = placement
        if note:
            existing.Note = note
        doc.recompute()
        return existing

    obj = doc.addObject("App::FeaturePython", "PlacementGuard")
    obj.Label = f"PlacementGuard: {target.Label}"
    PlacementGuardProxy(obj)
    obj.TargetObject = target
    obj.LockedPlacement = placement
    obj.Note = note

    if _GUI_AVAILABLE and obj.ViewObject:
        ViewProviderPlacementGuard(obj.ViewObject)

    ensure_placement_guard_group(doc).addObject(obj)

    doc.recompute()
    return obj


# Objekttypen, die beim Baugruppen-Modus (siehe CommandCreatePlacementGuard._guard_assembly())
# NICHT als "Komponente" gezaehlt werden - Ursprungs-Hilfselemente, native Joint/View-Gruppen
# und unsere eigene PlacementGuards-Gruppe selbst.
_ASSEMBLY_MEMBER_SKIP_TYPES = {
    "App::Origin", "App::Line", "App::Plane", "App::Point",
    "Assembly::JointGroup", "Assembly::ViewGroup", "App::DocumentObjectGroup",
}


if _GUI_AVAILABLE:
    class CommandCreatePlacementGuard:
        """Befehl: sperrt das AKTUELLE Placement des ausgewaehlten Teils per PlacementGuard-
        Objekt - ohne erst das Placement-Panel (ManualPlacementCommand.py) zu oeffnen. Fuer den
        Fall, dass die Position schon stimmt und nur noch gegen den (bei verschachtelten
        flexiblen Baugruppen fehlerhaften) Assembly-Solver abgesichert werden soll.

        Baugruppen-Modus (Nutzerwunsch 2026-08-26): ist die Auswahl statt eines einzelnen Teils
        eine ganze Assembly (Assembly::AssemblyObject oder Assembly::AssemblyLink), wird fuer
        JEDES direkte Mitglied ein eigener PlacementGuard erstellt/aktualisiert - automatisiert
        genau den zuvor manuellen "jedes Teil einzeln anklicken"-Ablauf fuer eine bereits korrekt
        zusammengebaute Unterbaugruppe. Geht bewusst nur EINE Ebene tief (keine Rekursion in
        verschachtelte Sub-Baugruppen) - fuer eine tiefer verschachtelte Sub-Baugruppe wird der
        Befehl einfach ein zweites Mal auf DEREN Assembly-Knoten ausgefuehrt, genau wie beim
        bisherigen manuellen Vorgehen Ebene fuer Ebene."""

        def GetResources(self):
            return {
                'Pixmap': os.path.join(ICON_DIR, 'placement_guard.svg'),
                'MenuText': 'FCProject: PlacementGuard (Placement sperren)',
                'ToolTip': (
                    'Sperrt das aktuelle Placement des ausgewaehlten Teils dauerhaft per '
                    'sichtbarem PlacementGuard-Objekt - haelt es auch gegen einen fehlerhaften '
                    'Assembly-Solver fest, ohne das Placement-Panel oeffnen zu muessen. Bei '
                    'Auswahl einer ganzen Baugruppe: erstellt einen Guard fuer JEDES ihrer '
                    'direkten Mitglieder auf einmal.'
                )
            }

        def Activated(self):
            from PySide6 import QtWidgets
            main_win = Gui.getMainWindow()
            sel = Gui.Selection.getSelection()
            if len(sel) != 1:
                QtWidgets.QMessageBox.warning(
                    main_win, "FCProject", "Bitte genau ein Teil oder eine Baugruppe auswaehlen."
                )
                return
            obj = sel[0]

            if obj.TypeId in ("Assembly::AssemblyObject", "Assembly::AssemblyLink"):
                self._guard_assembly(obj)
                return

            self._guard_single_part(obj)

        def _guard_single_part(self, obj):
            from PySide6 import QtWidgets
            main_win = Gui.getMainWindow()

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

            make_placement_guard(
                obj.Document, obj, App.Placement(obj.Placement),
                note="Aktuelles Placement gesperrt ueber FCProject_CreatePlacementGuard"
            )
            auto_save_document(obj.Document, reason=f"PlacementGuard fuer '{obj.Label}' gesperrt")

        def _guard_assembly(self, assembly):
            doc = assembly.Document
            members = getattr(assembly, "Group", None) or []

            created, already_locked, skipped = [], [], []
            for member in members:
                if member is None or member.TypeId in _ASSEMBLY_MEMBER_SKIP_TYPES:
                    continue
                if not hasattr(member, "Placement"):
                    skipped.append(f"{member.Label} (keine Placement-Eigenschaft)")
                    continue

                # WICHTIG (Nutzerentscheidung 2026-08-26): bereits gesperrte Teile NICHT
                # anfassen/aktualisieren - gleiches Prinzip wie in RestoreJointPositionCommand.py
                # (siehe dort fuer die volle Begruendung). Ein bereits vorhandener Guard gilt als
                # autoritativ (z.B. praeziser ueber RestoreRigidGroupCommand/
                # RestoreJointPositionCommand berechnet statt nur "aktuelle Placement uebernommen")
                # - dieser Befehl soll nur LUECKEN fuellen, nichts Bestehendes ueberschreiben.
                if find_placement_guard_for(doc, member) is not None:
                    already_locked.append(member.Label)
                    continue

                make_placement_guard(
                    doc, member, App.Placement(member.Placement),
                    note=f"Aktuelles Placement gesperrt ueber PlacementGuard-Baugruppen-Modus "
                         f"('{assembly.Label}')"
                )
                created.append(member.Label)

            App.Console.PrintMessage(
                f"FCProject: PlacementGuard fuer Baugruppe '{assembly.Label}': "
                f"{len(created)} neu erstellt"
                + (f" ({', '.join(created)})" if created else "")
                + (
                    f", {len(already_locked)} uebersprungen (bereits gesperrt: "
                    f"{', '.join(already_locked)})" if already_locked else ""
                )
                + (f", {len(skipped)} uebersprungen ({', '.join(skipped)})" if skipped else "")
                + ".\n"
            )

            if created:
                auto_save_document(
                    doc, reason=f"PlacementGuards fuer Baugruppe '{assembly.Label}' erstellt"
                )

        def IsActive(self):
            return App.ActiveDocument is not None

    Gui.addCommand('FCProject_CreatePlacementGuard', CommandCreatePlacementGuard())
