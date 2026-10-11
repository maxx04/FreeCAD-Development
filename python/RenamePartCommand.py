# FCProject: "Part/Baugruppe umbenennen" - aendert Bezeichnung + Article-ID eines PDM-Root-
# Objekts (Typ P/A, funktioniert generisch fuer jedes Objekt mit ArticleID-Property) und haelt
# dabei alle App::Link-Verlinkungen INNERHALB desselben PROJ_-Ordners konsistent: die .FCStd-
# Datei wird entsprechend umbenannt (Speichern unter neuem Namen, alte Datei danach entfernt),
# jeder App::Link in einer anderen Projektdatei, der auf dieses Objekt zeigt, bekommt sein Label
# nachgezogen und wird neu gespeichert.
#
# WICHTIG (Nutzervorgabe, siehe CONSTRAINTS.md): Rename wird NUR innerhalb des eigenen PROJ_-
# Ordners durchgefuehrt. Wird dasselbe Teil auch in einem ANDEREN Projekt verwendet, wird das
# hier bewusst NICHT automatisch repariert - siehe TODO.md (2. Prio: Hilfe zur manuellen
# Reparatur fuer projektuebergreifende Verwendungen anbieten).
#
# Technischer Hintergrund, warum ein simples os.rename() der Datei NICHT reicht: FreeCADs
# App::Link speichert die Referenz auf ein Objekt in einem ANDEREN Dokument ueber PropertyXLink -
# das haelt neben dem internen Dokument-Namen zusaetzlich einen RELATIVEN DATEIPFAD, der beim
# naechsten Speichern des VERLINKENDEN Dokuments aus den dann AKTUELLEN Pfaden beider Dokumente
# neu berechnet wird (siehe freecad-source: App/PropertyLinks.cpp, DocInfo::getDocPath()). Die
# eigentliche Objekt-Referenz (link.LinkedObject) bleibt dabei die ganze Zeit unveraendert -
# nur die verlinkenden Dokumente muessen nach dem Verschieben der Zieldatei einmal neu
# gespeichert werden, damit ihr gespeicherter relativer Pfad wieder stimmt.
import os
import FreeCAD as App
import FreeCADGui as Gui
from PySide6 import QtWidgets

from PartExchangeAnalyzer import find_external_project_references, find_project_root

_active_panel = None


def _resolve_root_pdm_object(obj):
    """Folgt (wie Utils.get_artikel_id) der Link-Kette, bis ein Objekt mit eigener ArticleID
    gefunden wird - anders als get_artikel_id wird hier das OBJEKT selbst zurueckgegeben (nicht
    nur die ID-Zeichenkette), weil die echte Root-Datei umbenannt werden muss."""
    current = obj
    if hasattr(current, "ArticleID") and current.ArticleID:
        return current
    while hasattr(current, "LinkedObject") and current.LinkedObject:
        current = current.LinkedObject
        if hasattr(current, "ArticleID") and current.ArticleID:
            return current
    return None


def _build_label(article_id, bezeichnung):
    """Gleiche Konvention wie EntityCreator.create_pdm_document(): Label = ArticleID, optional
    mit der Bezeichnung als Suffix - identisch zum physischen Dateinamen (ohne .FCStd)."""
    return f"{article_id}_{bezeichnung}" if bezeichnung else article_id


