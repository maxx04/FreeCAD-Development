import html
import os
import re
import shutil
import tempfile
import time
import zipfile

import FreeCAD as App
from PySide import QtCore


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
    from PySide import QtWidgets
    import FreeCADGui

    if not doc.FileName:
        return

    old_path = os.path.abspath(doc.FileName)
    doc_dir = os.path.dirname(old_path)
    current_stem = os.path.splitext(os.path.basename(old_path))[0]
    new_path = os.path.join(doc_dir, f"{expected_stem}.FCStd")
    if os.path.exists(new_path):
        QtWidgets.QMessageBox.warning(
            FreeCADGui.getMainWindow(),
            "FCProject: Dateiname prüfen",
            f"Der Dateiname stimmt nicht mit dem PDM-Objekt überein, aber\n\n  {expected_stem}.FCStd\n\n"
            f"gibt es im Projekt schon. Bitte zuerst klären, welche der beiden Dateien gilt.",
        )
        return

    referencing = find_referencing_files(doc_dir, old_path)
    refs = "\n".join(f"  {os.path.basename(f)}" for f in referencing[:15])
    if len(referencing) > 15:
        refs += f"\n  … und {len(referencing) - 15} weitere"
    msg = (
        f"Der Dateiname stimmt nicht mit dem PDM-Objekt überein:\n\n"
        f"  Aktuell:   {current_stem}.FCStd\n"
        f"  Vorschlag: {expected_stem}.FCStd\n\n"
    )
    if referencing:
        msg += f"Diese Projektdateien verweisen darauf und werden angepasst:\n{refs}\n\n"
    else:
        msg += "Keine andere Projektdatei verweist darauf.\n\n"
    msg += (
        f"Die alte Datei wird als Sicherung (.FCBak) umbenannt.\n\n"
        f"Soll die Datei umbenannt werden?"
    )
    reply = QtWidgets.QMessageBox.question(
        FreeCADGui.getMainWindow(),
        "FCProject: Dateiname prüfen",
        msg,
        QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        QtWidgets.QMessageBox.Yes,
    )
    if reply != QtWidgets.QMessageBox.Yes:
        return
    try:
        result = rename_document_with_references(doc, new_path)
    except Exception as e:
        QtWidgets.QMessageBox.critical(
            FreeCADGui.getMainWindow(), "FCProject: Umbenennen fehlgeschlagen", str(e)
        )
        return
    lines = [f"Umbenannt in {expected_stem}.FCStd."]
    if result["updated"]:
        lines.append(f"Verweise angepasst in {len(result['updated'])} Datei(en).")
    if result["open_unsaved"]:
        lines.append(
            "Geöffnet und noch zu speichern (Verweis im Speicher schon neu):\n"
            + "\n".join(f"  {n}" for n in result["open_unsaved"])
        )
    if result["backup"]:
        lines.append(f"Alte Datei gesichert als {os.path.basename(result['backup'])}.")
    QtWidgets.QMessageBox.information(
        FreeCADGui.getMainWindow(), "FCProject: Datei umbenannt", "\n\n".join(lines)
    )


# ---------------------------------------------------------------------- Umbenennen mit Verweisen
# Ein Dateiverweis steht in der verweisenden .FCStd in Document.xml als
#   <XLink file="CNC3018_067_A_NEMA17x33.FCStd" stamp="..." name="..."/>
# (Pfad relativ zur verweisenden Datei), die Stueckliste traegt absolute Pfade in Zellen.
# Frueher speicherte das Umbenennen nur per saveAs unter neuem Namen: die alte Datei blieb liegen,
# nicht geoeffnete Dateien verwiesen weiter darauf - zwei Fassungen desselben Teils im Projekt
# (2026-10-27: BG75 verwies auf eine alte Motor-Kopie, BG22 hing im Solver).

_XLINK_FILE = re.compile(r'(<XLink\b[^>]*?\bfile=")([^"]+)(")')


def _project_files(project_dir):
    return sorted(
        os.path.join(project_dir, f)
        for f in os.listdir(project_dir)
        if f.endswith(".FCStd") and os.path.isfile(os.path.join(project_dir, f))
    )


def _xlink_targets(xml, ref_file):
    """(Attributwert, aufgeloester absoluter Pfad) aller XLink-Dateiverweise."""
    base = os.path.dirname(os.path.abspath(ref_file))
    for m in _XLINK_FILE.finditer(xml):
        value = html.unescape(m.group(2))
        yield m, os.path.normpath(os.path.join(base, value))


