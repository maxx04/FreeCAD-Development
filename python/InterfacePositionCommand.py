# FCProject: "Nach Interface positionieren" - erster Baustein des groesseren Interface-Konzepts
# (Referenzelemente Achse+Flaeche/LCS am Teil + Gegenelemente bei Einbau -> solver-freie
# Einmal-Ausrichtung, siehe project_fcproject_interface_feature_concept-Memory), aufbauend auf
# der Import-Komponente aus ImportComponentCommand.py (2026-08-28, Nutzerentscheidung: "LCS als
# Interfaces Anfang" - statt eines eigenen Referenzelement-Systems nutzen wir FreeCADs eigenes,
# bewaehrtes Attachment-System (Part::LocalCoordinateSystem) als Referenzelement-Typ).
#
# Ablauf: der Nutzer legt in der QUELLE (dem zu importierenden Dokument) ein LCS an der
# gewuenschten Andock-Stelle an (per normalem FreeCAD-Attachment - Flaeche/Kante waehlen), und in
# der ZIEL-Baugruppe ein zweites LCS an der Gegenstelle. Dieser Befehl waehlt beide (erst Quelle,
# dann Ziel) aus und berechnet daraus EINMALIG die Placement, die die Quell-LCS exakt auf die
# Ziel-LCS legt - kein lebendiger Joint, keine Solver-Abhaengigkeit danach. Die betroffene
# Import-Komponente wird automatisch ueber das Dokument der Quell-LCS gefunden (muss ein
# FCProjectImport-markiertes App::Link sein, siehe ImportComponentCommand.py).
import os

import FreeCAD as App

try:
    import FreeCADGui as Gui
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


def position_by_interface(import_link, source_lcs, target_lcs):
    """Berechnet die Placement, die 'source_lcs' exakt auf 'target_lcs' legt, und wendet sie auf
    'import_link' an. Beide LCS werden mit ihrer AKTUELLEN, globalen Placement genommen (die
    Quell-LCS also so, wie sie IM QUELLDOKUMENT SELBST steht, nicht relativ zu einer bereits
    bestehenden Import-Placement - deshalb muss diese Funktion die bisherige Import-Placement
    korrekt herausrechnen)."""
    # newImportPlacement * sourceLcsLocal = targetLcsGlobal
    # sourceLcsLocal ist die Placement der Quell-LCS OHNE die (noch zu berechnende) neue
    # Import-Placement - da source_lcs im Quelldokument selbst liegt (nicht gespiegelt durch den
    # Import-Link), ist ihre .Placement bereits genau das: die Placement relativ zum Ursprung des
    # Quelldokuments, unbeeinflusst von import_link.Placement.
    source_local = App.Placement(source_lcs.Placement)
    target_global = App.Placement(target_lcs.Placement)

    new_placement = target_global.multiply(source_local.inverse())
    import_link.Placement = new_placement
    return new_placement


if _GUI_AVAILABLE:
    class CommandPositionByInterface:
        def GetResources(self):
            return {
                'Pixmap': os.path.join(ICON_DIR, 'import_component.svg'),
                'MenuText': 'FCProject: Nach Interface positionieren',
                'ToolTip': (
                    'Legt eine Import-Komponente EINMALIG anhand zweier lokaler '
                    'Koordinatensysteme (LCS) korrekt aus - erst das LCS in der Quelle '
                    '(Andock-Stelle am importierten Teil), dann das LCS im Ziel (Gegenstelle in '
                    'der Baugruppe) auswaehlen. Keine laufende Solver-Abhaengigkeit danach - '
                    'reine, einmalige geometrische Berechnung.'
                )
            }

        def Activated(self):
            from PySide6 import QtWidgets
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
                new_placement = position_by_interface(import_link, source_lcs, target_lcs)
            except Exception as exc:
                QtWidgets.QMessageBox.warning(main_win, "FCProject", str(exc))
                return

            active_doc.recompute()
            App.Console.PrintMessage(
                f"FCProject: '{import_link.Label}' per Interface positioniert "
                f"('{source_lcs.Label}' -> '{target_lcs.Label}'), neue Placement: "
                f"{new_placement}.\n"
            )

        def IsActive(self):
            return App.ActiveDocument is not None

    Gui.addCommand('FCProject_PositionByInterface', CommandPositionByInterface())
