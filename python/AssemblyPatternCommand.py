import FreeCAD as App
import FreeCADGui as Gui
from PySide6 import QtWidgets
from PySide6.QtCore import Qt
try:
    from .version import __version__
except ImportError:
    from version import __version__

from FCProjectCore import AssemblyPatternCreator

class AssemblyPatternCommand:
    """Command zum Erstellen eines Pattern (Array) von Elementen über Joints in einer Assembly."""
    
    def GetResources(self):
        import os
        icon_path = os.path.join(os.path.dirname(__file__), 'resources', 'icons', 'assembly_pattern.svg')
        return {
            'Pixmap': icon_path,
            'MenuText': f'FCProject: Assembly Pattern (LCS active) via Joints ',
            'ToolTip': f'Erstellt ein Array-Pattern mit richtungsabhängiger LCS-Referenz'
        }

    def Activated(self):
        active_doc = App.ActiveDocument
        main_win = Gui.getMainWindow()

        if not active_doc:
            QtWidgets.QMessageBox.warning(
                main_win, 
                "FCProject Assembly Pattern", 
                "Bitte öffne zuerst ein Dokument mit einer Assembly!"
            )
            return

        # Prüfe ob Assembly existiert
        assembly = None
        for obj in active_doc.Objects:
            if obj.TypeId == "Assembly::AssemblyObject":
                assembly = obj
                break

        if not assembly:
            QtWidgets.QMessageBox.warning(
                main_win,
                "FCProject Assembly Pattern",
                "Keine Assembly im Dokument gefunden!"
            )
            return

        App.Console.PrintMessage("FCProject Assembly Pattern 1.1 aktiv\n")
        try:
            # Starte den Pattern Creator mit einem Dialog
            dialog = AssemblyPatternDialog(active_doc, assembly, main_win)
            dialog.exec()
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                main_win,
                "FCProject Assembly Pattern",
                f"Fehler beim Pattern-Erstellen: {str(e)}"
            )
            App.Console.PrintError(f"AssemblyPatternCommand Error: {str(e)}\n")
            import traceback
            App.Console.PrintError(f"Traceback: {traceback.format_exc()}\n")

    def IsActive(self):
        if not App.ActiveDocument:
            return False
        # Prüfe ob Assembly existiert
        for obj in App.ActiveDocument.Objects:
            if obj.TypeId == "Assembly::AssemblyObject":
                return True
        return False