def _rewrite_xml(xml, ref_file, old_path, new_path):
    """Document.xml mit umgestellten Verweisen (XLink-Dateien, absolute Pfade in Zellen) und Anzahl."""
    base = os.path.dirname(os.path.abspath(ref_file))
    new_rel = os.path.relpath(new_path, base)
    count = 0

    def xlink(m):
        nonlocal count
        target = os.path.normpath(os.path.join(base, html.unescape(m.group(2))))
        if target != old_path:
            return m.group(0)
        count += 1
        return m.group(1) + html.escape(new_rel, quote=True) + m.group(3)

    xml = _XLINK_FILE.sub(xlink, xml)
    old_abs = html.escape(old_path, quote=True)
    if old_abs in xml:  # z.B. Stuecklisten-Zellen mit absolutem Pfad
        count += xml.count(old_abs)
        xml = xml.replace(old_abs, html.escape(new_path, quote=True))
    return xml, count


def find_referencing_files(project_dir, target_path):
    """Projektdateien, die per XLink oder absolutem Pfad auf target_path verweisen."""
    target_path = os.path.abspath(target_path)
    result = []
    for path in _project_files(project_dir):
        if os.path.abspath(path) == target_path:
            continue
        try:
            with zipfile.ZipFile(path) as z:
                xml = z.read("Document.xml").decode("utf-8")
        except Exception:
            continue
        if any(t == target_path for _, t in _xlink_targets(xml, path)) or html.escape(target_path, quote=True) in xml:
            result.append(path)
    return result


def _rewrite_fcstd(path, old_path, new_path):
    """Verweise in einer geschlossenen .FCStd umstellen; Rueckgabe: Anzahl geaenderter Stellen.
    Nur Document.xml wird neu geschrieben, alle anderen Eintraege byte-gleich uebernommen."""
    with zipfile.ZipFile(path) as z:
        xml = z.read("Document.xml").decode("utf-8")
        new_xml, count = _rewrite_xml(xml, path, old_path, new_path)
        if not count:
            return 0
        fd, tmp = tempfile.mkstemp(suffix=".FCStd", dir=os.path.dirname(path))
        os.close(fd)
        try:
            with zipfile.ZipFile(tmp, "w") as out:
                out.comment = z.comment
                for info in z.infolist():
                    data = new_xml.encode("utf-8") if info.filename == "Document.xml" else z.read(info)
                    out.writestr(info, data, compress_type=info.compress_type)
            shutil.copystat(path, tmp)
            os.replace(tmp, path)
        except Exception:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise
    return count


def rename_document_with_references(doc, new_path):
    """Dokument unter new_path speichern und alle Verweise im Projektordner darauf umstellen.

    - geoeffnete Dokumente: FreeCAD stellt ihre Verweise beim saveAs selbst um (im Speicher); sie
      werden zusaetzlich auf der Platte umgestellt, damit nichts am alten Namen haengt, falls sie
      nicht mehr gespeichert werden
    - geschlossene Dateien: nur die Verweis-Eintraege in Document.xml werden ersetzt
    - die alte Datei wird zu "<alt>.<Zeitstempel>.FCBak" (wie FreeCADs Sicherungen), damit keine
      zweite gueltige Fassung im Projekt liegt
    Rueckgabe: {"updated": [Pfade], "open_unsaved": [Dokumentnamen], "backup": Pfad oder None}
    """
    old_path = os.path.abspath(doc.FileName)
    new_path = os.path.abspath(new_path)
    project_dir = os.path.dirname(old_path)
    if os.path.exists(new_path):
        raise RuntimeError(f"{os.path.basename(new_path)} existiert schon.")
    referencing = find_referencing_files(project_dir, old_path)

    doc.saveAs(new_path)
    if os.path.abspath(doc.FileName) != new_path:
        raise RuntimeError("Speichern unter dem neuen Namen ist fehlgeschlagen.")

    updated = []
    for path in referencing:
        if _rewrite_fcstd(path, old_path, new_path):
            updated.append(path)

    open_unsaved = []
    for other in App.listDocuments().values():
        if other is doc or not other.FileName:
            continue
        if os.path.abspath(other.FileName) in referencing and other.isTouched():
            open_unsaved.append(other.Label)

    backup = None
    if os.path.exists(old_path):
        stem = os.path.splitext(old_path)[0]
        backup = f"{stem}.{time.strftime('%Y%m%d-%H%M%S')}.FCBak"
        os.replace(old_path, backup)

    App.Console.PrintMessage(
        f"FCProject: {os.path.basename(old_path)} -> {os.path.basename(new_path)}, Verweise "
        f"angepasst in {len(updated)} Datei(en)"
        + (f", alte Datei gesichert als {os.path.basename(backup)}" if backup else "")
        + "\n"
    )
    return {"updated": updated, "open_unsaved": open_unsaved, "backup": backup}


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
