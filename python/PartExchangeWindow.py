# FCProject: PartExchangeWindow - Joint-Referenzen von Original auf Ersatzteil ummappen
#
# Umfang bewusst auf zwei Punkte begrenzt:
#   1. Joints bleiben intakt (Reference1/Reference2 + Offset2 werden korrekt neu gesetzt)
#   2. die darin benutzten Referenzen werden korrekt auf das Ersatzteil umgehängt
# Auswirkungen auf andere Abhängigkeiten (Gruppenmitgliedschaft, generische
# Links, Ausblenden/Umbenennen des Originals) sind explizit ein späterer Schritt.

import os
import re
import weakref

import FreeCAD as App
import FreeCADGui as Gui
from PySide6 import QtWidgets, QtCore

from PartExchangeAnalyzer import (
    find_reference_root_and_path, full_reference_path, find_assembly,
    find_all_project_joints_referencing, GROUND_SIDE, RIGID_GROUP_SIDE
)

WHOLE_OBJECT_SIDES = (GROUND_SIDE, RIGID_GROUP_SIDE)  # kein Face/Edge-Konzept, keine manuelle Zuordnung noetig

ENTRY_ROLE = QtCore.Qt.UserRole
FILE_PATH_ROLE = QtCore.Qt.UserRole + 1

# Subname-Endung (z.B. "Face14") -> ViewProvider-Property mit einer Farbe pro Element.
# Teil von ViewProviderPartExt (Mod/Part/Gui/ViewProviderExt.h) - unabhängig von
# eigenen getDisplayModes()-Overrides (z.B. SheetMetal "BaseShape": liefert []) und
# unabhängig vom Selection-System.
_ELEMENT_COLOR_PROP = {"Face": "DiffuseColor", "Edge": "LineColorArray", "Vertex": "PointColorArray"}
_ELEMENT_COUNT_ATTR = {"Face": "Faces", "Edge": "Edges", "Vertex": "Vertexes"}


def _entry_original_obj(entry):
    """Liefert das TATSAECHLICHE Objekt, auf das dieser Eintrag zeigt (Reference1/2[0] je nach
    joint_side) - NICHT zwingend self.original_obj des Fensters, seit ein Eintrag auch aus einer
    ANDEREN Projektdatei stammen kann (find_all_project_joints_referencing(), 2026-08-30). Ohne
    das versuchte die Hervorhebung frueher immer relativ zum lokalen original_obj aufzuloesen,
    obwohl das Sub-Element (z.B. "Halter008.Face16") nur in der abweichenden Struktur der
    externen Datei existiert - fuehrte zu "Sub-object ... not found" (Nutzer-Report 2026-08-30).
    GroundedJoint.ObjectToGround/RigidGroupJoint.ObjectsToRigidGroup referenzieren das Objekt
    nicht ueber ein [obj, sub]-Tupel - dafuer traegt der Eintrag "target_obj" direkt."""
    if entry["joint_side"] in WHOLE_OBJECT_SIDES:
        return entry.get("target_obj")
    ref = entry["joint_obj"].Reference1 if entry["joint_side"] == 1 else entry["joint_obj"].Reference2
    return ref[0] if ref else None


def _joint_key(entry):
    """Dedup-/Mapping-Schluessel: NUR die referenzierte Fläche/Kante/LCS selbst (z.B. "Face9"),
    NICHT mehr welcher Joint/welches Dokument sie benutzt (2026-08-30, Nutzerwunsch). Dieselbe
    Referenz kann in mehreren Joints ueber mehrere Projektdateien hinweg auftauchen - der Nutzer
    soll sie nur EINMAL zuordnen muessen, _on_apply() wendet dieselbe Zuordnung dann auf ALLE
    Vorkommen an."""
    return entry["subelement"]


class _ReplacementSelectionObserver:
    """Beobachtet Gui.Selection und aktualisiert das 'Aktuelle 3D-Auswahl'-Label
    in Echtzeit, wenn der Nutzer im Ersatzteil-Dokument etwas anklickt.

    Nutzt weakref statt starker Referenz auf das Fenster: wenn das Fenster
    geschlossen/gelöscht wurde (auch ohne sauberen closeEvent-Aufruf), wird der
    Observer automatisch aus Gui.Selection entfernt und greift nicht mehr auf
    ungültige Qt-Objekte zu. setText() wird über QTimer.singleShot() im
    Haupt-Event-Loop aufgerufen - das verhindert Hänger wenn FreeCAD intern
    Selektions-Events während eines Datei-Dialogs auslöst.
    """

    def __init__(self, window):
        self._win_ref = weakref.ref(window)
        # KEIN Dokument-Filter mehr (2026-08-30, Nutzer-Report): ein Klick auf eine Flaeche kann
        # je nach Verschachtelungstiefe des Ersatzteils (Baugruppe -> Unterbaugruppe -> Einzelteil
        # -> ...) ein rohes Quellobjekt aus einem BELIEBIG tief verschachtelten, eigenen Dokument
        # liefern - eine einzelne LinkedObject-Aufloesung (siehe fruehere Version) deckt nur EINE
        # Ebene ab und griff bei mehrstufiger Verschachtelung nicht mehr (Diagnose bestaetigt per
        # Debug-Log: Klick landete in "CNC3018_006_B_Halter", zwei Ebenen unter dem erwarteten
        # "CNC3018_023_A_Halterbaugruppe"). Die Live-Vorschau ist rein informativ - zeigt jetzt
        # einfach JEDE Auswahl an, unabhaengig vom Dokument; die eigentliche Pruefung/Anwendung
        # passiert erst in _on_use_selection_clicked().

    def _get_win(self):
        """Gibt das Fenster zurück oder None (und entfernt sich selbst falls weg)."""
        win = self._win_ref()
        if win is None:
            try:
                Gui.Selection.removeObserver(self)
            except Exception:
                pass
        return win

    def addSelection(self, doc_name, obj_name, sub_name, x=0, y=0, z=0):
        win = self._get_win()
        if win is None:
            return
        try:
            doc = App.getDocument(doc_name)
            obj = doc.getObject(obj_name) if doc is not None else None
            label = getattr(obj, "Label", obj_name) if obj is not None else obj_name
            sub = sub_name or ""
            text = f"Aktuelle 3D-Auswahl: {label}.{sub}" if sub else f"Aktuelle 3D-Auswahl: {label}"
            label_widget = win.selection_label
            QtCore.QTimer.singleShot(0, lambda: label_widget.setText(text))
        except Exception as e:
            App.Console.PrintWarning(f"FCProject PartExchange SelectionObserver: {e}\n")

    def removeSelection(self, doc_name, obj_name, sub_name):
        pass

    def clearSelection(self, doc_name):
        # KEIN Dokument-Filter mehr (siehe addSelection oben) - clearSelection() feuert bei
        # jeder Aufhebung einer Auswahl in IRGENDEINEM Dokument, unabhaengig davon, wo die
        # zuletzt gezeigte Auswahl herkam; das Label wird trotzdem einfach zurueckgesetzt.
        win = self._get_win()
        if win is None:
            return
        label_widget = win.selection_label
        QtCore.QTimer.singleShot(0, lambda: label_widget.setText("Aktuelle 3D-Auswahl: –"))

    def setSelection(self, doc_name):
        pass