class AssemblyPatternDialog(QtWidgets.QDialog):
    """Dialog zur Konfiguration des Assembly Patterns."""
    
    def __init__(self, doc, assembly, parent=None):
        super().__init__(parent)
        self.doc = doc
        self.assembly = assembly
        try:
            self.creator = AssemblyPatternCreator(assembly.Name)
            self.init_ui()
        except Exception as e:
            App.Console.PrintError(f"FCProject Dialog Init Error: {str(e)}\n")
            import traceback
            App.Console.PrintError(f"Traceback: {traceback.format_exc()}\n")
            raise

    def init_ui(self):
        self.setWindowTitle(f"FCProject: Assembly Pattern V{__version__} erstellen")
        self.setGeometry(100, 100, 500, 420)

        layout = QtWidgets.QVBoxLayout()

        # Quell-Element auswählen
        layout.addWidget(QtWidgets.QLabel("Quell-Element: Bitte wähle im Dokument genau ein Objekt aus."))
        self.selected_label = QtWidgets.QLabel(self._get_selected_label_text())
        layout.addWidget(self.selected_label)

        # Anzahl der Kopien
        layout.addWidget(QtWidgets.QLabel("Anzahl Kopien:"))
        self.count_spinbox = QtWidgets.QSpinBox()
        self.count_spinbox.setMinimum(1)
        self.count_spinbox.setMaximum(100)
        self.count_spinbox.setValue(3)
        layout.addWidget(self.count_spinbox)

        # Joint-Abstand
        layout.addWidget(QtWidgets.QLabel("Abstand zwischen Elementen (mm):"))
        self.distance_spinbox = QtWidgets.QDoubleSpinBox()
        self.distance_spinbox.setMinimum(0.001)
        self.distance_spinbox.setMaximum(10000.0)
        # Erlaube mehr Nachkommastellen/Größeren Werte
        try:
            self.distance_spinbox.setDecimals(3)
        except Exception:
            pass
        self.distance_spinbox.setValue(600.0)
        self.distance_spinbox.setSingleStep(1.0)
        layout.addWidget(self.distance_spinbox)

        # Pattern-Richtung
        layout.addWidget(QtWidgets.QLabel("Pattern-Richtung:"))
        self.direction_combo = QtWidgets.QComboBox()
        self.direction_combo.addItems(["X-Achse", "Y-Achse", "Z-Achse"])
        layout.addWidget(self.direction_combo)

        version_label = QtWidgets.QLabel(f"<b>FCProject Assembly Pattern V{__version__} aktiv (LCS direction mode)</b>")
        version_label.setStyleSheet("color: #555555; font-size: 12px;")
        version_label.setTextFormat(Qt.RichText)
        layout.addWidget(version_label)

        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        create_btn = QtWidgets.QPushButton("Pattern erstellen")
        cancel_btn = QtWidgets.QPushButton("Abbrechen")
        
        create_btn.clicked.connect(self.create_pattern)
        cancel_btn.clicked.connect(self.reject)
        
        button_layout.addWidget(create_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        self.setLayout(layout)

    def _get_selected_label_text(self):
        selection = Gui.Selection.getSelection()
        if not selection:
            return "(Kein Objekt ausgewählt)"
        if len(selection) > 1:
            return "Mehrere Objekte ausgewählt – bitte genau ein Objekt wählen."

        source_element = selection[0]
        if not self._is_valid_source_element(source_element):
            return f"Ausgewähltes Objekt '{source_element.Label}' ist nicht gültig.\n\
            Unterstützt: Part, Body, Assembly, Link, oder Elemente mit Shape."
        return f"Ausgewählt: {source_element.Label} ({source_element.Name})"

    def _is_valid_source_element(self, element):
        if element is None:
            return False
        
        # Prüfe, ob das Element gültig ist (Part, Body, Assembly, Link, oder mit Shape)
        is_valid = False
        if hasattr(element, 'Shape') and element.Shape is not None:
            is_valid = True  # Hat Shape
        elif element.isDerivedFrom('Assembly::AssemblyObject'):
            is_valid = True  # Assembly
        elif element.isDerivedFrom('App::Part'):
            is_valid = True  # Part
        elif element.isDerivedFrom('PartDesign::Body'):
            is_valid = True  # Body
        elif element.isDerivedFrom('App::Link'):
            is_valid = True  # Link
        
        if not is_valid:
            return False
        
        # Lehne Gruppen und spezielle Objekte ab
        if element.TypeId == 'App::DocumentObjectGroup':
            return False
        
        name_lower = element.Name.lower() if hasattr(element, 'Name') else ''
        label_lower = element.Label.lower() if hasattr(element, 'Label') else ''
        
        # Lehne Joint und BOM Objekte ab
        #TODO Nicht nach Label, sondern nach Typ filtern
        if 'joint' in name_lower or 'joint' in label_lower:
            return False
        if 'bom' in name_lower or 'bom' in label_lower:
            return False
        return True

    def _get_selected_source_element(self):
        selection = Gui.Selection.getSelection()
        if len(selection) != 1:
            return None
        source_element = selection[0]
        return source_element if self._is_valid_source_element(source_element) else None

    def create_pattern(self):
        """Erstellt das Pattern mit den Dialog-Einstellungen."""
        source_element = self._get_selected_source_element()
        count = self.count_spinbox.value()
        distance = self.distance_spinbox.value()
        direction = self.direction_combo.currentText()

        if not source_element:
            QtWidgets.QMessageBox.warning(
                self,
                "Fehler",
                "Bitte wähle ein gültiges Quell-Element im Dokument genau einmal aus."
            )
            self.selected_label.setText(self._get_selected_label_text())
            return

        try:
            self.creator.create_pattern(
                source_element_name=source_element.Name,
                count=count,
                distance=distance,
                direction=direction
            )
            
            QtWidgets.QMessageBox.information(
                self,
                "Erfolg",
                f"FCProject Assembly Pattern v1.1: Pattern mit {count} Kopien erfolgreich erstellt!"
            )
            self.accept()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Fehler", f"Pattern-Erstellung fehlgeschlagen: {str(e)}")


class CircularPatternCommand:
    """Command zum Erstellen eines zirkularen Patterns von Elementen in einer Assembly."""

    def GetResources(self):
        import os
        icon_path = os.path.join(os.path.dirname(__file__), 'resources', 'icons', 'circular_pattern.svg')
        return {
            'Pixmap': icon_path,
            'MenuText': 'FCProject: Zirkulares Assembly Pattern',
            'ToolTip': 'Erstellt ein kreisförmiges Array-Pattern von Elementen in einer Assembly'
        }

    def Activated(self):
        active_doc = App.ActiveDocument
        main_win = Gui.getMainWindow()

        if not active_doc:
            QtWidgets.QMessageBox.warning(
                main_win,
                "FCProject Circular Pattern",
                "Bitte öffne zuerst ein Dokument mit einer Assembly!"
            )
            return

        assembly = None
        for obj in active_doc.Objects:
            if obj.TypeId == "Assembly::AssemblyObject":
                assembly = obj
                break

        if not assembly:
            QtWidgets.QMessageBox.warning(
                main_win,
                "FCProject Circular Pattern",
                "Keine Assembly im Dokument gefunden!"
            )
            return

        App.Console.PrintMessage("FCProject Circular Pattern aktiv\n")
        try:
            dialog = CircularPatternDialog(active_doc, assembly, main_win)
            dialog.exec()
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                main_win,
                "FCProject Circular Pattern",
                f"Fehler beim Pattern-Erstellen: {str(e)}"
            )
            App.Console.PrintError(f"CircularPatternCommand Error: {str(e)}\n")
            import traceback
            App.Console.PrintError(f"Traceback: {traceback.format_exc()}\n")

    def IsActive(self):
        if not App.ActiveDocument:
            return False
        for obj in App.ActiveDocument.Objects:
            if obj.TypeId == "Assembly::AssemblyObject":
                return True
        return False


