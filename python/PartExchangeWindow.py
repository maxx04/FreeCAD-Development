# FCProject: PartExchangeWindow - Joint-Referenzen von Original auf Ersatzteil ummappen
#
# Umfang bewusst auf zwei Punkte begrenzt:
#   1. Joints bleiben intakt (Reference1/Reference2 + Offset2 werden korrekt neu gesetzt)
#   2. die darin benutzten Referenzen werden korrekt auf das Ersatzteil umgehängt
# Auswirkungen auf andere Abhängigkeiten (Gruppenmitgliedschaft, generische
# Links, Ausblenden/Umbenennen des Originals) sind explizit ein späterer Schritt.

import re

import FreeCAD as App
import FreeCADGui as Gui
from PySide6 import QtWidgets, QtCore

from PartExchangeAnalyzer import (
    find_joints_referencing, compute_rewired_offset, subpath_for_descendant, full_reference_path, find_assembly
)

ENTRY_ROLE = QtCore.Qt.UserRole

# Subname-Endung (z.B. "Face14") -> ViewProvider-Property mit einer Farbe pro Element.
# Teil von ViewProviderPartExt (Mod/Part/Gui/ViewProviderExt.h) - unabhängig von
# eigenen getDisplayModes()-Overrides (z.B. SheetMetal "BaseShape": liefert []) und
# unabhängig vom Selection-System.
_ELEMENT_COLOR_PROP = {"Face": "DiffuseColor", "Edge": "LineColorArray", "Vertex": "PointColorArray"}
_ELEMENT_COUNT_ATTR = {"Face": "Faces", "Edge": "Edges", "Vertex": "Vertexes"}


