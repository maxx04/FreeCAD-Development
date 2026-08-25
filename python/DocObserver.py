import os
import FreeCAD as App

try:
    from PySide2 import QtCore
except ImportError:
    from PySide6 import QtCore


class FCProjectDocObserver:
    """Prüft beim Öffnen/Speichern ob der Dateiname mit dem PDM-Objekt übereinstimmt, und repariert
    vor jedem Speichern automatisch hängengebliebenes Selectable=False (Joint-Isolate-Bug, siehe
    SelectableRepairCommand.py)."""

    def slotOpenDocument(self, doc):
        # Objekte sind beim Open-Signal noch nicht geladen — kurz verzögern
        QtCore.QTimer.singleShot(500, lambda: _check_doc(doc))

    def slotSavedDocument(self, doc):
        _check_doc(doc)

    def slotStartSaveDocument(self, doc, filename):
        # Läuft VOR dem eigentlichen Schreiben (App::Document.signalStartSave) - die Reparatur
        # landet dadurch direkt im gerade laufenden Speichervorgang, statt erst beim nächsten.
        _repair_stuck_selectable(doc)

    def slotActivateDocument(self, doc):
        # Schließt das PDM-Creator-Panel zusätzlich zum Werkbench-Wechsel-Hook (InitGui.py
        # Deactivated()) auch bei einem reinen Dokument-Wechsel OHNE Werkbench-Wechsel - z.B. beim
        # Zurückspringen von einem frisch erstellten Kaufteil in die Gesamtbaugruppe, um dort
        # "Teil hinzufügen" zu nutzen. Siehe TaskPanel.close_panel_on_foreign_document() für die
        # Details (inkl. Ausnahme während unserer eigenen Kaufteil-Erstellung).
        try:
            import TaskPanel
            TaskPanel.close_panel_on_foreign_document(doc)
        except Exception as e:
            App.Console.PrintWarning(f"FCProject DocObserver: Panel-Check beim Dokument-Wechsel fehlgeschlagen: {str(e)}\n")

    def slotRecomputedDocument(self, doc):
        # Setzt alle "PlacementGuard"-Objekte (siehe PlacementGuardFeature.py) NACH einem
        # KOMPLETTEN Dokument-Recompute erneut durch - unabhaengig davon, in welcher internen
        # Reihenfolge der (bei verschachtelten flexiblen Baugruppen nachweislich fehlerhafte)
        # Assembly-Solver gelaufen ist. Kein doc.recompute()-Aufruf hier drin (reine
        # Eigenschaftszuweisung) - loest also KEIN erneutes signalRecomputed und damit keine
        # Rekursion aus.
        try:
            import PlacementGuardFeature
            PlacementGuardFeature.enforce_all_placement_guards(doc)
        except Exception as e:
            App.Console.PrintWarning(f"FCProject DocObserver: PlacementGuard-Durchsetzung fehlgeschlagen: {str(e)}\n")


def _repair_stuck_selectable(doc):
    """Repariert vor jedem Speichern automatisch hängengebliebenes Selectable=False (bekannter
    FreeCAD-Bug beim Joint-Editor-'Isolate'-Feature, siehe patches/freecad-assembly-jointobject.patch
    Fix 5 - der verhindert das nur für den EINEN dort gepatchten Ausstiegspfad; FreeCADs eigene
    Sperre gegen Dokument-Schließen bei offenem Task-Dialog ist in diesem Build auskommentiert
    (Document.cpp canClose()), es gibt also weitere, nicht einzeln patchbare Wege dahin). Statt
    jeden möglichen FreeCAD-internen Ausstiegspfad einzeln zu jagen: verhindert direkt, dass der
    kaputte Zustand überhaupt in die Datei geschrieben wird."""
    try:
        from SelectableRepairCommand import find_stuck_objects
        stuck = find_stuck_objects(doc)
        if not stuck:
            return
        for obj in stuck:
            obj.ViewObject.Selectable = True
        names = ", ".join(o.Label for o in stuck)
        App.Console.PrintWarning(
            f"FCProject DocObserver: {len(stuck)} Bauteil(e) hatten Selectable=False "
            f"(Joint-Isolate-Bug) - vor dem Speichern automatisch repariert: {names}\n"
        )
    except Exception as e:
        App.Console.PrintWarning(f"FCProject DocObserver: Selectable-Reparatur fehlgeschlagen: {str(e)}\n")


