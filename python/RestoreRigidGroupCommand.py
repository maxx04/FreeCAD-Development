# FCProject: Relativ-Positionen einer Rigid Group aus der Original-Datei wiederherstellen.
#
# Hintergrund (2026-08-23): bei mehrfach verschachtelten flexiblen Baugruppen verliert eine
# Rigid Group ihre Erdung/Zusammengehoerigkeit (siehe patches/README.md), die einzelnen Teile
# landen alle bei Placement=Identitaet. Die RELATIVE Struktur der Rigid Group ist in der
# URSPRUENGLICHEN Quelldatei (wo sie normal geladen/gelost wird) aber weiterhin korrekt. Dieser
# Befehl nutzt das: der Nutzer positioniert EIN Teil (den "Anker") manuell richtig (z.B. per
# ManualPlacementCommand.py), dieser Befehl berechnet daraus die Positionen ALLER ANDEREN
# Mitglieder derselben Rigid Group relativ zum Anker - genau die Rechnung, die
# JointObject.RigidGroupJoint.updateStoredPositions() im FreeCAD-Kern normalerweise macht,
# hier aber bewusst gegen die ORIGINAL-Datei statt gegen die (bei verschachtelten Baugruppen
# unbrauchbaren) aktuellen Werte gerechnet.
import os

import FreeCAD as App

try:
    import FreeCADGui as Gui
    from PySide6 import QtWidgets
    _GUI_AVAILABLE = True
except ImportError:
    _GUI_AVAILABLE = False

ICON_DIR = os.path.join(os.path.dirname(__file__), 'resources', 'icons')


def _find_local_instance(doc, target_obj):
    """Identisch zu ManualPlacementCommand._find_local_mirror() - hier dupliziert, um
    RestoreRigidGroupCommand.py unabhaengig importierbar zu halten (kein Kreisimport-Risiko)."""
    if target_obj.Document is doc:
        return target_obj
    try:
        target_root = target_obj.getLinkedObject(True)
    except Exception:
        target_root = None
    if target_root is None or target_root is target_obj:
        return None
    for candidate in doc.Objects:
        if candidate is target_obj or not candidate.isDerivedFrom("App::Link"):
            continue
        try:
            candidate_root = candidate.getLinkedObject(True)
        except Exception:
            continue
        if candidate_root is target_root:
            return candidate
    return None


def _resolve_root(obj):
    """Loest obj vollstaendig zu seiner ultimativen Quelle auf (getLinkedObject(True)) - liefert
    obj selbst zurueck, falls es kein App::Link (oder aehnliches) ist bzw. die Aufloesung
    fehlschlaegt."""
    try:
        root = obj.getLinkedObject(True)
    except Exception:
        return obj
    return root if root is not None else obj


def _find_source_rigid_group(target_doc, anchor_root):
    """Durchsucht ALLE offenen Dokumente (ausser target_doc) nach einer RigidGroupJoint, unter
    deren Mitgliedern (nach Aufloesung via getLinkedObject(True)) sich anchor_root befindet.

    WICHTIG: die RigidGroupJoint liegt so gut wie nie im Dokument des Rohteils selbst (eine
    einzelne Teile-Datei wie CNC3018_067_A_NEMA17x33.FCStd hat typischerweise gar kein
    Assembly-Objekt) - sie liegt in der BAUGRUPPEN-Datei, die das Rohteil per App::Link einbindet
    (z.B. TreiberBaugruppe100.FCStd). Diese Datei muss dafuer parallel geoeffnet sein.

    Rueckgabe: (rigid_group_obj, members_liste, anchor_member) - anchor_member ist genau das
    Mitglieds-Objekt (i.d.R. ein App::Link INNERHALB der Original-Baugruppe), dessen aufgeloeste
    Wurzel mit anchor_root uebereinstimmt. Dessen eigene Placement (nicht die des Rohteils!) ist
    die relevante 'alte Anker-Position' fuer die Relativrechnung, weil nur sie im selben
    Koordinatensystem wie die anderen Mitglieder steht."""
    for doc in App.listDocuments().values():
        if doc is target_doc:
            continue
        for obj in doc.Objects:
            if not hasattr(obj, "ObjectsToRigidGroup"):
                continue
            members = obj.ObjectsToRigidGroup
            for member in members:
                if member is None:
                    continue
                if _resolve_root(member) is anchor_root:
                    return obj, list(members), member
    return None, [], None


