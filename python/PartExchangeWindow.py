# FCProject: PartExchangeWindow - Joint-Referenzen von Original auf Ersatzteil ummappen
#
# Umfang bewusst auf zwei Punkte begrenzt:
#   1. Joints bleiben intakt (Reference1/Reference2 + Offset2 werden korrekt neu gesetzt)
#   2. die darin benutzten Referenzen werden korrekt auf das Ersatzteil umgehängt
# Auswirkungen auf andere Abhängigkeiten (Gruppenmitgliedschaft, generische
# Links, Ausblenden/Umbenennen des Originals) sind explizit ein späterer Schritt.

import FreeCAD as App
import FreeCADGui as Gui
from PySide6 import QtWidgets, QtCore

from PartExchangeAnalyzer import (
    find_joints_referencing, compute_rewired_offset, subpath_for_descendant, full_reference_path, find_assembly
)

ENTRY_ROLE = QtCore.Qt.UserRole


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

        self._original_joints = find_joints_referencing(original_obj)
        self._mappings = []  # [{"original": entry, "replacement_subelement": str}]
        self._pending_original = None

        self.setWindowTitle("FCProject: Part/Assembly ersetzen – Joint-Zuordnung")
        self.setModal(False)

        self._build_ui()
        self._populate_joint_list()
        self._update_pending_label()
        self._update_apply_button_state()

        self._arrange_3d_views()
        self._position_below_main_window()

    # ------------------------------------------------------------------ UI

    def _build_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)

        columns = QtWidgets.QHBoxLayout()

        left_box = QtWidgets.QGroupBox(f"Original: {self.original_obj.Label}")
        left_layout = QtWidgets.QVBoxLayout(left_box)
        left_layout.addWidget(QtWidgets.QLabel("Joints, die dieses Teil referenzieren:"))
        self.joint_list = QtWidgets.QListWidget()
        self.joint_list.itemClicked.connect(self._on_joint_clicked)
        left_layout.addWidget(self.joint_list)
        columns.addWidget(left_box)

        right_box = QtWidgets.QGroupBox(f"Ersatzteil: {self.replacement_obj.Label}")
        right_layout = QtWidgets.QVBoxLayout(right_box)
        right_layout.addWidget(QtWidgets.QLabel(
            "Fläche/Kante/LCS am Ersatzteil im 3D-Fenster ODER im Baum anklicken "
            "(z.B. Origin-Achse/-Ebene), dann übernehmen:"
        ))
        self.selection_label = QtWidgets.QLabel("Aktuelle 3D-Auswahl: –")
        self.selection_label.setWordWrap(True)
        right_layout.addWidget(self.selection_label)
        self.use_selection_btn = QtWidgets.QPushButton("Als Referenz übernehmen")
        self.use_selection_btn.clicked.connect(self._on_use_selection_clicked)
        right_layout.addWidget(self.use_selection_btn)
        right_layout.addStretch()
        columns.addWidget(right_box)

        main_layout.addLayout(columns, stretch=2)

        self.pending_label = QtWidgets.QLabel()
        main_layout.addWidget(self.pending_label)

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
        self._select(self.original_doc, self.original_obj, entry.get("subelement") or "")
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

    def _select(self, doc, obj, sub):
        try:
            if Gui.ActiveDocument is None or Gui.ActiveDocument.Document is not doc:
                Gui.setActiveDocument(doc.Name)
        except Exception as e:
            App.Console.PrintWarning(
                f"FCProject PartExchange: Dokument '{doc.Name}' konnte nicht aktiviert werden: {str(e)}\n"
            )
        try:
            Gui.Selection.clearSelection(doc.Name)
        except Exception as e:
            App.Console.PrintWarning(f"FCProject PartExchange: Auswahl konnte nicht geleert werden: {str(e)}\n")
        try:
            Gui.Selection.addSelection(doc.Name, obj.Name, sub)
        except Exception as e:
            App.Console.PrintWarning(
                f"FCProject PartExchange: '{obj.Label}' konnte nicht selektiert werden: {str(e)}\n"
            )

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

    def _update_apply_button_state(self):
        required_keys = {_joint_key(entry) for entry in self._original_joints}
        mapped_keys = {_joint_key(m["original"]) for m in self._mappings}
        self.apply_btn.setEnabled(len(required_keys) > 0 and required_keys.issubset(mapped_keys))

    # ------------------------------------------------------- Fenster-Layout

    def _arrange_3d_views(self):
        if self.original_doc is self.replacement_doc:
            return
        try:
            main_win = Gui.getMainWindow()
            mdi_area = main_win.findChild(QtWidgets.QMdiArea)
            if mdi_area is None:
                return

            Gui.setActiveDocument(self.original_doc.Name)
            QtWidgets.QApplication.processEvents()
            Gui.setActiveDocument(self.replacement_doc.Name)
            QtWidgets.QApplication.processEvents()

            original_sub = self._find_subwindow(mdi_area, self.original_doc)
            replacement_sub = self._find_subwindow(mdi_area, self.replacement_doc)
            if original_sub is None or replacement_sub is None:
                return

            area_rect = mdi_area.rect()
            half_w = area_rect.width() // 2
            original_sub.showNormal()
            replacement_sub.showNormal()
            original_sub.setGeometry(0, 0, half_w, area_rect.height())
            replacement_sub.setGeometry(half_w, 0, area_rect.width() - half_w, area_rect.height())
        except Exception as e:
            App.Console.PrintWarning(f"FCProject PartExchange: Fenster konnten nicht angeordnet werden: {str(e)}\n")

    @staticmethod
    def _find_subwindow(mdi_area, doc):
        label = doc.Label or doc.Name
        for sub in mdi_area.subWindowList():
            title = sub.windowTitle() or ""
            if title.startswith(label) or title.startswith(doc.Name):
                return sub
        return None

    def _position_below_main_window(self):
        try:
            main_win = Gui.getMainWindow()
            geo = main_win.geometry()
            width = int(geo.width() * 0.8)
            self.resize(width, 420)
            self.move(geo.x() + (geo.width() - width) // 2, geo.y() + geo.height())
        except Exception:
            pass

    # ------------------------------------------------------------- Apply

    def _on_apply(self):
        errors = []
        rewired_joints = 0

        local_replacement = self._ensure_local_replacement(self.original_doc, self.replacement_obj)
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

        try:
            self.original_doc.recompute()
        except Exception as e:
            errors.append(f"Neuberechnung des Original-Dokuments fehlgeschlagen: {str(e)}")

        self._solve_assembly(errors)

        summary = f"Joints umgehängt: {rewired_joints}"
        if errors:
            summary += "\n\nWarnungen:\n" + "\n".join(errors)

        QtWidgets.QMessageBox.information(self, "FCProject: Part/Assembly ersetzen", summary)

    def _solve_assembly(self, errors):
        """Löst den Assembly-Solver explizit aus.

        `doc.recompute()` allein berechnet keine neuen Platzierungen anhand der
        Joints - das Lösen der Constraints übernimmt der Assembly-Solver, der
        über die Methode `solve()` auf dem Assembly::AssemblyObject angestoßen
        werden muss.
        """
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
    def _ensure_local_replacement(doc, replacement):
        """Hängt ein Ersatzteil aus einem fremden Dokument als App::Link in `doc` ein,
        damit die Joint-Referenz innerhalb desselben Dokuments bleibt."""
        if replacement.Document is doc:
            return replacement
        link = doc.addObject("App::Link", f"{replacement.Name}_Link")
        link.Label = replacement.Label
        link.LinkedObject = replacement
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
