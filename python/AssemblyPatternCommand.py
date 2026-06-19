import FreeCAD as App
import FreeCADGui as Gui
from PySide6 import QtWidgets

from PatternFeatures import make_linear_pattern, make_circular_pattern, _is_valid_source_element


def _find_assembly(doc):
    for obj in doc.Objects:
        if obj.TypeId == "Assembly::AssemblyObject":
            return obj
    return None


def _get_selected_source_element(assembly):
    selection = Gui.Selection.getSelection()
    if len(selection) != 1:
        return None
    source_element = selection[0]
    if source_element == assembly:
        return None
    return source_element if _is_valid_source_element(source_element) else None


class AssemblyPatternCommand:
    """Command zum Erstellen eines parametrischen linearen Pattern-Features in einer Assembly."""

    def GetResources(self):
        import os
        icon_path = os.path.join(os.path.dirname(__file__), 'resources', 'icons', 'assembly_pattern.svg')
        return {
            'Pixmap': icon_path,
            'MenuText': 'FCProject: Lineares Assembly Pattern',
            'ToolTip': 'Erstellt ein parametrisches lineares Pattern-Feature eines Elements in einer Assembly'
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

        assembly = _find_assembly(active_doc)
        if not assembly:
            QtWidgets.QMessageBox.warning(
                main_win,
                "FCProject Assembly Pattern",
                "Keine Assembly im Dokument gefunden!"
            )
            return

        source_element = _get_selected_source_element(assembly)
        if not source_element:
            QtWidgets.QMessageBox.warning(
                main_win,
                "FCProject Assembly Pattern",
                "Bitte wähle ein gültiges Quell-Element im Dokument genau einmal aus.\n"
                "Die oberste Assembly selbst kann nicht als Pattern-Quelle verwendet werden."
            )
            return

        try:
            obj = make_linear_pattern(active_doc, assembly, source_element)
            Gui.Selection.clearSelection()
            Gui.ActiveDocument.setEdit(obj.Name)
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
        return _find_assembly(App.ActiveDocument) is not None


class CircularPatternCommand:
    """Command zum Erstellen eines parametrischen zirkularen (Polar-)Pattern-Features in einer Assembly."""

    def GetResources(self):
        import os
        icon_path = os.path.join(os.path.dirname(__file__), 'resources', 'icons', 'circular_pattern.svg')
        return {
            'Pixmap': icon_path,
            'MenuText': 'FCProject: Zirkulares Assembly Pattern',
            'ToolTip': 'Erstellt ein parametrisches Polar-Pattern-Feature eines Elements in einer Assembly'
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

        assembly = _find_assembly(active_doc)
        if not assembly:
            QtWidgets.QMessageBox.warning(
                main_win,
                "FCProject Circular Pattern",
                "Keine Assembly im Dokument gefunden!"
            )
            return

        source_element = _get_selected_source_element(assembly)
        if not source_element:
            QtWidgets.QMessageBox.warning(
                main_win,
                "FCProject Circular Pattern",
                "Bitte wähle ein gültiges Quell-Element im Dokument genau einmal aus.\n"
                "Die oberste Assembly selbst kann nicht als Pattern-Quelle verwendet werden."
            )
            return

        try:
            obj = make_circular_pattern(active_doc, assembly, source_element)
            Gui.Selection.clearSelection()
            Gui.ActiveDocument.setEdit(obj.Name)
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
        return _find_assembly(App.ActiveDocument) is not None


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
        return _find_assembly(App.ActiveDocument) is not None


# Registriere den Command
Gui.addCommand('FCProject_AssemblyPattern', AssemblyPatternCommand())
Gui.addCommand('FCProject_CircularPattern', CircularPatternCommand())
Gui.addCommand('FCProject_PatternGroup', AssemblyPatternGroupCommand())