def _check_doc(doc):
    try:
        if not doc.FileName:
            return

        doc_dir = os.path.dirname(doc.FileName)
        if not _is_project_folder(doc_dir):
            return

        pdm_obj = _find_pdm_object(doc)
        if not pdm_obj:
            return

        expected_stem = _build_expected_stem(pdm_obj)
        if not expected_stem:
            return

        current_stem = os.path.splitext(os.path.basename(doc.FileName))[0]
        if current_stem == expected_stem:
            return

        QtCore.QTimer.singleShot(0, lambda: _ask_rename(doc, expected_stem))
    except Exception as e:
        App.Console.PrintWarning(f"FCProject DocObserver: Fehler bei Prüfung: {str(e)}\n")


def _is_project_folder(folder):
    folder_name = os.path.basename(folder)
    json_path = os.path.join(folder, f"{folder_name}.json")
    return folder_name.startswith("PROJ_") and os.path.exists(json_path)


def _find_pdm_object(doc):
    """Findet das primäre PDM-Objekt im Dokument.
    Bevorzugt Assembly oder Body gegenüber untergeordneten Link-Objekten."""
    # Zuerst: Assembly-Objekte (Baugruppen-Dokument)
    for obj in doc.Objects:
        if obj.TypeId == "Assembly::AssemblyObject":
            if hasattr(obj, "ArticleID") and obj.ArticleID:
                return obj

    # Dann: PartDesign::Body (Einzelteil-Dokument)
    for obj in doc.Objects:
        if obj.TypeId == "PartDesign::Body":
            if hasattr(obj, "ArticleID") and obj.ArticleID:
                return obj

    # Fallback: erstes beliebiges Objekt mit ArticleID
    for obj in doc.Objects:
        if hasattr(obj, "ArticleID") and obj.ArticleID:
            return obj

    return None


def _build_expected_stem(obj):
    article_id = str(obj.ArticleID).strip()
    if not article_id:
        return None
    # rstrip("_") bleibt als Kompatibilität für ArticleIDs aus vor der Umstellung
    # gespeicherten Dokumenten - neue IDs haben keinen Unterstrich am Ende mehr.
    article_id = article_id.rstrip("_")
    bezeichnung = str(getattr(obj, "Bezeichnung", "") or "").strip()
    if bezeichnung:
        return f"{article_id}_{bezeichnung}"
    return article_id


def _ask_rename(doc, expected_stem):
    try:
        from PySide2 import QtWidgets
        import FreeCADGui
    except ImportError:
        from PySide6 import QtWidgets
        import FreeCADGui

    if not doc.FileName:
        return

    doc_dir = os.path.dirname(doc.FileName)
    current_stem = os.path.splitext(os.path.basename(doc.FileName))[0]
    new_path = os.path.join(doc_dir, f"{expected_stem}.FCStd")

    msg = (
        f"Der Dateiname stimmt nicht mit dem PDM-Objekt überein:\n\n"
        f"  Aktuell:   {current_stem}.FCStd\n"
        f"  Vorschlag: {expected_stem}.FCStd\n\n"
        f"Soll die Datei unter dem korrekten Namen gespeichert werden?"
    )
    reply = QtWidgets.QMessageBox.question(
        FreeCADGui.getMainWindow(),
        "FCProject: Dateiname prüfen",
        msg,
        QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        QtWidgets.QMessageBox.Yes,
    )
    if reply == QtWidgets.QMessageBox.Yes:
        doc.saveAs(new_path)


_observer = None


def register():
    global _observer
    if _observer is None:
        _observer = FCProjectDocObserver()
        App.addDocumentObserver(_observer)

    # Bereits geöffnete Dokumente nachträglich prüfen (z.B. nach Auto-Restore)
    for doc in App.listDocuments().values():
        QtCore.QTimer.singleShot(200, lambda d=doc: _check_doc(d))


def unregister():
    global _observer
    if _observer is not None:
        App.removeDocumentObserver(_observer)
        _observer = None