class CircularPatternDialog(QtWidgets.QDialog):
    """Dialog zur Konfiguration des zirkularen Assembly Patterns."""

    def __init__(self, doc, assembly, parent=None):
        super().__init__(parent)
        self.doc = doc
        self.assembly = assembly
        try:
            self.creator = AssemblyPatternCreator(assembly.Name)
            self.init_ui()
        except Exception as e:
            App.Console.PrintError(f"FCProject Circular Dialog Init Error: {str(e)}\n")
            import traceback
            App.Console.PrintError(f"Traceback: {traceback.format_exc()}\n")
            raise

    def init_ui(self):
        self.setWindowTitle(f"FCProject: Zirkulares Pattern V{__version__} erstellen")
        self.setGeometry(100, 100, 500, 380)

        layout = QtWidgets.QVBoxLayout()

        layout.addWidget(QtWidgets.QLabel("Quell-Element: Bitte wähle im Dokument genau ein Objekt aus."))
        self.selected_label = QtWidgets.QLabel(self._get_selected_label_text())
        layout.addWidget(self.selected_label)

        layout.addWidget(QtWidgets.QLabel("Anzahl Elemente im Kreis:"))
        self.count_spinbox = QtWidgets.QSpinBox()
        self.count_spinbox.setMinimum(2)
        self.count_spinbox.setMaximum(100)
        self.count_spinbox.setValue(6)
        layout.addWidget(self.count_spinbox)

        layout.addWidget(QtWidgets.QLabel("Radius (mm):"))
        self.radius_spinbox = QtWidgets.QDoubleSpinBox()
        self.radius_spinbox.setMinimum(1.0)
        self.radius_spinbox.setMaximum(100000.0)
        self.radius_spinbox.setDecimals(3)
        self.radius_spinbox.setValue(200.0)
        self.radius_spinbox.setSingleStep(10.0)
        layout.addWidget(self.radius_spinbox)

        version_label = QtWidgets.QLabel(f"<b>FCProject Circular Pattern V{__version__} aktiv</b>")
        version_label.setStyleSheet("color: #555555; font-size: 12px;")
        version_label.setTextFormat(Qt.RichText)
        layout.addWidget(version_label)

        button_layout = QtWidgets.QHBoxLayout()
        create_btn = QtWidgets.QPushButton("Circular Pattern erstellen")
        cancel_btn = QtWidgets.QPushButton("Abbrechen")

        create_btn.clicked.connect(self.create_pattern)
        cancel_btn.clicked.connect(self.reject)

        button_layout.addWidget(create_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        self.setLayout(layout)

    def _get_selected_label_text(self):
        selection = Gui.Selection.getSelection()
        if not selection:
            return "(Kein Objekt ausgewählt)"
        if len(selection) > 1:
            return "Mehrere Objekte ausgewählt – bitte genau ein Objekt wählen."
        source_element = selection[0]
        if not self._is_valid_source_element(source_element):
            return f"Ausgewähltes Objekt '{source_element.Label}' ist nicht gültig."
        return f"Ausgewählt: {source_element.Label} ({source_element.Name})"

    def _is_valid_source_element(self, element):
        if element is None:
            return False
        is_valid = False
        if hasattr(element, 'Shape') and element.Shape is not None:
            is_valid = True
        elif element.isDerivedFrom('Assembly::AssemblyObject'):
            is_valid = True
        elif element.isDerivedFrom('App::Part'):
            is_valid = True
        elif element.isDerivedFrom('PartDesign::Body'):
            is_valid = True
        elif element.isDerivedFrom('App::Link'):
            is_valid = True
        if not is_valid:
            return False
        if element.TypeId == 'App::DocumentObjectGroup':
            return False
        name_lower = element.Name.lower() if hasattr(element, 'Name') else ''
        label_lower = element.Label.lower() if hasattr(element, 'Label') else ''
        if 'joint' in name_lower or 'joint' in label_lower:
            return False
        if 'bom' in name_lower or 'bom' in label_lower:
            return False
        return True

    def _get_selected_source_element(self):
        selection = Gui.Selection.getSelection()
        if len(selection) != 1:
            return None
        source_element = selection[0]
        return source_element if self._is_valid_source_element(source_element) else None

    def create_pattern(self):
        source_element = self._get_selected_source_element()
        count = self.count_spinbox.value()
        radius = self.radius_spinbox.value()

        if not source_element:
            QtWidgets.QMessageBox.warning(
                self,
                "Fehler",
                "Bitte wähle ein gültiges Quell-Element im Dokument genau einmal aus."
            )
            self.selected_label.setText(self._get_selected_label_text())
            return

        try:
            self.creator.create_circular_pattern(
                source_element_name=source_element.Name,
                count=count,
                radius=radius
            )
            QtWidgets.QMessageBox.information(
                self,
                "Erfolg",
                f"FCProject Circular Pattern: {count} Elemente auf Radius {radius:.1f}mm erfolgreich erstellt!"
            )
            self.accept()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Fehler", f"Circular Pattern fehlgeschlagen: {str(e)}")


class AssemblyPatternGroupCommand:
    """Dropdown-Gruppe für alle Pattern-Befehle (lineares und zirkulares Pattern)."""

    def GetCommands(self):
        return ('FCProject_AssemblyPattern', 'FCProject_CircularPattern')

    def GetDefaultCommand(self):
        return 0

    def GetResources(self):
        return {
            'MenuText': 'FCProject Pattern',
            'ToolTip': 'Assembly Pattern Befehle (linear und zirkular)'
        }

    def IsActive(self):
        if not App.ActiveDocument:
            return False
        for obj in App.ActiveDocument.Objects:
            if obj.TypeId == "Assembly::AssemblyObject":
                return True
        return False


# Registriere den Command
Gui.addCommand('FCProject_AssemblyPattern', AssemblyPatternCommand())
Gui.addCommand('FCProject_CircularPattern', CircularPatternCommand())
Gui.addCommand('FCProject_PatternGroup', AssemblyPatternGroupCommand())
