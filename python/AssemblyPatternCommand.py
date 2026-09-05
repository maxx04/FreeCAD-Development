import FreeCAD as App
import FreeCADGui as Gui
from PySide6 import QtWidgets

from PatternFeatures import (
    make_linear_pattern, make_circular_pattern, _is_valid_source_element,
    delete_pattern_safely, LinearPatternProxy, CircularPatternProxy,
)


def _get_selected_pattern():
    """Liefert das selektierte Pattern-Feature-Objekt, falls genau eines mit
    LinearPatternProxy/CircularPatternProxy ausgewaehlt ist, sonst None."""
    selection = Gui.Selection.getSelection()
    if len(selection) != 1:
        return None
    obj = selection[0]
    proxy = getattr(obj, 'Proxy', None)
    if isinstance(proxy, (LinearPatternProxy, CircularPatternProxy)):
        return obj
    return None


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


class DeletePatternCommand:
    """Löscht ein Pattern-Feature (Linear/Circular) samt Kopien und Joints sicher per
    direktem Skript-Aufruf - siehe delete_pattern_safely() in PatternFeatures.py für
    die Begründung, warum die normale Entf-Taste dafür nicht zuverlässig funktioniert."""

    def GetResources(self):
        import os
        icon_path = os.path.join(os.path.dirname(__file__), 'resources', 'icons', 'assembly_pattern.svg')
        return {
            'Pixmap': icon_path,
            'MenuText': 'FCProject: Pattern löschen',
            'ToolTip': (
                'Löscht das ausgewählte Pattern-Feature samt aller Kopien und Joints.\n'
                'Bitte für Pattern-Objekte anstelle der Entf-Taste verwenden - die normale\n'
                'Lösch-Transaktion ist bei Pattern+Joints nachweislich instabil (null shape).'
            )
        }

    def Activated(self):
        main_win = Gui.getMainWindow()
        obj = _get_selected_pattern()
        if obj is None:
            QtWidgets.QMessageBox.warning(
                main_win,
                "FCProject Pattern löschen",
                "Bitte wähle genau ein Pattern-Feature-Objekt aus (Linear Pattern oder Circular Pattern)."
            )
            return

        reply = QtWidgets.QMessageBox.question(
            main_win,
            "FCProject Pattern löschen",
            f"'{obj.Label}' inklusive aller Kopien und Joints wirklich löschen?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return

        removed, failed = delete_pattern_safely(obj)

        if failed:
            QtWidgets.QMessageBox.warning(
                main_win,
                "FCProject Pattern löschen",
                f"{len(removed)} Objekt(e) entfernt, aber {len(failed)} konnten nicht entfernt "
                f"werden:\n{', '.join(failed)}\n\nBitte FreeCAD neu starten und erneut versuchen."
            )
        else:
            App.Console.PrintMessage(
                f"FCProject: Pattern '{obj.Label}' und {len(removed) - 1} zugehörige Objekt(e) "
                f"erfolgreich entfernt.\n"
            )

    def IsActive(self):
        return _get_selected_pattern() is not None


class AssemblyPatternGroupCommand:
    """Dropdown-Gruppe für alle Pattern-Befehle (lineares und zirkulares Pattern)."""

    def GetCommands(self):
        return ('FCProject_AssemblyPattern', 'FCProject_CircularPattern', 'FCProject_DeletePattern')

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
Gui.addCommand('FCProject_DeletePattern', DeletePatternCommand())
Gui.addCommand('FCProject_PatternGroup', AssemblyPatternGroupCommand())
