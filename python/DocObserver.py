import os
import FreeCAD as App


class FCProjectDocObserver:
    """Prüft beim Öffnen ob der Dateiname mit dem ersten PDM-Objekt übereinstimmt."""

    def slotOpenDocument(self, doc):
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

        try:
            from PySide2 import QtCore
        except ImportError:
            from PySide6 import QtCore

        QtCore.QTimer.singleShot(0, lambda: _ask_rename(doc, expected_stem))


def _is_project_folder(folder):
    folder_name = os.path.basename(folder)
    json_path = os.path.join(folder, f"{folder_name}.json")
    return folder_name.startswith("PROJ_") and os.path.exists(json_path)


def _find_pdm_object(doc):
    for obj in doc.Objects:
        if hasattr(obj, "ArticleID") and obj.ArticleID:
            return obj
    return None


def _build_expected_stem(obj):
    article_id = str(obj.ArticleID).strip()
    if not article_id:
        return None
    bezeichnung = str(getattr(obj, "Bezeichnung", "") or "").strip()
    if bezeichnung:
        return article_id.rstrip("_") + "_" + bezeichnung + "_"
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


def unregister():
    global _observer
    if _observer is not None:
        App.removeDocumentObserver(_observer)
        _observer = None