def rename_pdm_object(root_obj, new_bezeichnung, new_article_id):
    """Benennt root_obj (Label/ArticleID/Bezeichnung-Property + physische .FCStd-Datei) um und
    haelt alle App::Link-Verlinkungen INNERHALB des PROJ_-Ordners konsistent.

    Gibt ein Dict mit altem/neuem Label und Anzahl aktualisierter Links/Dateien zurueck."""
    doc = root_obj.Document
    old_path = doc.FileName
    if not old_path:
        raise RuntimeError("Das Dokument wurde noch nie gespeichert - bitte zuerst einmal speichern.")

    old_label = root_obj.Label
    new_label = _build_label(new_article_id, new_bezeichnung)

    project_dir = os.path.dirname(old_path)
    new_path = os.path.join(project_dir, f"{new_label}.FCStd")
    if os.path.exists(new_path) and os.path.abspath(new_path) != os.path.abspath(old_path):
        raise FileExistsError(f"Die Datei '{os.path.basename(new_path)}' existiert bereits.")

    # 1. VOR jeder Aenderung: projektweite Referenzen auf root_obj.Name per schnellem ZIP-Scan
    # finden (siehe PartExchangeAnalyzer.find_external_project_references). .Name ist der
    # INTERNE FreeCAD-Objektname, NICHT Label/ArticleID - er aendert sich beim Umbenennen nie,
    # die Suche bleibt also vorher wie nachher gueltig. Muss vor dem eigentlichen Umbenennen
    # laufen, damit die alte Datei zum gefahrlosen Oeffnen noch existiert, falls eine
    # Kandidatendatei gerade nicht offen ist.
    candidates = find_external_project_references(root_obj)
    project_root = find_project_root(doc)

    opened_here = []
    updated_links = 0
    touched_docs = set()

    try:
        for file_path, _count in candidates:
            # Nur innerhalb des eigenen PROJ_-Ordners automatisch reparieren (Nutzervorgabe,
            # siehe Modul-Docstring) - Dateien ausserhalb bewusst unberuehrt lassen.
            if project_root is None or not os.path.abspath(file_path).startswith(os.path.abspath(project_root)):
                continue

            already_open_name = None
            for doc_name, open_doc in App.listDocuments().items():
                if open_doc.FileName and os.path.abspath(open_doc.FileName) == os.path.abspath(file_path):
                    already_open_name = doc_name
                    break

            if already_open_name:
                other_doc = App.getDocument(already_open_name)
            else:
                other_doc = App.openDocument(file_path)
                opened_here.append(other_doc.Name)

            doc_touched = False
            for obj in other_doc.Objects:
                if not obj.isDerivedFrom("App::Link"):
                    continue
                if obj.LinkedObject is root_obj:
                    obj.Label = new_label
                    doc_touched = True
                    updated_links += 1

            if doc_touched:
                touched_docs.add(other_doc.Name)

        # 2. Jetzt erst das Root-Objekt selbst umbenennen: Properties setzen, unter dem neuen
        # Dateinamen speichern (schreibt die NEUE Datei) - die ALTE Datei bleibt bewusst noch
        # auf der Platte, bis Schritt 3 (unten) alle betroffenen Link-Dokumente mit dem neuen
        # relativen Pfad neu gespeichert hat.
        if hasattr(root_obj, "Bezeichnung"):
            root_obj.Bezeichnung = new_bezeichnung
        root_obj.ArticleID = new_article_id
        root_obj.Label = new_label
        doc.recompute()

        if os.path.abspath(new_path) != os.path.abspath(old_path):
            doc.FileName = new_path
        doc.save()

        # 3. Betroffene Link-Dokumente neu speichern - FreeCADs PropertyXLink berechnet den
        # relativen Pfad zum verlinkten Dokument ERST beim Speichern neu, aus den dann AKTUELLEN
        # Pfaden beider Dokumente (siehe Modul-Docstring) - das Label-Setzen oben allein wuerde
        # die Datei selbst noch nicht aktualisieren.
        for doc_name in touched_docs:
            other_doc = App.getDocument(doc_name)
            other_doc.recompute()
            other_doc.save()

        # 4. Alte Datei erst JETZT entfernen - alle referenzierenden Dokumente zeigen inzwischen
        # auf den neuen Pfad, die alte Datei wird nirgends mehr gebraucht.
        if os.path.abspath(new_path) != os.path.abspath(old_path) and os.path.exists(old_path):
            os.remove(old_path)

    finally:
        # Dateien, die NUR fuer diesen Scan extra geoeffnet wurden, wieder schliessen - niemand
        # soll nach einem Umbenennen ploetzlich mehrere zusaetzliche Tabs offen haben.
        for doc_name in opened_here:
            if doc_name in App.listDocuments():
                try:
                    App.closeDocument(doc_name)
                except Exception as e:
                    App.Console.PrintWarning(
                        f"FCProject: Temporär geöffnetes Dokument '{doc_name}' konnte nicht "
                        f"wieder geschlossen werden: {str(e)}\n"
                    )

    return {
        "old_label": old_label,
        "new_label": new_label,
        "updated_links": updated_links,
        "updated_files": len(touched_docs),
    }


