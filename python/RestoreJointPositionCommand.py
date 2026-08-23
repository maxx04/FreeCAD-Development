# FCProject: Position eines ueber einen NORMALEN Joint (Reference1/Reference2, z.B. Revolute)
# verbundenen Teils aus der Original-Datei wiederherstellen.
#
# Hintergrund (2026-08-23): bei mehrfach verschachtelten flexiblen Baugruppen kann der native
# Assembly-Solver selbst nach korrekter Erdung noch versagen - siehe patches/README.md,
# "Solve failed: To be implemented." (Ondsel-Solver gibt bei der Redundanz-Erkennung nach vielen
# Wiederholungen auf). Betroffene Teile (z.B. der Rotor eines Motors, relativ zum Gehaeuse ueber
# einen Revolute-Joint verbunden) bleiben dadurch bei Placement=Identitaet stehen, obwohl das
# Gehaeuse selbst schon korrekt gesperrt ist.
#
# Gleiches Prinzip wie RestoreRigidGroupCommand.py (siehe dort fuer die volle Begruendung, warum
# eine reine Placement-Zuweisung nicht reicht und InterfaceFeature.make_interface() noetig ist),
# nur fuer normale Joint-Paare statt eine ganze RigidGroupJoint-Mitgliederliste: ausgehend von
# einem bereits korrekt positionierten Anker-Teil werden ALLE ORIGINALEN Joints gefunden, die
# dieses Teil referenzieren (ein Anker kann an mehreren Joints gleichzeitig haengen, z.B. eine
# Buchse an Gewindestange UND zwei Gewindestiften - fruehere Version nahm faelschlich nur den
# ERSTEN Treffer), und daraus jeweils die Placement des ANDEREN referenzierten Teils berechnet:
# neue_Position = neue_Anker_Position x (alte_Anker_Position^-1 x alte_Ziel_Position).
import os

import FreeCAD as App

try:
    import FreeCADGui as Gui
    from PySide6 import QtWidgets
    _GUI_AVAILABLE = True
except ImportError:
    _GUI_AVAILABLE = False

ICON_DIR = os.path.join(os.path.dirname(__file__), 'resources', 'icons')


def _resolve_root(obj):
    """Loest obj vollstaendig zu seiner ultimativen Quelle auf (getLinkedObject(True)) - liefert
    obj selbst zurueck, falls es kein App::Link (oder aehnliches) ist bzw. die Aufloesung
    fehlschlaegt. Identisch zu RestoreRigidGroupCommand._resolve_root() - hier dupliziert, um
    beide Module unabhaengig voneinander benutzbar zu halten."""
    try:
        root = obj.getLinkedObject(True)
    except Exception:
        return obj
    return root if root is not None else obj


def _find_local_instance(doc, target_obj):
    """Identisch zu RestoreRigidGroupCommand._find_local_instance()/
    ManualPlacementCommand._find_local_mirror()."""
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


def _joint_reference_object(joint, prop_name):
    """Liest Reference1/Reference2 (App::PropertyXLinkSub) aus - in Python je nach Zugriffsart
    entweder als (Objekt, Sub-Namen-Tupel) oder direkt als Objekt sichtbar; beide Faelle werden
    hier abgefangen."""
    value = getattr(joint, prop_name, None)
    if value is None:
        return None
    if isinstance(value, (tuple, list)) and len(value) >= 1:
        return value[0]
    return value