if _GUI_AVAILABLE:
    class RestoreRigidGroupCommand:
        """Befehl: berechnet aus der Original-Datei die Relativpositionen einer Rigid Group und
        wendet sie auf die entsprechenden lokalen Instanzen im aktuellen (verschachtelten)
        Zieldokument an - Anker-Teil vorher per ManualPlacementCommand.py korrekt positionieren,
        dann DIESEN Befehl mit dem Anker als Auswahl ausfuehren."""

        def GetResources(self):
            return {
                'Pixmap': os.path.join(ICON_DIR, 'restore_rigid_group.svg'),
                'MenuText': 'FCProject: Rigid-Group-Positionen aus Original wiederherstellen',
                'ToolTip': (
                    'Ausgehend vom ausgewaehlten, bereits korrekt positionierten Anker-Teil: '
                    'berechnet die Positionen aller anderen Mitglieder derselben Rigid Group '
                    'relativ dazu, aus der urspruenglichen Quelldatei uebernommen (fuer '
                    'verschachtelte Baugruppen, deren automatische Erdung verlorengegangen ist).'
                )
            }

        def Activated(self):
            main_win = Gui.getMainWindow()
            sel = Gui.Selection.getSelection()
            if len(sel) != 1:
                QtWidgets.QMessageBox.warning(main_win, "FCProject", "Bitte genau das Anker-Teil auswaehlen.")
                return
            anchor_local = sel[0]

            target_doc = App.ActiveDocument
            if target_doc is None:
                return

            # Gleiche Mirror-Aufloesung wie in ManualPlacementCommand.py/InterfaceFeature.py
            # (siehe project_fcproject_selection_raw_source_vs_mirror_link): die Baumauswahl kann
            # das rohe Quellobjekt (z.B. ein BaseFeature) statt die lokale Link-Instanz mit der
            # tatsaechlich relevanten Placement liefern.
            try:
                import ManualPlacementCommand
                mirror = ManualPlacementCommand._find_local_mirror(target_doc, anchor_local)
                if mirror is not None and mirror is not anchor_local:
                    App.Console.PrintMessage(
                        f"FCProject: Auswahl '{anchor_local.Label}' gehoert zum Quelldokument von "
                        f"Link-Instanz '{mirror.Label}' in '{target_doc.Name}' - verwende dieses.\n"
                    )
                    anchor_local = mirror
            except Exception as exc:
                App.Console.PrintWarning(f"FCProject: Mirror-Aufloesung fehlgeschlagen: {exc}\n")

            anchor_root = _resolve_root(anchor_local)
            if anchor_root is anchor_local:
                QtWidgets.QMessageBox.warning(
                    main_win, "FCProject",
                    f"'{anchor_local.Label}' ist kein Link auf eine externe Quelldatei - "
                    "kann keine Original-Rigid-Group dafuer finden."
                )
                return

            rigid_group, source_members, anchor_member = _find_source_rigid_group(target_doc, anchor_root)
            if rigid_group is None:
                open_docs = ", ".join(d.Name for d in App.listDocuments().values() if d is not target_doc)
                QtWidgets.QMessageBox.warning(
                    main_win, "FCProject",
                    f"In keinem der aktuell geoeffneten Dokumente ({open_docs or 'keine weiteren offen'}) "
                    f"wurde eine Rigid Group gefunden, die '{anchor_local.Label}' (aufgeloest: "
                    f"'{anchor_root.Label}') als Mitglied fuehrt.\n\n"
                    "Bitte die Original-Baugruppendatei (z.B. TreiberBaugruppe100.FCStd), in der "
                    "die Rigid Group definiert ist, zusaetzlich oeffnen und erneut versuchen."
                )
                return

            anchor_new_placement = App.Placement(anchor_local.Placement)
            # WICHTIG: die Placement des Anker-MITGLIEDS in der Original-Baugruppe verwenden, nicht
            # die des Rohteils in seiner eigenen Datei - nur erstere steht im selben
            # Koordinatensystem wie die Placements der anderen Mitglieder (siehe
            # _find_source_rigid_group()-Docstring).
            anchor_old_placement = App.Placement(anchor_member.Placement)
            anchor_old_inverse = anchor_old_placement.inverse()

            # WICHTIG (2026-08-23, Nutzer-Diagnose): eine reine Placement-Zuweisung reicht nicht.
            # AssemblyObject::getGroundedParts() im FreeCAD-Kern prueft NICHT, ob der Wert
            # "richtig" ist, sondern ausschliesslich Placement.isReadOnly() - ohne das ist das Teil
            # aus Solver-Sicht schlicht NICHT geerdet, egal wie korrekt die Zahl gerade steht. Ein
            # abhaengiger Joint (z.B. ein Revolute-Joint zum Rotor) hat dann keine feste Referenz
            # zum Loesen. Deshalb werden alle wiederhergestellten Teile hier zusaetzlich per
            # InterfaceFeature.make_interface() ECHT gesperrt (Placement.ReadOnly=True + dauerhafte
            # DocObserver-Durchsetzung), statt nur den vorherigen ReadOnly-Status wiederherzustellen.
            import InterfaceFeature

            note = f"Wiederhergestellt aus Rigid Group '{rigid_group.Label}' ({rigid_group.Document.Name})"
            InterfaceFeature.make_interface(target_doc, anchor_local, anchor_new_placement, note=note)

            updated = []
            skipped = []
            for member_source in source_members:
                if member_source is None or member_source is anchor_member:
                    continue
                local_instance = _find_local_instance(target_doc, member_source)
                if local_instance is None:
                    skipped.append(member_source.Label)
                    continue

                relative = anchor_old_inverse.multiply(member_source.Placement)
                new_placement = anchor_new_placement.multiply(relative)

                InterfaceFeature.make_interface(target_doc, local_instance, new_placement, note=note)
                updated.append(local_instance.Label)

            Gui.updateGui()

            msg = (
                f"FCProject: Rigid Group '{rigid_group.Label}' aus "
                f"'{rigid_group.Document.Name}' - {len(updated)} Teil(e) relativ zu "
                f"'{anchor_local.Label}' neu positioniert"
            )
            if skipped:
                msg += f", {len(skipped)} Teil(e) uebersprungen (keine lokale Instanz gefunden: {', '.join(skipped)})"
            msg += ". Bitte pruefen und bei Bedarf per Interface sperren.\n"
            App.Console.PrintMessage(msg)

        def IsActive(self):
            return App.ActiveDocument is not None

    Gui.addCommand('FCProject_RestoreRigidGroup', RestoreRigidGroupCommand())