def _joint_key(entry):
    return (entry["joint_obj"].Document.Name, entry["joint_obj"].Name, entry["joint_side"])


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

        self._original_joints = find_joints_referencing(original_obj)
        self._mappings = []  # [{"original": entry, "replacement_subelement": str}]
        self._pending_original = None
        self._forced_visible = []  # ViewObjects, die für die Hervorhebung sichtbar gemacht wurden
        self._color_overrides = {}  # (doc.Name, obj.Name, prop) -> (ViewObject, prop, Original-Farbliste)
        self._embedded_views = []  # [(widget, doc)] - aus dem Haupt-MDI-Bereich ausgeliehene 3D-Ansichten
        self._highlighted_docs = set()  # doc.Name - für Datum-Hervorhebung (Gui.Selection) benutzte Dokumente

        self.setWindowTitle("FCProject: Part/Assembly ersetzen – Joint-Zuordnung")
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
        left_layout.addWidget(QtWidgets.QLabel("Joints, die dieses Teil referenzieren:"), stretch=0)
        self.joint_list = QtWidgets.QListWidget()
        self.joint_list.setMaximumHeight(110)
        self.joint_list.itemClicked.connect(self._on_joint_clicked)
        left_layout.addWidget(self.joint_list, stretch=0)
        self.original_view_container = QtWidgets.QVBoxLayout()
        left_layout.addLayout(self.original_view_container, stretch=1)
        columns.addWidget(left_box)

        right_box = QtWidgets.QGroupBox(f"Ersatzteil: {self.replacement_obj.Label}")
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

        mapping_box = QtWidgets.QGroupBox("Zuordnungen (Joint → Ersatzteil-Referenz)")
        mapping_layout = QtWidgets.QVBoxLayout(mapping_box)
        self.mapping_table = QtWidgets.QTableWidget(0, 3)
        self.mapping_table.setHorizontalHeaderLabels(["Joint (Original)", "Ersatzteil-Referenz", ""])
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
        self.joint_list.clear()
        for entry in self._original_joints:
            item = QtWidgets.QListWidgetItem(entry["label"])
            item.setData(ENTRY_ROLE, entry)
            self.joint_list.addItem(item)
        if not self._original_joints:
            self.joint_list.addItem("(keine Joints gefunden)")
            self.joint_list.setEnabled(False)

    # ------------------------------------------------------------- Klicks

    def _on_joint_clicked(self, item):
        entry = item.data(ENTRY_ROLE)
        if entry is None:
            return
        self._pending_original = entry
        sub = entry.get("subelement") or ""
        self._clear_highlight_selection()
        self._highlight_reference(self.original_obj, sub, (1.0, 0.0, 1.0))
        self._update_pending_label()

    def _on_use_selection_clicked(self):
        selection = Gui.Selection.getSelectionEx(self.replacement_doc.Name)
        if not selection:
            QtWidgets.QMessageBox.warning(
                self, "FCProject",
                f"Bitte zuerst im 3D-Fenster oder im Baum eine Referenz von "
                f"'{self.replacement_obj.Label}' wählen (z.B. Fläche, Kante, LCS oder Origin-Achse)."
            )
            return

        sel_obj = selection[0]
        if sel_obj.Object is self.replacement_obj:
            # Direkter Treffer (typischerweise 3D-Klick auf Fläche/Kante).
            subelement = sel_obj.SubElementNames[0] if sel_obj.SubElementNames else ""
        else:
            # Baum-Auswahl eines Kind-Elements (z.B. Origin-Achse/-Ebene, LCS),
            # das in der 3D-Ansicht kaum treffsicher anklickbar ist.
            subelement = subpath_for_descendant(self.replacement_obj, sel_obj.Object)
            if subelement is None:
                QtWidgets.QMessageBox.warning(
                    self, "FCProject",
                    f"'{sel_obj.Object.Label}' gehört nicht zu '{self.replacement_obj.Label}'.\n"
                    "Bitte eine Fläche/Kante im 3D-Fenster oder ein Element davon im Baum wählen "
                    "(z.B. eine Origin-Achse/-Ebene oder ein LCS)."
                )
                return

        if self._pending_original is None:
            QtWidgets.QMessageBox.warning(
                self, "FCProject", "Bitte zuerst links einen Joint-Eintrag des Originals auswählen."
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
            self._highlight_via_selection(display_obj)
        self._ensure_view(display_obj.Document)
        try:
            Gui.setActiveDocument(display_obj.Document.Name)
        except Exception:
            pass

    def _highlight_via_selection(self, display_obj):
        """Gui.Selection-Auswahl für Datum-Elemente (Origin-Achse/-Ebene, LCS) - diese
        haben keine Face/Edge/Vertex-Topologie zum Einfärben, sind aber Standard-
        FreeCAD-Kernobjekte mit normal funktionierender Selektions-Hervorhebung."""
        doc = display_obj.Document
        try:
            Gui.Selection.removeSelectionGate(doc.Name)
        except Exception:
            pass
        try:
            Gui.Selection.addSelection(doc.Name, display_obj.Name)
            self._highlighted_docs.add(doc.Name)
        except Exception as e:
            App.Console.PrintWarning(
                f"FCProject PartExchange: '{display_obj.Label}' konnte nicht selektiert werden: {str(e)}\n"
            )

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
        if vobj is None or not hasattr(display_obj, "Shape"):
            return None, False

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
        self.pending_label.setText(f"Ausgewählter Original-Joint: <b>{text}</b>")

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
        required_keys = {_joint_key(entry) for entry in self._original_joints}
        mapped_keys = {_joint_key(m["original"]) for m in self._mappings}
        self.apply_btn.setEnabled(len(required_keys) > 0 and required_keys.issubset(mapped_keys))

    # ------------------------------------------------------- Fenster-Layout

    @staticmethod
    def _resolve_display_doc(obj):
        """Das Dokument, in dem `obj` tatsächlich seine Geometrie zeigt.

        Für App::Link-Ketten (z.B. Pattern-Kopie → Assembly-Link → Teil-Dokument)
        wird die gesamte LinkedObject-Kette durchlaufen, bis kein weiterer Link
        mehr folgt. Das stellt sicher, dass auch Pattern-Kopien das eigentliche
        Teil-Dokument statt der Assembly liefern.
        """
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
        return current.Document

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
        self._embed_one(mdi_area, self.original_display_doc, self.original_view_container)
        if self.replacement_doc is not self.original_display_doc:
            self._embed_one(mdi_area, self.replacement_doc, self.replacement_view_container)

    def _embed_one(self, mdi_area, doc, container_layout):
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
                Gui.SendMsgToActiveView("ViewFit")
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

    def _on_apply(self):
        errors = []
        rewired_joints = 0

        assembly_obj = find_assembly(self.original_doc)
        local_replacement = self._ensure_local_replacement(
            self.original_doc, self.replacement_obj, assembly_obj
        )

        # Ersatzteil startet an der Position des alten Teils → bessere Solver-Konvergenz
        try:
            local_replacement.Placement = self.original_obj.Placement
        except Exception:
            pass

        mapping_by_key = {_joint_key(m["original"]): m for m in self._mappings}

        for entry in self._original_joints:
            mapping = mapping_by_key.get(_joint_key(entry))
            if mapping is None:
                continue
            if self._rewire_joint(
                entry["joint_obj"], entry["joint_side"],
                local_replacement, mapping["replacement_subelement"], errors
            ):
                rewired_joints += 1

        # Ersetztes Teil ausblenden
        try:
            orig_vobj = getattr(self.original_obj, "ViewObject", None)
            if orig_vobj is not None:
                orig_vobj.Visibility = False
        except Exception:
            pass

        try:
            self.original_doc.recompute()
        except Exception as e:
            errors.append(f"Neuberechnung des Original-Dokuments fehlgeschlagen: {str(e)}")

        self._solve_assembly(errors, assembly_obj)

        App.Console.PrintMessage(
            f"FCProject PartExchange: {rewired_joints} Joint(s) erfolgreich umgehängt.\n"
        )
        for err in errors:
            App.Console.PrintWarning(f"FCProject PartExchange: {err}\n")

        try:
            Gui.setActiveDocument(self.original_doc.Name)
        except Exception:
            pass
        self.close()

    def _solve_assembly(self, errors, assembly_obj=None):
        """Löst den Assembly-Solver explizit aus.

        `doc.recompute()` allein berechnet keine neuen Platzierungen anhand der
        Joints - das Lösen der Constraints übernimmt der Assembly-Solver, der
        über die Methode `solve()` auf dem Assembly::AssemblyObject angestoßen
        werden muss.
        """
        if assembly_obj is None:
            assembly_obj = find_assembly(self.original_doc)
        if assembly_obj is None:
            errors.append(
                "Keine Assembly im Original-Dokument gefunden - Position des Ersatzteils "
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
            self.original_doc.recompute()
        except Exception as e:
            errors.append(f"Assembly-Solver konnte nicht ausgeführt werden: {str(e)}")

    @staticmethod
    def _ensure_local_replacement(doc, replacement, assembly=None):
        """Hängt ein Ersatzteil aus einem fremden Dokument als App::Link in `doc` ein,
        damit die Joint-Referenz innerhalb desselben Dokuments bleibt.
        Der Link wird in die Assembly eingehängt (nicht lose ans Dokument-Root)."""
        if replacement.Document is doc:
            return replacement
        link = doc.addObject("App::Link", f"{replacement.Name}_Link")
        link.Label = replacement.Label
        link.LinkedObject = replacement
        if assembly is not None and hasattr(assembly, 'addObject'):
            try:
                assembly.addObject(link)
            except Exception as e:
                App.Console.PrintWarning(
                    f"FCProject PartExchange: Ersatzteil konnte nicht in Assembly eingehängt werden: {e}\n"
                )
        return link

    @staticmethod
    def _rewire_joint(joint, side, replacement_obj, replacement_sub, errors):
        new_ref = [replacement_obj, [replacement_sub or "", ""]]
        try:
            if side == 1:
                joint.Reference1 = new_ref
            else:
                joint.Reference2 = new_ref
        except Exception as e:
            errors.append(f"Joint '{joint.Label}': Referenz konnte nicht gesetzt werden ({str(e)})")
            return False

        offset = compute_rewired_offset(joint.Reference1, joint.Reference2)
        if offset is not None:
            try:
                joint.Offset2 = offset
            except Exception as e:
                errors.append(f"Joint '{joint.Label}': Offset2 konnte nicht aktualisiert werden ({str(e)})")
        return True