def _find_source_joints(target_doc, anchor_root):
    """Durchsucht ALLE offenen Dokumente (ausser target_doc) nach ALLEN normalen Joints
    (erkennbar an Reference1 UND Reference2), deren eine Seite - nach Aufloesung via
    getLinkedObject(True) - mit anchor_root uebereinstimmt.

    WICHTIG (2026-08-23, Nutzer-Repro): ein Anker-Teil kann an MEHREREN Joints gleichzeitig
    haengen (z.B. eine Motor-Buchse an Gewindestange UND zwei Gewindestiften UND einem
    Wellen-Link) - eine fruehere Version dieser Funktion gab nur den ERSTEN Treffer zurueck,
    wodurch zufaellig ein falscher Nachbar (z.B. ein Gewindestift statt der eigentlich
    gewuenschten Gewindestange) aktualisiert wurde. Jetzt werden ALLE passenden Joints
    zurueckgegeben und in Activated() alle auf einmal verarbeitet - genau wie
    RestoreRigidGroupCommand alle Mitglieder einer Rigid Group auf einmal verarbeitet.

    WICHTIG (siehe RestoreRigidGroupCommand._find_source_rigid_group() fuer die ausfuehrliche
    Begruendung): der Joint liegt so gut wie nie im Dokument des Rohteils selbst, sondern in der
    BAUGRUPPEN-Datei, die die Teile per App::Link einbindet - diese Datei muss dafuer parallel
    geoeffnet sein.

    Rueckgabe: Liste von (joint, anchor_member, other_member) - anchor_member/other_member sind
    die beiden ueber Reference1/Reference2 referenzierten Objekte INNERHALB der Original-
    Baugruppe (nicht zwingend die Rohteile selbst) - deren Placement steht im selben
    Koordinatensystem wie das jeweils andere Referenzobjekt, das ist fuer die Relativrechnung
    entscheidend."""
    results = []
    for doc in App.listDocuments().values():
        if doc is target_doc:
            continue
        for obj in doc.Objects:
            if not (hasattr(obj, "Reference1") and hasattr(obj, "Reference2")):
                continue
            ref1 = _joint_reference_object(obj, "Reference1")
            ref2 = _joint_reference_object(obj, "Reference2")
            if ref1 is None or ref2 is None:
                continue
            if _resolve_root(ref1) is anchor_root:
                results.append((obj, ref1, ref2))
            elif _resolve_root(ref2) is anchor_root:
                results.append((obj, ref2, ref1))
    return results


