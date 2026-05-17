# Macro Version: 1.0.0 - FCProject: AssemblyPatternCommand für Array-Erstellung über Joints
import FreeCAD as App
import FreeCADGui as Gui
from PySide6 import QtWidgets
from AssemblyPatternCreator import AssemblyPatternCreator

class AssemblyPatternCommand:
    """Command zum Erstellen eines Pattern (Array) von Elementen über Joints in einer Assembly."""
    
    def GetResources(self):
        import os
        icon_path = os.path.join(os.path.dirname(__file__), 'resources', 'icons', 'assembly_pattern.svg')
        return {
            'Pixmap': icon_path,
            'MenuText': 'FCProject: Assembly Pattern via Joints',
            'ToolTip': 'Erstellt ein Array-Pattern eines Elements in der Assembly über Joints'
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
            self.creator = AssemblyPatternCreator(doc, assembly)
            self.init_ui()
        except Exception as e:
            App.Console.PrintError(f"FCProject Dialog Init Error: {str(e)}\n")
            import traceback
            App.Console.PrintError(f"Traceback: {traceback.format_exc()}\n")
            raise

    def init_ui(self):
        self.setWindowTitle("FCProject: Assembly Pattern erstellen")
        self.setGeometry(100, 100, 500, 400)

        layout = QtWidgets.QVBoxLayout()

        # Quell-Element auswählen
        layout.addWidget(QtWidgets.QLabel("Quell-Element (zu vervielfältigend):"))
        self.element_combo = QtWidgets.QComboBox()
        self.populate_elements()
        layout.addWidget(self.element_combo)

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
        self.distance_spinbox.setValue(10.0)
        self.distance_spinbox.setSingleStep(1.0)
        layout.addWidget(self.distance_spinbox)

        # Pattern-Richtung
        layout.addWidget(QtWidgets.QLabel("Pattern-Richtung:"))
        self.direction_combo = QtWidgets.QComboBox()
        self.direction_combo.addItems(["X-Achse", "Y-Achse", "Z-Achse"])
        layout.addWidget(self.direction_combo)

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

    def populate_elements(self):
        """Füllt die Combo-Box mit verfügbaren Elementen."""
        # FreeCAD 1.1: Verwende Objects statt Children
        try:
            objects = getattr(self.assembly, 'Objects', None) or getattr(self.assembly, 'Group', [])
            if not objects:
                objects = []
            
            App.Console.PrintMessage(f"FCProject: {len(objects)} Objekte in Assembly gefunden.\n")
            
            # Filter: nur copyable Objekte
            copyable_objects = []
            for obj in objects:
                if not hasattr(obj, 'Label'):
                    continue
                if obj.TypeId == 'App::DocumentObjectGroup':
                    continue
                if obj.TypeId == 'Assembly::AssemblyObject':
                    continue
                
                # Prüfe ob Objekt eine Shape oder LinkedObject hat
                has_shape = hasattr(obj, 'Shape') and obj.Shape is not None
                has_link = hasattr(obj, 'LinkedObject')
                
                if has_shape or has_link or hasattr(obj, 'PropertiesList'):
                    copyable_objects.append(obj)
                    App.Console.PrintMessage(f"FCProject: Objekt '{obj.Label}' (Type: {obj.TypeId}) ist kopierbar.\n")
            
            for obj in copyable_objects:
                self.element_combo.addItem(obj.Label, obj)
            
            if self.element_combo.count() == 0:
                self.element_combo.addItem("(Keine kopierbaren Elemente)", None)
                App.Console.PrintWarning("FCProject: Keine kopierbaren Elemente in Assembly gefunden.\n")
        except Exception as e:
            App.Console.PrintError(f"FCProject: Fehler beim Auflisten der Elemente: {str(e)}\n")
            import traceback
            App.Console.PrintError(traceback.format_exc())
            self.element_combo.addItem("(Fehler beim Auflisten)", None)

    def create_pattern(self):
        """Erstellt das Pattern mit den Dialog-Einstellungen."""
        source_element = self.element_combo.currentData()
        count = self.count_spinbox.value()
        distance = self.distance_spinbox.value()
        direction = self.direction_combo.currentText()

        if not source_element:
            QtWidgets.QMessageBox.warning(self, "Fehler", "Bitte wähle ein Quell-Element!")
            return

        try:
            self.creator.create_pattern(
                source_element=source_element,
                count=count,
                distance=distance,
                direction=direction
            )
            
            QtWidgets.QMessageBox.information(
                self,
                "Erfolg",
                f"Pattern mit {count} Kopien erfolgreich erstellt!"
            )
            self.accept()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Fehler", f"Pattern-Erstellung fehlgeschlagen: {str(e)}")


# Registriere den Command
Gui.addCommand('FCProject_AssemblyPattern', AssemblyPatternCommand())