class PartExchangeWindow(QtWidgets.QDialog):
    """Nicht-modales Fenster: Joint-Referenzen des Originals auf das Ersatzteil ummappen."""

    def __init__(self, original_obj, replacement_obj, parent=None):
        super().__init__(parent or Gui.getMainWindow())
        self.original_obj = original_obj
        self.replacement_obj = replacement_obj
        self.original_doc = original_obj.Document
        self.replacement_doc = replacement_obj.Document
        # Anzeige-Dokument des Originals: das eigentliche Teil-Dokument (z.B.
        # NM3_017_P_Einzelteil_), nicht die Baugruppe - in der Baugruppe muss
        # für die Referenzprüfung nichts selektiert werden.
        self.original_display_doc = self._resolve_display_doc(original_obj)

        # Sammelt ALLE echten Joints im GESAMTEN Projekt (nicht nur im lokalen Dokument) - siehe
        # find_all_project_joints_referencing() (2026-08-30, ersetzt den fruaeheren "ein Fenster
        # pro externer Datei"-Ablauf, den der Nutzer bei vielen Treffern - z.B. 58 - als nicht
        # praktikabel verworfen hat). _skipped_files_log sammelt menschenlesbare Hinweise zu
        # uebersprungenen Kandidatendateien (kein Objekt/kein echter Joint gefunden).
        self._skipped_files_log = []
        self._original_joints = find_all_project_joints_referencing(original_obj, log=self._skipped_files_log)
        self._mappings = []  # [{"original": entry, "replacement_subelement": str}]
        self._pending_original = None
        self._forced_visible = []  # ViewObjects, die für die Hervorhebung sichtbar gemacht wurden
        self._color_overrides = {}  # (doc.Name, obj.Name, prop) -> (ViewObject, prop, Original-Farbliste)
        self._embedded_views = []  # [(widget, doc)] - aus dem Haupt-MDI-Bereich ausgeliehene 3D-Ansichten
        self._highlighted_docs = set()  # doc.Name - für Datum-Hervorhebung (Gui.Selection) benutzte Dokumente
        self._sel_observer = _ReplacementSelectionObserver(self)
        Gui.Selection.addObserver(self._sel_observer)

        self.setWindowTitle("FCProject: Part/Assembly ersetzen – Referenz-Zuordnung")
        self.setModal(False)

        self._build_ui()
        self._populate_joint_list()
        self._update_pending_label()
        self._update_apply_button_state()

        self._embed_3d_views()
        self._position_below_main_window()

    # ------------------------------------------------------------------ UI

    def _build_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)

        columns = QtWidgets.QHBoxLayout()

        left_box = QtWidgets.QGroupBox(f"Original: {self.original_obj.Label}")
        left_layout = QtWidgets.QVBoxLayout(left_box)
        left_layout.addWidget(QtWidgets.QLabel("Referenzen, die dieses Teil verwenden:"), stretch=0)
        self.joint_list = QtWidgets.QListWidget()
        self.joint_list.setMaximumHeight(110)
        self.joint_list.itemClicked.connect(self._on_joint_clicked)
        left_layout.addWidget(self.joint_list, stretch=0)
        self.original_view_container = QtWidgets.QVBoxLayout()
        left_layout.addLayout(self.original_view_container, stretch=1)
        columns.addWidget(left_box)

        self.right_box = right_box = QtWidgets.QGroupBox(f"Ersatzteil: {self.replacement_obj.Label}")
        right_layout = QtWidgets.QVBoxLayout(right_box)
        right_layout.addWidget(QtWidgets.QLabel(
            "Fläche/Kante/LCS am Ersatzteil im 3D-Fenster ODER im Baum anklicken "
            "(z.B. Origin-Achse/-Ebene), dann übernehmen:"
        ), stretch=0)
        self.selection_label = QtWidgets.QLabel("Aktuelle 3D-Auswahl: –")
        self.selection_label.setWordWrap(True)
        right_layout.addWidget(self.selection_label, stretch=0)
        self.use_selection_btn = QtWidgets.QPushButton("Als Referenz übernehmen")
        self.use_selection_btn.clicked.connect(self._on_use_selection_clicked)
        right_layout.addWidget(self.use_selection_btn, stretch=0)
        self.replacement_view_container = QtWidgets.QVBoxLayout()
        right_layout.addLayout(self.replacement_view_container, stretch=1)
        columns.addWidget(right_box)

        main_layout.addLayout(columns, stretch=3)

        self.pending_label = QtWidgets.QLabel()
        main_layout.addWidget(self.pending_label)

        self.highlight_warning_label = QtWidgets.QLabel()
        self.highlight_warning_label.setStyleSheet("color: #b8860b;")
        self.highlight_warning_label.setWordWrap(True)
        self.highlight_warning_label.setVisible(False)
        main_layout.addWidget(self.highlight_warning_label)

        # Projektweite Zusammenfassung (Nutzerwunsch 2026-08-30): self._original_joints wurde
        # bereits in __init__ ueber das GESAMTE Projekt gesammelt (siehe
        # find_all_project_joints_referencing()) - hier nur noch anzeigen, wie viele Dateien
        # betroffen sind, und welche Kandidatendateien uebersprungen wurden (kein Objekt/kein
        # echter Joint gefunden - vermutlich nur ein automatischer Assembly-Mirror-Eintrag).
        self.project_scope_label = QtWidgets.QLabel()
        self.project_scope_label.setStyleSheet("color: #888;")
        self.project_scope_label.setWordWrap(True)
        main_layout.addWidget(self.project_scope_label)

        # Datei-Auswahl (Nutzerwunsch 2026-08-30, verschaerft 2026-09-02): der Nutzer soll
        # explizit per Haken bestaetigen muessen, in WELCHEN der gefundenen Dateien
        # tatsaechlich umgehaengt werden soll. Standardmaessig KEIN Haken gesetzt (2026-09-02,
        # Nutzerwunsch): bei mehreren identischen Teilen im Projekt soll "Uebernehmen" nicht
        # aus Versehen ueberall gleichzeitig zuschlagen - der Nutzer waehlt bewusst aus.
        file_box = QtWidgets.QGroupBox("In diesen Dateien ersetzen:")
        file_layout = QtWidgets.QVBoxLayout(file_box)
        self.file_checklist = QtWidgets.QListWidget()
        self.file_checklist.setMaximumHeight(110)
        file_layout.addWidget(self.file_checklist)
        main_layout.addWidget(file_box)

        mapping_box = QtWidgets.QGroupBox("Zuordnungen (Referenz → Ersatzteil-Referenz)")
        mapping_layout = QtWidgets.QVBoxLayout(mapping_box)
        self.mapping_table = QtWidgets.QTableWidget(0, 3)
        self.mapping_table.setHorizontalHeaderLabels(["Referenz (Original)", "Ersatzteil-Referenz", ""])
        self.mapping_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.mapping_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self.mapping_table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.Fixed)
        self.mapping_table.setColumnWidth(2, 90)
        self.mapping_table.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.mapping_table.verticalHeader().setVisible(False)
        self.mapping_table.cellClicked.connect(self._on_mapping_row_clicked)
        mapping_layout.addWidget(self.mapping_table)
        main_layout.addWidget(mapping_box, stretch=1)

        bottom_row = QtWidgets.QHBoxLayout()
        bottom_row.addStretch()
        self.apply_btn = QtWidgets.QPushButton("Übernehmen")
        self.apply_btn.clicked.connect(self._on_apply)
        self.close_btn = QtWidgets.QPushButton("Schließen")
        self.close_btn.clicked.connect(self.close)
        bottom_row.addWidget(self.apply_btn)
        bottom_row.addWidget(self.close_btn)
        main_layout.addLayout(bottom_row)

    def _populate_joint_list(self):
        """Zeigt EINE Zeile pro EINDEUTIGER Referenz (z.B. "Face9"), nicht mehr eine Zeile pro
        rohem Joint-Vorkommen - dieselbe Fläche/Kante/LCS kann über mehrere Joints und mehrere
        Projektdateien hinweg auftauchen, soll aber nur einmal zugeordnet werden müssen
        (Nutzerwunsch 2026-08-30). item.setData() traegt dabei den ERSTEN Eintrag der Gruppe als
        Stellvertreter fuer die Hervorhebung - _joint_key() sorgt dafuer, dass das spaeter
        angelegte Mapping trotzdem fuer ALLE Vorkommen der Gruppe gilt (_on_apply() iteriert ja
        weiterhin ueber die volle, ungruppierte self._original_joints-Liste)."""
        self.joint_list.clear()
        groups = {}
        order = []
        auto_entries = []  # GroundedJoint/RigidGroupJoint - keine manuelle Zuordnung noetig
        for entry in self._original_joints:
            # GroundedJoint.ObjectToGround/RigidGroupJoint.ObjectsToRigidGroup referenzieren
            # immer das GANZE Ersatzteil-Objekt - es gibt kein Face/Edge zum Anklicken, also
            # keine manuelle Zuordnung noetig. Wird in _on_apply() automatisch mit umgehaengt
            # (siehe dortige Sonderbehandlung), taucht deshalb hier nicht in der
            # Zuordnungsliste auf (2026-08-30, Nutzer-Report "GroundedJoint ist beim alten
            # Original geblieben", analog fuer RigidGroup vorbereitet).
            if entry["joint_side"] in WHOLE_OBJECT_SIDES:
                auto_entries.append(entry)
                continue
            key = _joint_key(entry)
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(entry)

        for key in order:
            group = groups[key]
            representative = group[0]
            files = {e["file_path"] for e in group}
            if len(group) == 1:
                label = representative["label"]
            else:
                label = f'{representative["full_path"]} ({len(group)}x in {len(files)} Datei(en))'
            item = QtWidgets.QListWidgetItem(label)
            item.setData(ENTRY_ROLE, representative)
            self.joint_list.addItem(item)

        if not self._original_joints:
            self.joint_list.addItem("(keine Referenzen gefunden)")
            self.joint_list.setEnabled(False)
        elif not order and auto_entries:
            # Nur GroundedJoint/RigidGroupJoint gefunden, keine normalen Referenzen zum
            # Zuordnen - Liste bliebe sonst ohne Erklaerung leer.
            self.joint_list.addItem("(nur Erdung/Rigid Group - siehe Hinweis unten, keine Zuordnung nötig)")
            self.joint_list.setEnabled(False)

        files_involved = {e["file_path"] for e in self._original_joints}

        self.file_checklist.clear()
        for path in sorted(files_involved):
            # file_path ist entweder ein voller Dateipfad oder (falls ungespeichertes
            # Dokument) einfach der Dokumentname - os.path.basename() liefert in beiden
            # Faellen den richtigen Anzeigetext.
            item = QtWidgets.QListWidgetItem(os.path.basename(path))
            item.setData(FILE_PATH_ROLE, path)
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.Unchecked)
            self.file_checklist.addItem(item)

        parts = []
        if files_involved:
            parts.append(f"Betrifft {len(files_involved)} Datei(en), {len(order)} eindeutige Referenz(en).")
        if auto_entries:
            parts.append(
                f"{len(auto_entries)} GroundedJoint(s)/RigidGroup-Mitgliedschaft(en) werden "
                "automatisch mit auf das Ersatzteil umgehängt, ohne separate Zuordnung."
            )
        if self._skipped_files_log:
            parts.append(
                f"{len(self._skipped_files_log)} weitere Kandidatendatei(en) übersprungen "
                "(vermutlich nur automatische Assembly-Mirror-Einträge, keine echten Joints) - "
                "siehe Report View für Details."
            )
            for line in self._skipped_files_log:
                App.Console.PrintMessage(f"FCProject PartExchange: {line}\n")
        self.project_scope_label.setText(" ".join(parts))

    # ------------------------------------------------------------- Klicks

    def _on_joint_clicked(self, item):
        entry = item.data(ENTRY_ROLE)
        if entry is None:
            return
        self._pending_original = entry
        sub = entry.get("subelement") or ""
        entry_obj = _entry_original_obj(entry) or self.original_obj
        self._clear_highlight_selection()
        self._highlight_reference(entry_obj, sub, (1.0, 0.0, 1.0))
        self._update_pending_label()

    def _on_use_selection_clicked(self):
        # KEIN Dokument-Filter mehr (2026-08-30, Nutzer-Report): bei mehrstufig verschachtelten
        # Baugruppen kann ein 3D-Klick das rohe Quellobjekt aus einem BELIEBIG tief
        # verschachtelten, eigenen Dokument liefern (Debug-Log bestaetigte einen Fall zwei
        # Verlinkungsebenen unter dem Ersatzteil-Dokument) - Gui.Selection.getSelection() ohne
        # Dokument-Einschraenkung holt die zuletzt getroffene Auswahl unabhaengig davon, in
        # welchem Dokument sie technisch registriert wurde.
        # "*" statt "" ist entscheidend: FreeCADs SelectionSingleton::getDocument() behandelt
        # einen LEEREN String NICHT als "alle Dokumente", sondern als "nur das AKTIVE Dokument"
        # (isNullOrEmpty -> getActiveDocument()) - siehe Selection.cpp. Nur "*" ueberspringt den
        # Dokument-Filter komplett. Die eingebettete Ersatzteil-3D-Ansicht ist aber meist NICHT
        # das offiziell aktive Dokument, wodurch die Auswahl mit "" staendig leer zurueckkam,
        # obwohl das Live-Label sie schon korrekt anzeigte (2026-08-30, Nutzer-Report).
        selection = Gui.Selection.getSelectionEx("*")
        if not selection:
            QtWidgets.QMessageBox.warning(
                self, "FCProject",
                f"Bitte zuerst im 3D-Fenster oder im Baum eine Referenz von "
                f"'{self.replacement_obj.Label}' wählen (z.B. Fläche, Kante, LCS oder Origin-Achse)."
            )
            return

        sel_obj = selection[-1]
        # find_reference_root_and_path() deckt jetzt einheitlich alle Faelle ab: direkter
        # Treffer, beliebig tief verschachtelte/verlinkte Kind-Elemente (Link-Ketten aufgeloest -
        # siehe subpath_for_descendant()-Docstring), UND ein automatischer Aufstieg zum
        # umschliessenden Body/Part, falls das gewaehlte Ersatzteil-Objekt selbst nur ein
        # einzelnes internes Feature ist (z.B. "BaseFeature") und die geklickte Referenz ein
        # GESCHWISTER-Feature desselben Body ist (z.B. eine spaeter hinzugefuegte Bohrung) -
        # der Nutzer soll ein einzelnes Feature bewusst als Ersatzteil waehlen duerfen, ohne
        # dass spaetere Referenzen am selben Body faelschlich als "gehoert nicht zu" abgelehnt
        # werden (2026-08-30, Nutzer-Report).
        actual_root, path_to_obj = find_reference_root_and_path(self.replacement_obj, sel_obj.Object)
        if path_to_obj is None:
            QtWidgets.QMessageBox.warning(
                self, "FCProject",
                f"'{sel_obj.Object.Label}' gehört nicht zu '{self.replacement_obj.Label}'.\n"
                "Bitte eine Fläche/Kante im 3D-Fenster oder ein Element davon im Baum wählen "
                "(z.B. eine Origin-Achse/-Ebene oder ein LCS)."
            )
            return
        if actual_root is not self.replacement_obj:
            # Aufstieg war noetig - der umschliessende Body/Part ist der eigentlich gemeinte
            # Ersatzteil-Anker, alle folgenden Referenzen dieser Sitzung sollen relativ zu ihm
            # gebildet werden (sonst waere die gespeicherte Reference1/2 nicht konsistent).
            self.replacement_obj = actual_root
            self.right_box.setTitle(f"Ersatzteil: {self.replacement_obj.Label}")
        # Sub-Element-Name (Face/Edge/Vertex) anhängen, damit _set_element_color später den
        # Index auflösen und die spezifische Fläche einfärben kann.
        sub_el = sel_obj.SubElementNames[0] if sel_obj.SubElementNames else ""
        if not path_to_obj:
            subelement = sub_el
        elif sub_el:
            subelement = f"{path_to_obj}.{sub_el}"
        else:
            subelement = path_to_obj

        if self._pending_original is None:
            QtWidgets.QMessageBox.warning(
                self, "FCProject", "Bitte zuerst links einen Referenz-Eintrag des Originals auswählen."
            )
            return

        full_path = full_reference_path(self.replacement_obj, subelement)
        self.selection_label.setText(f"Aktuelle Auswahl: {full_path}")

        key = _joint_key(self._pending_original)
        self._mappings = [m for m in self._mappings if _joint_key(m["original"]) != key]
        self._mappings.append({
            "original": self._pending_original,
            "replacement_subelement": subelement,
            "replacement_full_path": full_path,
        })

        self._refresh_mapping_table()
        self._update_apply_button_state()

    def _highlight_reference(self, obj, sub, color):
        """Hebt die referenzierte Geometrie hervor - die Baugruppen-Ansicht wird dafür
        nicht gebraucht, der Wechsel passiert direkt im Teil-Dokument.

        Zwei Fälle, je nach Referenztyp:
        - Face/Edge/Vertex (echte Shape-Topologie): direktes Einfärben über
          DiffuseColor/LineColorArray/PointColorArray, ohne Gui.Selection (das
          löst bei ViewProvidern ohne Element-Hervorhebung, z.B. SheetMetals
          "BaseShape", eine Ganzes-Objekt-Auswahl aus, die die normale
          Schattierung durch eine reine Drahtmodell-Darstellung ersetzt).
        - Datum-Elemente (Origin-Achse/-Ebene, LCS) ohne Face/Edge/Vertex-Index:
          keine Shape-Topologie zum Einfärben vorhanden - hier ist die normale
          Gui.Selection-Auswahl der richtige, "nicht-3D-Engine-nahe" Weg und
          funktioniert für diese FreeCAD-Kernobjekte zuverlässig.
        """
        self._set_highlight_warning(None)
        if not sub:
            return
        self._ensure_visible(obj, sub)
        display_obj, colored = self._set_element_color(obj, sub, color)
        if display_obj is None:
            self._set_highlight_warning(sub)
            return
        if not colored:
            self._highlight_via_selection(obj, sub, display_obj)
        self._ensure_view(display_obj.Document)
        try:
            Gui.setActiveDocument(display_obj.Document.Name)
        except Exception:
            pass

    def _highlight_via_selection(self, obj, sub, display_obj=None):
        """Gui.Selection-Auswahl für Datum-Elemente (Origin-Achse/-Ebene, LCS).

        Falls das aufgelöste Datum-Objekt (display_obj) in einem anderen Dokument
        liegt als obj (z.B. obj=Pattern-Kopie in Assembly, display_obj=XY-Ebene im
        Teil-Dok), wird die Selektion im Teil-Dok durchgeführt - sonst würde sie in
        der Assembly landen, obwohl die eingebettete Ansicht das Teil-Dok zeigt.
        """
        if display_obj is not None and display_obj.Document is not obj.Document:
            root, root_sub = self._datum_selection_root(display_obj)
            if root is not None:
                self._do_addselection(root.Document.Name, root.Name, root_sub)
                return
        self._do_addselection(obj.Document.Name, obj.Name, sub or "")

    def _do_addselection(self, doc_name, obj_name, sub):
        try:
            Gui.Selection.removeSelectionGate(doc_name)
        except Exception:
            pass
        try:
            Gui.Selection.addSelection(doc_name, obj_name, sub)
            self._highlighted_docs.add(doc_name)
        except Exception as e:
            App.Console.PrintWarning(
                f"FCProject PartExchange: '{obj_name}.{sub}' konnte nicht selektiert werden: {str(e)}\n"
            )

    @staticmethod
    def _datum_selection_root(datum_obj):
        """Traversiert die Parents-Kette nach oben um Root-Objekt und Sub-Pfad für
        addSelection im Kontext des Teil-Dokuments zu finden.

        Beispiel: XY_Plane002 (Parents: Origin005 → NM3_002_R_Alu_40x001)
        → gibt (NM3_002_R_Alu_40x001, "Origin005.XY_Plane002.") zurück, sodass
        addSelection(part_doc, root.Name, "Origin005.XY_Plane002.") korrekt
        die XY-Ebene turquois hervorhebt.
        """
        doc = datum_obj.Document
        current = datum_obj
        path_parts = []
        seen = set()
        try:
            while True:
                oid = id(current)
                if oid in seen:
                    break
                seen.add(oid)
                parents = [(p, path) for p, path in (getattr(current, "Parents", None) or [])
                           if p.Document is doc]
                if not parents:
                    break
                parent, path = parents[0]
                path_parts.insert(0, path)
                current = parent
        except Exception:
            return None, None
        return current, "".join(path_parts)

    def _clear_highlight_selection(self):
        for doc_name in self._highlighted_docs:
            try:
                Gui.Selection.clearSelection(doc_name)
            except Exception:
                pass
        self._highlighted_docs.clear()

    def _set_element_color(self, obj, sub, color):
        """Setzt eine Farbe für genau das referenzierte Element über DiffuseColor/
        LineColorArray/PointColorArray (ViewProviderPartExt) - das ist Teil der
        Geometrie-Darstellung selbst, nicht des Selection-Highlight-Mechanismus.
        Gibt (eingefärbtes/aufgelöstes Objekt, ob tatsächlich eingefärbt wurde)
        zurück; Objekt ist None, wenn die Referenz nicht auflösbar war.
        """
        try:
            chain = obj.getSubObjectList(sub)
        except Exception:
            chain = None
        if not chain:
            return None, False
        leaf = chain[-1]
        tip = getattr(leaf, "Tip", None)
        display_obj = tip if tip is not None else leaf
        vobj = getattr(display_obj, "ViewObject", None)
        if vobj is None:
            return None, False
        if not hasattr(display_obj, "Shape"):
            # Datum-Objekt (App::Line, App::Plane, LCS) — kein Shape zum Einfärben,
            # aber via Gui.Selection hervorhebbar (turquoise wie beim manuellen Klick).
            return display_obj, False

        tail = sub.rsplit(".", 1)[-1] if "." in sub else sub
        match = re.match(r"([A-Za-z]+?)(\d+)$", tail)
        if not match:
            return display_obj, False
        kind, number = match.group(1), int(match.group(2))
        prop = _ELEMENT_COLOR_PROP.get(kind)
        count_attr = _ELEMENT_COUNT_ATTR.get(kind)
        if prop is None or not hasattr(vobj, prop):
            return display_obj, False
        try:
            count = len(getattr(display_obj.Shape, count_attr))
        except Exception:
            return display_obj, False
        index = number - 1
        if index < 0 or index >= count:
            return display_obj, False

        key = (display_obj.Document.Name, display_obj.Name, prop)
        if key not in self._color_overrides:
            try:
                original = list(getattr(vobj, prop))
            except Exception:
                original = []
            if len(original) != count:
                base = getattr(vobj, "ShapeColor", (0.8, 0.8, 0.8, 1.0))
                original = [base] * count
            self._color_overrides[key] = (vobj, prop, original)

        # 4. Tupel-Wert ist Alpha (1.0 = voll sichtbar/opak), KEINE Transparenz -
        # ViewProviderPartExtPy.cpp parst ihn direkt in Base::Color.a; 0.0 macht
        # die Fläche komplett unsichtbar.
        _, _, original = self._color_overrides[key]
        new_colors = list(original)
        new_colors[index] = (color[0], color[1], color[2], 1.0)
        try:
            setattr(vobj, prop, new_colors)
        except Exception as e:
            App.Console.PrintWarning(
                f"FCProject PartExchange: {prop} für '{display_obj.Label}' konnte nicht gesetzt werden: {str(e)}\n"
            )
            return display_obj, False
        return display_obj, True

    def _set_highlight_warning(self, info):
        if not info:
            self.highlight_warning_label.setVisible(False)
            return
        self.highlight_warning_label.setText(
            f"⚠ Referenz '{info}' konnte nicht eingefärbt werden - "
            "Bitte den Textpfad oben manuell prüfen."
        )
        self.highlight_warning_label.setVisible(True)

    def _ensure_visible(self, obj, sub):
        """Macht alle Objekte entlang des Subnamen-Pfads sichtbar, bevor sie selektiert werden.

        Viele Referenzen (z.B. Kaufteil-Bodies) sind standardmäßig ausgeblendet
        (zur Entflechtung der Baugruppendarstellung) - eine Selektion auf einem
        unsichtbaren Objekt erzeugt aber keine sichtbare Hervorhebung. Bereits
        ausgeblendete Objekte werden vermerkt, um sie beim Schließen des Fensters
        wieder auf den Ursprungszustand zurückzusetzen.
        """
        try:
            chain = obj.getSubObjectList(sub) if sub else [obj]
        except Exception:
            chain = [obj]
        for o in chain:
            vobj = getattr(o, "ViewObject", None)
            if vobj is None:
                continue
            # Partiell geladene Dokumente (als Link-Abhängigkeit geladen, nicht voll
            # geöffnet): Visibility-Änderungen dort erzeugen FreeCAD-Warnmeldungen
            # ("Changes to partial loaded document will not be saved") und werden
            # ohnehin nicht persistiert - überspringen.
            if getattr(o.Document, "Partial", False):
                continue
            try:
                if not vobj.Visibility:
                    self._forced_visible.append(vobj)
                    vobj.Visibility = True
            except Exception as e:
                App.Console.PrintWarning(
                    f"FCProject PartExchange: '{o.Label}' konnte nicht sichtbar gemacht werden: {str(e)}\n"
                )

    def closeEvent(self, event):
        try:
            Gui.Selection.removeObserver(self._sel_observer)
        except Exception:
            pass
        for vobj in self._forced_visible:
            try:
                vobj.Visibility = False
            except Exception:
                pass
        self._forced_visible.clear()
        for vobj, prop, original in self._color_overrides.values():
            try:
                setattr(vobj, prop, original)
            except Exception:
                pass
        self._color_overrides.clear()
        self._clear_highlight_selection()
        self._restore_3d_views()
        super().closeEvent(event)

    # ----------------------------------------------------------- Mapping

    def _update_pending_label(self):
        text = self._pending_original["label"] if self._pending_original else "–"
        self.pending_label.setText(f"Ausgewählte Original-Referenz: <b>{text}</b>")

    def _refresh_mapping_table(self):
        self.mapping_table.setRowCount(0)
        for row, mapping in enumerate(self._mappings):
            self.mapping_table.insertRow(row)
            self.mapping_table.setItem(row, 0, QtWidgets.QTableWidgetItem(mapping["original"]["label"]))
            repl_label = mapping.get("replacement_full_path") or "(ganzes Objekt)"
            self.mapping_table.setItem(row, 1, QtWidgets.QTableWidgetItem(repl_label))

            remove_btn = QtWidgets.QPushButton("Entfernen")
            remove_btn.clicked.connect(lambda _checked=False, r=row: self._on_remove_mapping(r))
            self.mapping_table.setCellWidget(row, 2, remove_btn)

    def _on_remove_mapping(self, row):
        if 0 <= row < len(self._mappings):
            del self._mappings[row]
            self._refresh_mapping_table()
            self._update_apply_button_state()

    def _on_mapping_row_clicked(self, row, _column):
        if not (0 <= row < len(self._mappings)):
            return
        mapping = self._mappings[row]
        original = mapping["original"]
        self._pending_original = original
        self._update_pending_label()

        self._clear_highlight_selection()
        original_sub = original.get("subelement") or ""
        self._highlight_reference(self.original_obj, original_sub, (1.0, 0.0, 1.0))
        replacement_sub = mapping["replacement_subelement"] or ""
        self._highlight_reference(self.replacement_obj, replacement_sub, (0.0, 1.0, 1.0))

    def _update_apply_button_state(self):
        # GroundedJoint-/RigidGroup-Eintraege brauchen keine manuelle Zuordnung (siehe
        # _populate_joint_list()) - sonst bliebe "Übernehmen" dauerhaft deaktiviert, weil fuer
        # sie nie ein Mapping erstellt werden kann (2026-08-30, Nutzer-Report).
        required_keys = {
            _joint_key(entry) for entry in self._original_joints
            if entry["joint_side"] not in WHOLE_OBJECT_SIDES
        }
        mapped_keys = {_joint_key(m["original"]) for m in self._mappings}
        has_ground_only = bool(self._original_joints) and not required_keys
        self.apply_btn.setEnabled(
            has_ground_only or (len(required_keys) > 0 and required_keys.issubset(mapped_keys))
        )

    # ------------------------------------------------------- Fenster-Layout

    @staticmethod
    def _resolve_display_obj(obj):
        """Das Objekt, das `obj`s tatsächliche Geometrie traegt (fuer App::Link-Ketten, z.B.
        Pattern-Kopie → Assembly-Link → Teil-Dokument, wird die gesamte LinkedObject-Kette
        durchlaufen, bis kein weiterer Link mehr folgt)."""
        seen = set()
        current = obj
        while True:
            obj_id = id(current)
            if obj_id in seen:
                break
            seen.add(obj_id)
            linked = getattr(current, "LinkedObject", None)
            if linked is None:
                break
            current = linked
        return current

    @staticmethod
    def _resolve_display_doc(obj):
        """Das Dokument, in dem `obj` tatsächlich seine Geometrie zeigt - siehe
        _resolve_display_obj()."""
        return PartExchangeWindow._resolve_display_obj(obj).Document

    def _embed_3d_views(self):
        """Erzeugt für Original und Ersatzteil je eine ZUSÄTZLICHE 3D-Ansicht und bettet
        sie direkt in diesen Dialog ein - so sieht man beides zusammen mit der
        Joint-Zuordnung, ohne zwischen Fenstern wechseln zu müssen.

        Wichtig: die bereits offene(n) Ansicht(en) im Hauptfenster werden NICHT
        angefasst/geschlossen - schließt man die letzte Ansicht eines Dokuments,
        schließt FreeCAD darüber das ganze Dokument. Stattdessen wird hier je eine
        eigene, zusätzliche View erzeugt, die beim Schließen dieses Dialogs einfach
        wieder verworfen wird (das Dokument hat dann immer noch seine ursprüngliche
        Ansicht im Hauptfenster). Werkzeugleisten/Navigationswürfel bleiben im
        Hauptfenster zurück (hier nicht nötig, nur Auswahl/Ansicht wird gebraucht);
        Klicken/Zoomen/Rotieren in der eingebetteten Ansicht funktioniert normal.
        """
        main_win = Gui.getMainWindow()
        mdi_area = main_win.findChild(QtWidgets.QMdiArea)
        if mdi_area is None:
            return
        original_focus = self._resolve_display_obj(self.original_obj)
        self._embed_one(mdi_area, self.original_display_doc, self.original_view_container, original_focus)
        # IMMER eine eigene Ansicht fuers Ersatzteil erzeugen, auch wenn Original und Ersatzteil
        # im selben Dokument liegen (z.B. beide direkt in derselben Baugruppe eingefuegt statt in
        # getrennten Dokumenten) - Gui::View3DInventor unterstuetzt mehrere unabhaengige Ansichten
        # desselben Dokuments problemlos. Vorher wurde die zweite Ansicht in diesem Fall
        # uebersprungen (Annahme: "sieht man ja schon in der ersten Ansicht") - das liess den
        # rechten Bereich komplett leer und war verwirrend, obwohl die Auswahl selbst technisch
        # funktionierte (Nutzer-Report 2026-08-30: "Ersatzteil wird nicht angezeigt").
        # WICHTIG: hier bewusst OHNE _resolve_display_obj()-Kettenaufloesung, anders als beim
        # Original - self.replacement_doc wird ebenfalls unaufgeloest gesetzt (replacement_obj.
        # Document direkt, siehe __init__), focus_obj und die eingebettete Ansicht muessen also
        # dasselbe Dokument referenzieren. Mit der Aufloesung landete der Fokus bei einem per
        # Link-Kette eingebundenen Ersatzteil in einem ANDEREN Dokument als die tatsaechlich
        # eingebettete Ansicht - der focus_obj.Document is doc-Check in _embed_one() schlug fehl
        # und fiel auf "ganzes Dokument zeigen" zurueck (Nutzer-Report 2026-08-30: zweite
        # Ersatzteil-Ansicht zeigte die komplette FuehrungsBaugruppe400 statt nur das neue Teil).
        self._embed_one(mdi_area, self.replacement_doc, self.replacement_view_container, self.replacement_obj)

    def _embed_one(self, mdi_area, doc, container_layout, focus_obj=None):
        try:
            gui_doc = Gui.getDocument(doc.Name)
            gui_doc.createView("Gui::View3DInventor")
            QtWidgets.QApplication.processEvents()

            # Per id()/Objekt-Identität lässt sich ein "neues" Subwindow nicht zuverlässig
            # erkennen (PySide6 liefert bei subWindowList() ggf. neue Wrapper-Objekte für
            # dasselbe QMdiSubWindow zurück - id()-Diffing griff dadurch z.B. auch die
            # FreeCAD-Startseite ab). Stattdessen nach Titel filtern (enthält Label/Name
            # des Dokuments) und das LETZTE Treffer-Fenster nehmen, da QMdiArea neue
            # Subwindows ans Ende der Liste anhängt - die soeben erzeugte Ansicht steht
            # also hinter der/den bereits vorher offenen Ansicht(en) desselben Dokuments.
            label = doc.Label or doc.Name
            matches = [
                w for w in mdi_area.subWindowList()
                if label in (w.windowTitle() or "") or doc.Name in (w.windowTitle() or "")
            ]
            if not matches:
                return
            sub_window = matches[-1]
            widget = sub_window.widget()
            if widget is None:
                return

            Gui.setActiveDocument(doc.Name)
            QtWidgets.QApplication.processEvents()
            try:
                # Eine von der Assembly-Werkbank hinterlassene Selection-Gate würde
                # spätere manuelle 3D-Klicks (Ersatzteil-Referenz wählen) sonst lautlos
                # ablehnen.
                Gui.Selection.removeSelectionGate(doc.Name)
            except Exception:
                pass
            try:
                # Direkt über das View-Objekt statt Gui.SendMsgToActiveView("ViewFit") - Letzteres
                # ist seit FreeCAD 26.3 deprecated und wird in 27.2 entfernt.
                gui_doc = Gui.getDocument(doc.Name)
                if gui_doc and gui_doc.ActiveView:
                    if focus_obj is not None and focus_obj.Document is doc:
                        self._fit_view_to_object(gui_doc.ActiveView, doc, focus_obj)
                    else:
                        gui_doc.ActiveView.fitAll()
            except Exception:
                pass

            self._show_datum_objects(doc)

            widget.setParent(None)
            widget.setMinimumHeight(220)
            container_layout.addWidget(widget)
            widget.show()
            self._embedded_views.append((widget, doc))
        except Exception as e:
            App.Console.PrintWarning(
                f"FCProject PartExchange: 3D-Ansicht für '{doc.Name}' konnte nicht eingebettet werden: {str(e)}\n"
            )

    @staticmethod
    def _collect_keep_set(focus_obj):
        """Liefert focus_obj + all seine Vorfahren (damit sie als Container sichtbar bleiben)
        + all seine Nachfahren (gehoeren optisch mit dazu) - alles ausserhalb dieser Menge darf
        fuer den Fokus-Zoom ausgeblendet werden."""
        keep = {id(focus_obj)}

        ancestor = focus_obj
        while True:
            parent = ancestor.getParentGeoFeatureGroup()
            if parent is None or id(parent) in keep:
                break
            keep.add(id(parent))
            ancestor = parent

        stack = [focus_obj]
        while stack:
            current = stack.pop()
            children = list(getattr(current, "Group", []) or []) + list(getattr(current, "OutList", []) or [])
            for child in children:
                if id(child) not in keep:
                    keep.add(id(child))
                    stack.append(child)

        return keep

    @classmethod
    def _fit_view_to_object(cls, view, doc, focus_obj):
        """Zoomt `view` gezielt auf `focus_obj`, nicht auf das ganze Dokument - View3DInventorPy
        hat keine eigene "auf Objekt X einpassen"-API, nur fitAll() ueber ALLE sichtbaren
        Objekte. In einer Assembly-Datei haengen praktisch ALLE Teile unter demselben EINEN
        Assembly-Container - ein reiner "keinen Elternteil"-Filter (echtes Top-Level) trifft
        deshalb fast nie zu und blendet nichts aus. Stattdessen werden gezielt alle Objekte
        ausserhalb von focus_objs eigenem Vorfahren-/Nachfahren-Pfad ausgeblendet (siehe
        _collect_keep_set()), fitAll() aufgerufen, danach die urspruengliche Sichtbarkeit wieder
        hergestellt.

        Ohne das zeigten beide eingebetteten Ansichten (Original UND Ersatzteil) schlicht die
        komplette Baugruppe, sobald beide im selben Dokument liegen - nicht zu unterscheiden,
        welche Ansicht wozu gehoert (Nutzer-Report 2026-08-30)."""
        hidden = []
        keep = cls._collect_keep_set(focus_obj)
        focus_vobj = getattr(focus_obj, "ViewObject", None)
        was_hidden = focus_vobj is not None and not focus_vobj.Visibility
        try:
            for obj in doc.Objects:
                if id(obj) in keep:
                    continue
                vobj = getattr(obj, "ViewObject", None)
                if vobj is None or not vobj.Visibility:
                    continue
                hidden.append(vobj)
                vobj.Visibility = False
            if was_hidden:
                focus_vobj.Visibility = True
            view.fitAll()
        finally:
            for vobj in hidden:
                try:
                    vobj.Visibility = True
                except Exception:
                    pass
            if was_hidden:
                try:
                    focus_vobj.Visibility = False
                except Exception:
                    pass

    _DATUM_TYPES = (
        "App::Origin",
        "App::LocalCoordinateSystem",
        "PartDesign::Line",
        "PartDesign::Plane",
        "PartDesign::Point",
    )

    def _show_datum_objects(self, doc):
        """Macht alle Datum-/Referenz-Objekte im Dokument sichtbar (Origin, LCS,
        Datum-Achse/-Ebene/-Punkt) und merkt sie für das Wiederherstellen beim
        Schließen vor (via _forced_visible)."""
        if getattr(doc, "Partial", False):
            return
        for obj in doc.Objects:
            try:
                if not any(obj.isDerivedFrom(t) for t in self._DATUM_TYPES):
                    continue
                vobj = getattr(obj, "ViewObject", None)
                if vobj is None or vobj.Visibility:
                    continue
                self._forced_visible.append(vobj)
                vobj.Visibility = True
            except Exception:
                pass

    def _restore_3d_views(self):
        """Verwirft die für die Einbettung eigens erzeugten Zusatz-Ansichten wieder -
        die ursprüngliche(n) Ansicht(en) im Hauptfenster waren nie betroffen, daher
        ist hier ein einfaches close() sicher (es bleibt immer mindestens eine
        andere Ansicht des Dokuments übrig)."""
        for widget, doc in list(self._embedded_views):
            try:
                widget.close()
            except Exception as e:
                App.Console.PrintWarning(
                    f"FCProject PartExchange: 3D-Ansicht für '{getattr(doc, 'Name', '?')}' "
                    f"konnte nicht geschlossen werden: {str(e)}\n"
                )
        self._embedded_views.clear()

    @staticmethod
    def _ensure_view(doc):
        """Erstellt ein 3D-Fenster für `doc`, falls noch keins offen ist (z.B. bei
        Dokumenten, die nur als Link-Abhängigkeit nachgeladen wurden)."""
        try:
            gui_doc = Gui.getDocument(doc.Name)
            if gui_doc.ActiveView is None:
                gui_doc.createView("Gui::View3DInventor")
        except Exception as e:
            App.Console.PrintWarning(
                f"FCProject PartExchange: 3D-Fenster für '{doc.Name}' konnte nicht erstellt werden: {str(e)}\n"
            )

    def _position_below_main_window(self):
        try:
            main_win = Gui.getMainWindow()
            geo = main_win.geometry()
            width = int(geo.width() * 0.8)
            # Höher als früher, da die eingebetteten 3D-Ansichten Platz brauchen -
            # an der Bildschirmhöhe geclampt, damit der Dialog sichtbar bleibt.
            screen = QtWidgets.QApplication.primaryScreen()
            max_height = screen.availableGeometry().height() if screen else geo.height()
            height = min(int(geo.height() * 0.9), max_height - 60)
            self.resize(width, height)
            x = geo.x() + (geo.width() - width) // 2
            y = geo.y() + (geo.height() - height) // 2
            self.move(x, max(y, 0))
        except Exception:
            pass

    # ------------------------------------------------------------- Apply

    def _bring_doc_to_front(self, doc):
        """Holt das MDI-Fenster von `doc` nach vorne (Nutzerwunsch 2026-09-02: die Datei soll
        beim Abarbeiten "zur Bearbeitung geöffnet" - sprich sichtbar/aktiv - sein, nicht nur
        im Hintergrund verändert werden). Die Datei selbst ist zu diesem Zeitpunkt bereits
        geladen (find_all_project_joints_referencing() öffnet alle Kandidaten beim Sammeln) -
        hier wird nur ihr Fenster in den Vordergrund geholt."""
        try:
            self._ensure_view(doc)
            main_win = Gui.getMainWindow()
            mdi_area = main_win.findChild(QtWidgets.QMdiArea)
            if mdi_area is None:
                return
            label = doc.Label or doc.Name
            matches = [
                w for w in mdi_area.subWindowList()
                if label in (w.windowTitle() or "") or doc.Name in (w.windowTitle() or "")
            ]
            if matches:
                mdi_area.setActiveSubWindow(matches[-1])
            Gui.setActiveDocument(doc.Name)
        except Exception as e:
            App.Console.PrintWarning(
                f"FCProject PartExchange: Fenster für '{doc.Name}' konnte nicht nach vorne "
                f"geholt werden: {str(e)}\n"
            )

    def _confirm_replace_instance(self, entry):
        """EIN Bestätigungsdialog für GENAU dieses Vorkommen (Nutzerwunsch 2026-09-02): bei
        mehreren identischen Teilen im Projekt soll gezielt nur eine einzelne Instanz ersetzt
        werden können, statt automatisch alle gleichnamigen Vorkommen auf einmal. Hebt vorher
        die betroffene Original-Instanz im 3D-Fenster/Baum hervor ("Ziel selektieren"), damit
        der Nutzer sieht, welches der mehreren gleichen Teile gerade zur Debatte steht.

        Gibt "yes" (dieses Vorkommen ersetzen), "no" (überspringen) oder "all" (dieses UND
        alle weiteren Vorkommen ohne erneute Rückfrage ersetzen) zurück."""
        target_obj = _entry_original_obj(entry)
        self._clear_highlight_selection()
        if target_obj is not None:
            # Fokus + Selektion auf das GANZE Teil, nicht nur die referenzierte Fläche/Kante
            # (Nutzerwunsch 2026-09-02): bei mehreren optisch IDENTISCHEN Teilen in derselben
            # Baugruppe reicht das reine Einfärben einer Fläche nicht, wenn die Instanz gerade
            # ausserhalb des sichtbaren Bereichs liegt oder winzig ist - die Ansicht zoomt
            # deshalb zusätzlich auf genau dieses Teil (_fit_view_to_object(), wie schon für
            # die eingebetteten Original-/Ersatzteil-Ansichten benutzt) und selektiert es als
            # Ganzes (Baum + 3D), bevor zusätzlich die einzelne Fläche/Kante eingefärbt wird.
            focus_doc = target_obj.Document
            self._bring_doc_to_front(focus_doc)
            try:
                gui_doc = Gui.getDocument(focus_doc.Name)
                if gui_doc and gui_doc.ActiveView:
                    self._fit_view_to_object(gui_doc.ActiveView, focus_doc, target_obj)
            except Exception as e:
                App.Console.PrintWarning(
                    f"FCProject PartExchange: Fokus auf '{target_obj.Label}' fehlgeschlagen: {str(e)}\n"
                )
            self._do_addselection(focus_doc.Name, target_obj.Name, "")
            self._highlight_reference(target_obj, entry.get("subelement") or "", (1.0, 0.0, 1.0))

        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle("FCProject: Vorkommen ersetzen?")
        box.setText(f"Dieses Vorkommen ersetzen?\n\n{entry.get('label', '')}")
        yes_btn = box.addButton("Ja", QtWidgets.QMessageBox.YesRole)
        box.addButton("Nein (überspringen)", QtWidgets.QMessageBox.NoRole)
        all_btn = box.addButton("Alle ersetzen", QtWidgets.QMessageBox.YesRole)
        box.setDefaultButton(yes_btn)
        box.exec()
        clicked = box.clickedButton()
        if clicked is all_btn:
            return "all"
        if clicked is yes_btn:
            return "yes"
        return "no"

    def _confirm_save_doc(self, doc):
        """Fragt nach dem Bearbeiten EINER Datei explizit, ob/wie gespeichert werden soll
        (Nutzerwunsch 2026-09-02) - statt wie bisher automatisch zu speichern, bevor es mit
        der nächsten angehakten Datei weitergeht."""
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle("FCProject: Datei speichern?")
        doc_label = os.path.basename(doc.FileName) if doc.FileName else doc.Name
        box.setText(f"'{doc_label}' wurde geändert. Jetzt speichern?")
        yes_btn = box.addButton("Ja", QtWidgets.QMessageBox.YesRole)
        box.addButton("Nein", QtWidgets.QMessageBox.NoRole)
        saveas_btn = box.addButton("Speichern unter…", QtWidgets.QMessageBox.ActionRole)
        box.setDefaultButton(yes_btn)
        box.exec()
        clicked = box.clickedButton()
        if clicked is yes_btn:
            try:
                doc.save()
            except Exception as e:
                QtWidgets.QMessageBox.warning(self, "FCProject", f"Speichern fehlgeschlagen: {str(e)}")
        elif clicked is saveas_btn:
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, "Speichern unter", doc.FileName or "", "FreeCAD-Dokument (*.FCStd)"
            )
            if path:
                try:
                    doc.saveAs(path)
                except Exception as e:
                    QtWidgets.QMessageBox.warning(
                        self, "FCProject", f"Speichern unter fehlgeschlagen: {str(e)}"
                    )
        # "Nein" -> bewusst ungespeichert lassen, weiter zur nächsten Datei.

    def _on_apply(self):
        """Wendet das (einmalige, pro eindeutiger Referenz erstellte) Mapping auf die vom
        Nutzer BESTAETIGTEN Joint-Vorkommen im GESAMTEN Projekt an - nicht nur im lokalen
        Dokument. Gruppiert dafür self._original_joints (via find_all_project_joints_
        referencing() über alle betroffenen Dateien hinweg gesammelt) nach ihrem jeweiligen
        Zieldokument, erstellt pro Dokument GENAU EINEN lokalen Ersatzteil-Link, loest/speichert
        danach jedes betroffene Dokument.

        Nutzerwunsch 2026-09-02 ("4 gleiche Parts, nur eins soll geaendert werden"): anders als
        frueher wird NICHT mehr automatisch JEDES Vorkommen ersetzt, das die Zuordnungstabelle
        abdeckt - stattdessen wird pro angehakter Datei und darin PRO EINZELNEM Joint-Vorkommen
        einzeln nachgefragt (_confirm_replace_instance(), mit "Alle ersetzen"-Abkuerzung), und
        nach jeder Datei explizit gefragt, ob/wie gespeichert werden soll
        (_confirm_save_doc())."""
        errors = []
        rewired_joints = 0
        mapping_by_key = {_joint_key(m["original"]): m for m in self._mappings}

        # Nur Dateien beruecksichtigen, die der Nutzer in der Checkliste angehakt hat
        # (Nutzerwunsch 2026-08-30: explizite Bestaetigung statt automatisch ALLE Dateien).
        checked_paths = set()
        for i in range(self.file_checklist.count()):
            item = self.file_checklist.item(i)
            if item.checkState() == QtCore.Qt.Checked:
                checked_paths.add(item.data(FILE_PATH_ROLE))

        if not checked_paths:
            QtWidgets.QMessageBox.warning(
                self, "FCProject",
                "Bitte mindestens eine Datei in der Liste \"In diesen Dateien ersetzen\" "
                "anhaken, bevor du übernimmst."
            )
            return

        entries_by_doc = {}
        for entry in self._original_joints:
            if entry["file_path"] not in checked_paths:
                continue
            entries_by_doc.setdefault(entry["joint_obj"].Document, []).append(entry)

        touched_docs = []  # nur Dokumente, in denen tatsaechlich etwas umgehaengt wurde
        # "Alle ersetzen" gilt global fuer den Rest dieses Durchlaufs (ueber alle noch
        # kommenden Dateien/Vorkommen hinweg), nicht nur fuer die aktuelle Datei.
        replace_all_remaining = False

        for doc, doc_entries in entries_by_doc.items():
            assembly_obj = find_assembly(doc)
            local_replacement = self._ensure_local_replacement(doc, self.replacement_obj, assembly_obj)

            # Ersatzteil startet an der Position des Original-VORKOMMENS in DIESEM Dokument
            # (nicht zwingend self.original_obj - in einer anderen Datei kann das dieselbe
            # logische Baugruppe unter einer eigenen, lokalen Platzierung sein) -> bessere
            # Solver-Konvergenz.
            local_originals = {}
            for entry in doc_entries:
                local_orig = _entry_original_obj(entry)
                if local_orig is not None:
                    local_originals[local_orig.Name] = local_orig
            if local_originals:
                try:
                    local_replacement.Placement = next(iter(local_originals.values())).Placement
                except Exception:
                    pass

            # WICHTIG (2026-08-30, Nutzer-Report "Teil springt nicht zur Stange"): Bevor das
            # frisch erzeugte/platzierte Ersatzteil-Objekt einer Joint-Referenz (Reference1/2)
            # zugewiesen wird, MUSS es einmal neu berechnet werden. FreeCAD legt beim Zuweisen
            # einer Sub-Element-Referenz einen "Shadow"-Hash zur robusten Kanten-Wiedererkennung
            # an - wird der auf Basis eines noch nicht fertig berechneten Shapes erzeugt, zeigt er
            # spaeter auf die falsche Kante, obwohl die Nummer (z.B. "Edge34") gleich bleibt.
            # Bestaetigt per Live-Test: manuelles Neu-Anklicken derselben Kante NACH einem
            # Recompute hat das Problem behoben, ohne dass Kante oder Offset2 sich geaendert
            # haetten - die Ersatzteil-Seite (nicht die unveraenderte Original-Seite) war
            # betroffen.
            # WICHTIG (2026-08-30, Nutzer-Report "Stange hat sich gedreht, ohne dass ich
            # etwas berechnet habe"): doc.recompute() loest bei Assembly-Dokumenten IMMER
            # automatisch einen internen Solve aus (FreeCAD koppelt das fest, laesst sich
            # nicht abschalten) - schon das Entfernen des expliziten _solve_assembly_for()-
            # Aufrufs reicht also NICHT. Per git-Vergleich (vor/nach-Commit) belegt: Ondsels
            # automatische Redundant-Constraint-Aufloesung kann dabei den per GroundedJoint
            # fest geerdeten Teil selbst verschieben, obwohl der per Definition unbeweglich
            # sein soll. Deshalb: Placement aller geerdeten Teile VOR dem Recompute sichern
            # und danach explizit zurueckschreiben, falls der Solve sie trotzdem verschoben
            # hat.
            try:
                self._recompute_preserving_grounded(doc)
            except Exception:
                pass

            self._bring_doc_to_front(doc)

            applied_here = 0
            joint_names_here = []
            applied_originals = []  # NUR tatsaechlich ersetzte Original-Instanzen (fuer Ausblenden)
            for entry in doc_entries:
                # Fuer normale Referenzen (nicht GroundedJoint/RigidGroup) muss ueberhaupt erst
                # eine Zuordnung existieren - sonst gibt's nichts zu bestaetigen/anzuwenden.
                if entry["joint_side"] not in WHOLE_OBJECT_SIDES:
                    if mapping_by_key.get(_joint_key(entry)) is None:
                        continue

                # Pro Vorkommen einzeln nachfragen (Nutzerwunsch 2026-09-02), es sei denn
                # "Alle ersetzen" wurde schon fuer den Rest dieses Durchlaufs gewaehlt.
                if replace_all_remaining:
                    decision = "yes"
                else:
                    decision = self._confirm_replace_instance(entry)
                    if decision == "all":
                        replace_all_remaining = True
                        decision = "yes"

                if decision != "yes":
                    continue

                # GroundedJoint braucht keine manuelle Zuordnung (kein Face/Edge-Konzept -
                # ObjectToGround erdet immer das GANZE Objekt) - wird deshalb hier immer
                # automatisch auf das Ersatzteil umgehaengt, unabhaengig von den Nutzer-
                # Zuordnungen (2026-08-30, Nutzer-Report "GroundedJoint ist beim alten
                # Original geblieben").
                if entry["joint_side"] == GROUND_SIDE:
                    try:
                        entry["joint_obj"].ObjectToGround = local_replacement
                        rewired_joints += 1
                        applied_here += 1
                        joint_names_here.append(entry["joint_obj"].Name)
                        orig = _entry_original_obj(entry)
                        if orig is not None:
                            applied_originals.append(orig)
                    except Exception as e:
                        errors.append(
                            f"GroundedJoint '{entry['joint_obj'].Label}': ObjectToGround "
                            f"konnte nicht umgehängt werden ({str(e)})"
                        )
                    continue

                if entry["joint_side"] == RIGID_GROUP_SIDE:
                    # RigidGroupJoint.ObjectsToRigidGroup ist eine LISTE - das alte Original
                    # (entry["target_obj"]) muss darin durch das Ersatzteil ERSETZT werden,
                    # nicht die ganze Liste ueberschrieben werden (andere Mitglieder bleiben
                    # unveraendert). Analog zu GroundedJoint keine manuelle Zuordnung noetig.
                    try:
                        original_member = entry.get("target_obj")
                        members = list(entry["joint_obj"].ObjectsToRigidGroup or [])
                        members = [
                            local_replacement if m is original_member else m
                            for m in members
                        ]
                        entry["joint_obj"].ObjectsToRigidGroup = members
                        rewired_joints += 1
                        applied_here += 1
                        joint_names_here.append(entry["joint_obj"].Name)
                        if original_member is not None:
                            applied_originals.append(original_member)
                    except Exception as e:
                        errors.append(
                            f"RigidGroup '{entry['joint_obj'].Label}': Mitgliedschaft "
                            f"konnte nicht umgehängt werden ({str(e)})"
                        )
                    continue

                mapping = mapping_by_key.get(_joint_key(entry))
                if self._rewire_joint(
                    entry["joint_obj"], entry["joint_side"],
                    local_replacement, mapping["replacement_subelement"], errors
                ):
                    rewired_joints += 1
                    applied_here += 1
                    joint_names_here.append(entry["joint_obj"].Name)
                    orig = _entry_original_obj(entry)
                    if orig is not None:
                        applied_originals.append(orig)

            self._clear_highlight_selection()

            if applied_here == 0:
                continue

            doc_file_name = os.path.basename(doc.FileName) if doc.FileName else doc.Name
            touched_docs.append(f"{doc_file_name} [{', '.join(joint_names_here)}]")

            # NUR die tatsaechlich ersetzten Original-Instanzen ausblenden - uebersprungene
            # (per "Nein" abgelehnte) Instanzen bleiben unangetastet sichtbar.
            for local_orig in applied_originals:
                try:
                    vobj = getattr(local_orig, "ViewObject", None)
                    if vobj is not None:
                        vobj.Visibility = False
                except Exception:
                    pass

            try:
                self._recompute_preserving_grounded(doc)
            except Exception as e:
                errors.append(f"Neuberechnung von '{doc.Name}' fehlgeschlagen: {str(e)}")

            # Explizit nachfragen statt automatisch zu speichern (Nutzerwunsch 2026-09-02).
            self._confirm_save_doc(doc)

        App.Console.PrintMessage(
            f"FCProject PartExchange: {rewired_joints} Joint(s) in {len(touched_docs)} "
            f"Datei(en) erfolgreich umgehängt: {', '.join(touched_docs)}\n"
        )
        for err in errors:
            App.Console.PrintWarning(f"FCProject PartExchange: {err}\n")

        try:
            Gui.setActiveDocument(self.original_doc.Name)
        except Exception:
            pass
        self.close()

    @staticmethod
    def _solve_assembly_for(doc, errors, assembly_obj=None):
        """Löst den Assembly-Solver explizit für `doc` aus.

        `doc.recompute()` allein berechnet keine neuen Platzierungen anhand der
        Joints - das Lösen der Constraints übernimmt der Assembly-Solver, der
        über die Methode `solve()` auf dem Assembly::AssemblyObject angestoßen
        werden muss. Generalisiert (2026-08-30) von ursprünglich nur
        self.original_doc auf ein beliebiges `doc` - beim projektweiten
        Sammel-Anwenden wird das für JEDE betroffene Datei einzeln gebraucht.
        """
        if assembly_obj is None:
            assembly_obj = find_assembly(doc)
        if assembly_obj is None:
            errors.append(
                f"Keine Assembly in '{doc.Name}' gefunden - Position des Ersatzteils "
                "konnte nicht neu berechnet werden."
            )
            return

        if not hasattr(assembly_obj, 'solve'):
            errors.append(
                f"'{assembly_obj.Label}' bietet keine solve()-Methode in dieser FreeCAD-Version - "
                "Position des Ersatzteils muss ggf. manuell aktualisiert werden (z.B. über den "
                "Assembly-Workbench-Button 'Solve')."
            )
            return

        try:
            assembly_obj.solve()
            doc.recompute()
        except Exception as e:
            errors.append(f"Assembly-Solver in '{doc.Name}' konnte nicht ausgeführt werden: {str(e)}")

    @classmethod
    def _ensure_local_replacement(cls, doc, replacement, assembly=None):
        """Erzeugt IMMER einen eigenen, frischen App::Link auf das ECHTE Quellobjekt hinter
        `replacement` - auch wenn `replacement` schon im selben Dokument liegt. Ohne das gab die
        alte Kurzform (direkt das rohe Objekt zurückgeben, falls `replacement.Document is doc`)
        bei einem ZWEITEN Tausch mit demselben Ersatzteil-Kandidaten dieselbe physische
        Objekt-Referenz zurück wie beim ersten Tausch - der nachfolgende Placement-Zuweisung
        (siehe _on_apply()) verschob dann DASSELBE Objekt an die Position des zweiten Originals,
        wodurch der erste Tausch optisch verschwand (Nutzer-Report 2026-08-30: "erstes Teil ist
        nach dem zweiten Tausch weg").

        `replacement` wird dafuer per _resolve_display_obj() zuerst bis zum ECHTEN Quellobjekt
        aufgeloest, falls es selbst schon ein von uns erzeugter App::Link ist (z.B. weil der
        Nutzer im Ersatzteil-Dropdown versehentlich den `_Link` aus einem fruaeheren Tausch
        gewaehlt hat, der ja seitdem auch als gueltiger Kandidat auftaucht) - sonst waere ein
        Link-auf-Link entstanden ("..._Link_Link"), der beim Solve nicht sauber durchrechnet
        ("still touched after recompute", Nutzer-Report 2026-08-30).

        `doc.addObject()` haengt bei einem Namenskonflikt automatisch eine Zahl an (z.B.
        "..._Link001"), das war im urspruenglichen, bereits laenger bestehenden
        Cross-Dokument-Zweig unten schon immer der Fall - jetzt einheitlich fuer beide Faelle.
        Der Link wird in die Assembly eingehängt (nicht lose ans Dokument-Root)."""
        replacement = cls._resolve_display_obj(replacement)
        link = doc.addObject("App::Link", f"{replacement.Name}_Link")
        link.Label = replacement.Label
        link.LinkedObject = replacement
        # Markierung, damit dieser selbst erzeugte Link kuenftig NICHT mehr als Ersatzteil-
        # Kandidat im Dropdown auftaucht (siehe is_valid_exchange_candidate() in
        # PartExchangeAnalyzer.py) - verhindert die Verwechslungsgefahr direkt an der Quelle,
        # statt sich nur auf die _resolve_display_obj()-Aufloesung oben zu verlassen.
        link.addProperty(
            "App::PropertyBool", "FCProjectExchangeLink", "FCProject",
            "Markiert diesen App::Link als von FCProject_PartExchange erzeugtes Ersatzteil-Link"
        )
        link.FCProjectExchangeLink = True
        if assembly is not None and hasattr(assembly, 'addObject'):
            try:
                assembly.addObject(link)
            except Exception as e:
                App.Console.PrintWarning(
                    f"FCProject PartExchange: Ersatzteil konnte nicht in Assembly eingehängt werden: {e}\n"
                )
        return link

    @staticmethod
    def _recompute_preserving_grounded(doc):
        """doc.recompute(), aber mit Schutz fuer per GroundedJoint fest geerdete Teile.

        WICHTIG (2026-08-30, Nutzer-Report "Stange hat sich nach dem Ersetzen gedreht, ohne
        dass ich etwas berechnet habe"): doc.recompute() loest bei Assembly-Dokumenten IMMER
        automatisch einen internen Solve aus (FreeCAD koppelt das fest, laesst sich nicht per
        Parameter abschalten). Per git-Vergleich (vor/nach-Commit derselben Aktion) belegt:
        Ondsels automatische Redundant-Constraint-Aufloesung kann dabei den per GroundedJoint
        fest geerdeten Teil selbst verschieben, obwohl der per Definition unbeweglich sein
        soll - ein Solver-Verhalten, kein Referenz-/Offset-Fehler unsererseits. Deshalb wird
        das Placement aller geerdeten Teile vor dem Recompute gesichert und danach explizit
        zurueckgeschrieben, falls der Solve sie trotzdem verschoben hat.
        """
        grounded_before = {}
        for obj in doc.Objects:
            target = getattr(obj, "ObjectToGround", None)
            if target is not None:
                try:
                    grounded_before[target.Name] = App.Placement(target.Placement)
                except Exception:
                    pass

        doc.recompute()

        for name, placement in grounded_before.items():
            target = doc.getObject(name)
            if target is None:
                continue
            try:
                if not target.Placement.isSame(placement):
                    target.Placement = placement
            except Exception:
                pass

    # Eigenschaften, die FreeCAD beim Setzen einer neuen Reference1/Reference2 auf einem
    # BESTEHENDEN Joint-Objekt als Nebeneffekt automatisch neu berechnet/zuruecksetzt (aus
    # Assembly/JointObject.py: Offset1/Offset2 = eingefrorene Connector-Transformation,
    # Distance/Distance2/Angle = Joint-Wert je nach Typ, LengthMin/Max/AngleMin/Max +
    # zugehoerige Enable-Flags = Verfahr-/Winkelgrenzen). Werden hier VOR dem Referenz-Wechsel
    # gesichert und danach wiederhergestellt (siehe _rewire_joint()-Docstring).
    _PRESERVED_JOINT_PROPS = [
        "Offset1", "Offset2", "Angle", "Distance", "Distance2",
        "LengthMin", "LengthMax", "AngleMin", "AngleMax",
        "EnableLengthMin", "EnableLengthMax", "EnableAngleMin", "EnableAngleMax",
    ]

    @staticmethod
    def _rewire_joint(joint, side, replacement_obj, replacement_sub, errors):
        # WICHTIG (2026-08-30, Nutzer-Report "Teile haben Position verloren"/Solver divergiert
        # massiv nach dem Umhaengen, spaeter auch "Maximale Laenge steht jetzt auf 0"):
        # Nutzer-Entscheidung "alles soll unangetastet bleiben beim Teiletausch" - FreeCAD
        # berechnet aber beim Setzen einer neuen Reference1/Reference2 auf einem BESTEHENDEN
        # Joint-Objekt mehrere abgeleitete Eigenschaften automatisch neu (nicht nur Offset2,
        # sondern z.B. auch LengthMax bei Gleitverbindungen - bestaetigt per Nutzer-Test: nach
        # dem Umhaengen stand LengthMax auf 0, obwohl unser Code diese Eigenschaft nirgends
        # anfasst). Deshalb werden jetzt ALLE bekannten "eingefrorenen" Joint-Eigenschaften vor
        # dem Referenz-Wechsel gesichert und danach explizit wiederhergestellt, statt nur
        # Offset2 unangetastet zu lassen.
        saved = {}
        for prop in PartExchangeWindow._PRESERVED_JOINT_PROPS:
            if hasattr(joint, prop):
                try:
                    saved[prop] = getattr(joint, prop)
                except Exception:
                    pass

        # Reference1/2 tragen den Sub-Namen ZWEIMAL (Element + "Vertex-Hint" fuer die
        # Platzierung, siehe UtilsAssembly.findPlacement()/JointObject.handleInitialSelection()
        # - "We add sub_name twice ... both are the same"). Ein leerer zweiter Eintrag laesst
        # findPlacement() in den "ganzes Teil ohne Sub-Element"-Fallback laufen und still eine
        # Identitaets-Placement statt der echten Flaechen-/Kanten-Position liefern - siehe
        # patches/bugreport-fixed-joint-no-coincidence/Questions.md auf solver-root-cause-fix.
        sub = replacement_sub or ""
        new_ref = [replacement_obj, [sub, sub]]
        try:
            if side == 1:
                joint.Reference1 = new_ref
            else:
                joint.Reference2 = new_ref
        except Exception as e:
            errors.append(f"Joint '{joint.Label}': Referenz konnte nicht gesetzt werden ({str(e)})")
            return False

        for prop, value in saved.items():
            try:
                setattr(joint, prop, value)
            except Exception as e:
                errors.append(
                    f"Joint '{joint.Label}': '{prop}' konnte nicht wiederhergestellt werden ({str(e)})"
                )
        return True