if _GUI_AVAILABLE:
    def _warn(main_win, text):
        """Zeigt eine Warnung sowohl als Popup als auch in der Konsole/Log-Datei - Popups
        landen NICHT im Log, das Claude ueber run-freecad-26.3.sh liest (siehe
        project_fcproject_live_log_file_access), ohne diese Zeile waeren Fehlermeldungen aus
        diesem Befehl fuer eine Ferndiagnose unsichtbar."""
        App.Console.PrintWarning(f"FCProject: {text}\n")
        QtWidgets.QMessageBox.warning(main_win, "FCProject", text)

    class RestoreJointPositionCommand:
        """Befehl: berechnet aus der Original-Datei die Positionen ALLER ueber normale Joints
        mit dem Anker verbundenen Teile relativ zu diesem bereits korrekt positionierten
        Anker-Teil - Anker-Teil vorher per ManualPlacementCommand.py/RestoreRigidGroupCommand.py
        korrekt positionieren, dann DIESEN Befehl mit dem Anker als Auswahl ausfuehren."""

        def GetResources(self):
            return {
                'Pixmap': os.path.join(ICON_DIR, 'restore_joint_position.svg'),
                'MenuText': 'FCProject: Joint-Positionen aus Original wiederherstellen',
                'ToolTip': (
                    'Ausgehend vom ausgewaehlten, bereits korrekt positionierten Anker-Teil: '
                    'berechnet die Positionen ALLER ueber normale Joints (z.B. Revolute) damit '
                    'verbundenen Teile relativ dazu, aus der urspruenglichen Baugruppendatei '
                    'uebernommen (fuer Faelle, in denen der Assembly-Solver bei mehrfach '
                    'verschachtelten Baugruppen nicht mehr zuverlaessig loest). Ein Anker kann an '
                    'mehreren Joints gleichzeitig haengen (z.B. eine Buchse an Gewindestange UND '
                    'Gewindestiften) - alle werden auf einmal aktualisiert.'
                )
            }

        def Activated(self):
            main_win = Gui.getMainWindow()
            sel = Gui.Selection.getSelection()
            if len(sel) != 1:
                _warn(main_win, "Bitte genau das Anker-Teil auswaehlen.")
                return
            anchor_local = sel[0]

            target_doc = App.ActiveDocument
            if target_doc is None:
                return

            # Gleiche Mirror-Aufloesung wie in ManualPlacementCommand.py/RestoreRigidGroupCommand.py
            # (siehe project_fcproject_selection_raw_source_vs_mirror_link): die Baumauswahl kann
            # das rohe Quellobjekt statt die lokale Link-Instanz mit der tatsaechlich relevanten
            # Placement liefern.
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
                _warn(
                    main_win,
                    f"'{anchor_local.Label}' (Typ {anchor_local.TypeId}, Dokument "
                    f"'{anchor_local.Document.Name}') ist kein Link auf eine externe Quelldatei - "
                    "kann keinen Original-Joint dafuer finden."
                )
                return

            found_joints = _find_source_joints(target_doc, anchor_root)
            if not found_joints:
                open_docs = ", ".join(d.Name for d in App.listDocuments().values() if d is not target_doc)
                _warn(
                    main_win,
                    f"In keinem der aktuell geoeffneten Dokumente ({open_docs or 'keine weiteren offen'}) "
                    f"wurde ein Joint gefunden, der '{anchor_local.Label}' (aufgeloest: "
                    f"'{anchor_root.Label}') referenziert. Bitte die Original-Baugruppendatei, in "
                    "der der Joint definiert ist, zusaetzlich oeffnen und erneut versuchen."
                )
                return

            anchor_new_placement = App.Placement(anchor_local.Placement)
            import InterfaceFeature

            updated = []
            skipped = []
            already_locked = []
            for joint, anchor_member, other_member in found_joints:
                local_other = _find_local_instance(target_doc, other_member)
                if local_other is None:
                    other_label = other_member.Label if other_member is not None else "?"
                    skipped.append(f"{other_label} (Joint '{joint.Label}')")
                    continue

                # WICHTIG (2026-08-23, Nutzer-Repro): ein Anker kann ueber MEHRERE Joints
                # gleichzeitig an Teile grenzen, die bereits ueber einen ANDEREN, autoritativeren
                # Anker korrekt positioniert und gesperrt wurden (z.B. Rotor wird korrekt vom
                # Gehaeuse abgeleitet, haengt aber ZUSAETZLICH ueber einen eigenen Joint an der
                # Buchse - wird die Buchse als Anker benutzt, wuerde dieser zweite Pfad den
                # bereits korrekten Rotor wieder ueberschreiben und aus der Kette werfen). Bereits
                # gesperrte Teile deshalb NICHT anfassen, damit die Reihenfolge der Anker-Klicks
                # (Gehaeuse -> Rotor+Buchse, dann Buchse -> Gewindestange/-stifte) stabil bleibt.
                existing = InterfaceFeature.find_interface_for(target_doc, local_other)
                if existing is not None:
                    already_locked.append(f"{local_other.Label} (Joint '{joint.Label}')")
                    continue

                # WICHTIG: die Placement des Anker-MITGLIEDS im Original-Joint verwenden, nicht
                # die des Rohteils in seiner eigenen Datei - nur erstere steht im selben
                # Koordinatensystem wie die Placement des anderen Referenzobjekts (siehe
                # _find_source_joints()-Docstring).
                anchor_old_placement = App.Placement(anchor_member.Placement)
                relative = anchor_old_placement.inverse().multiply(App.Placement(other_member.Placement))
                new_placement = anchor_new_placement.multiply(relative)

                # WICHTIG (siehe RestoreRigidGroupCommand.py): reine Placement-Zuweisung reicht
                # nicht, der Solver erdet nur ueber Placement.isReadOnly() - deshalb ueber
                # InterfaceFeature.make_interface() echt sperren statt nur den Wert zu setzen.
                note = (
                    f"Wiederhergestellt aus Joint '{joint.Label}' ({joint.Document.Name}), "
                    f"relativ zu '{anchor_local.Label}'"
                )
                InterfaceFeature.make_interface(target_doc, local_other, new_placement, note=note)
                updated.append(f"{local_other.Label} (Joint '{joint.Label}')")

            Gui.updateGui()

            msg = (
                f"FCProject: relativ zu '{anchor_local.Label}' neu positioniert und gesperrt: "
                f"{', '.join(updated) if updated else '(keine)'}."
            )
            if already_locked:
                msg += (
                    f" Uebersprungen (bereits ueber anderen Anker gesperrt, NICHT ueberschrieben): "
                    f"{', '.join(already_locked)}."
                )
            if skipped:
                msg += f" Uebersprungen (keine lokale Instanz gefunden): {', '.join(skipped)}."
            App.Console.PrintMessage(msg + "\n")

            if updated:
                InterfaceFeature.auto_save_document(
                    target_doc, reason=f"relativ zu '{anchor_local.Label}' neu positioniert"
                )

        def IsActive(self):
            return App.ActiveDocument is not None

    Gui.addCommand('FCProject_RestoreJointPosition', RestoreJointPositionCommand())