class RenamePartTaskPanel:
    """Aufgabenbereich-Panel (Gui.Control) zum Umbenennen eines PDM-Teils/einer Baugruppe -
    gleiches Protokoll wie FCProjectTaskPanel (TaskPanel.py): eigene Buttons statt Standard-
    OK/Abbrechen, _attached_doc fuer korrektes Schliessen beim Werkbench-/Dokument-Wechsel."""

    def __init__(self, root_obj):
        self.root_obj = root_obj
        self._attached_doc = Gui.ActiveDocument

        self.form = QtWidgets.QWidget()
        self.form.setWindowTitle("FCProject: Part/Baugruppe umbenennen")
        layout = QtWidgets.QVBoxLayout(self.form)
        layout.addWidget(QtWidgets.QLabel("<h3>FCProject: Part/Baugruppe umbenennen</h3>"))

        current_file = os.path.basename(root_obj.Document.FileName) if root_obj.Document.FileName else root_obj.Document.Name
        layout.addWidget(QtWidgets.QLabel(f"<i>Aktuelle Datei:</i> {current_file}"))

        layout.addWidget(QtWidgets.QLabel("<b>Bezeichnung:</b>"))
        self.bezeichnung_input = QtWidgets.QLineEdit(str(getattr(root_obj, "Bezeichnung", "")))
        layout.addWidget(self.bezeichnung_input)

        layout.addWidget(QtWidgets.QLabel("<b>Article-ID:</b>"))
        self.article_id_input = QtWidgets.QLineEdit(str(getattr(root_obj, "ArticleID", "")))
        layout.addWidget(self.article_id_input)

        self.info_label = QtWidgets.QLabel("")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        self.apply_btn = QtWidgets.QPushButton("Übernehmen")
        self.apply_btn.clicked.connect(self.on_apply_clicked)
        layout.addWidget(self.apply_btn)

        self.close_btn = QtWidgets.QPushButton("Schließen")
        self.close_btn.clicked.connect(self._on_close_clicked)
        layout.addWidget(self.close_btn)

        layout.addStretch()

        global _active_panel
        _active_panel = self

    # --- FreeCAD-Task-Panel-Protokoll (Gui.Control) - siehe TaskPanel.py fuer die Begruendung ---

    def getStandardButtons(self):
        return QtWidgets.QDialogButtonBox.NoButton

    def accept(self):
        return True

    def reject(self):
        global _active_panel
        if _active_panel is self:
            _active_panel = None
        return True

    def _on_close_clicked(self):
        self.reject()
        try:
            Gui.Control.closeDialog()
        except Exception as e:
            App.Console.PrintWarning(f"FCProject: Panel konnte nicht geschlossen werden: {str(e)}\n")

    def on_apply_clicked(self):
        new_bezeichnung = self.bezeichnung_input.text().strip()
        new_article_id = self.article_id_input.text().strip()

        if not new_article_id:
            QtWidgets.QMessageBox.warning(self.form, "FCProject", "Die Article-ID darf nicht leer sein.")
            return

        invalid_chars = set('\\/:*?"<>|')
        if invalid_chars & set(new_article_id + new_bezeichnung):
            QtWidgets.QMessageBox.warning(
                self.form, "FCProject",
                'Bezeichnung/Article-ID dürfen keine der Zeichen \\ / : * ? " < > | enthalten (Dateiname).'
            )
            return

        try:
            report = rename_pdm_object(self.root_obj, new_bezeichnung, new_article_id)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self.form, "FCProject", f"Umbenennen fehlgeschlagen: {str(e)}")
            return

        self.info_label.setText(
            f"Umbenannt in '{report['new_label']}'. "
            f"{report['updated_links']} Verlinkung(en) in {report['updated_files']} Datei(en) aktualisiert."
        )
        App.Console.PrintMessage(
            f"FCProject: '{report['old_label']}' -> '{report['new_label']}' umbenannt "
            f"({report['updated_links']} Verlinkung(en) in {report['updated_files']} Datei(en) angepasst).\n"
        )


class RenamePartCommand:
    def GetResources(self):
        import IconUtils
        icon_dir = os.path.join(os.path.dirname(__file__), 'resources', 'icons')
        return {
            'Pixmap': IconUtils.icon_path(icon_dir, 'rename_part.svg'),
            'MenuText': 'FCProject: Part/Baugruppe umbenennen',
            'ToolTip': 'Ändert Bezeichnung und Article-ID eines PDM-Teils/einer Baugruppe und passt alle Verlinkungen innerhalb des Projekts an'
        }

    def Activated(self):
        main_win = Gui.getMainWindow()
        if not App.ActiveDocument:
            QtWidgets.QMessageBox.warning(main_win, "FCProject", "Bitte öffne zuerst ein Dokument/Projekt.")
            return

        selection = Gui.Selection.getSelection()
        if len(selection) != 1:
            QtWidgets.QMessageBox.warning(main_win, "FCProject", "Bitte genau ein Part/Assembly-Objekt auswählen.")
            return

        root_obj = _resolve_root_pdm_object(selection[0])
        if root_obj is None:
            QtWidgets.QMessageBox.warning(
                main_win, "FCProject",
                "Das ausgewählte Objekt ist kein FCProject-PDM-Objekt (keine ArticleID gefunden)."
            )
            return

        self._close_active_task_dialog()

        panel = RenamePartTaskPanel(root_obj)
        Gui.Control.showDialog(panel, panel._attached_doc)

    @staticmethod
    def _close_active_task_dialog():
        """Schließt ein evtl. bereits offenes eigenes Rename-Panel, bevor ein neues geöffnet
        wird - sonst weist Gui.Control.showDialog() den Aufruf mit einer Konsolen-Warnung
        lautlos ab ("already an active task dialog"), siehe gleiches Muster in Commands.py."""
        global _active_panel
        panel = _active_panel
        if panel is not None:
            try:
                panel.reject()
                Gui.Control.closeDialog(panel._attached_doc)
            except Exception as e:
                App.Console.PrintWarning(f"FCProject: Vorhandenes Umbenennen-Panel konnte nicht geschlossen werden: {str(e)}\n")

    def IsActive(self):
        return App.ActiveDocument is not None


Gui.addCommand('FCProject_RenamePart', RenamePartCommand())
