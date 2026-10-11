# FCProject: setzt das Placement der aktuell ausgewaehlten Objekte auf Identity zurueck
# (Position 0,0,0 / Rotationsachse 0,0,1 / Winkel 0) - haeufig gebraucht, um ein versehentlich
# verschobenes/verdrehtes Teil ohne manuelles Eintippen von Position/Achse/Winkel im
# Eigenschaften-Editor wieder auf den Nullpunkt zu bringen.
import FreeCAD as App
import FreeCADGui as Gui
from PySide6 import QtWidgets


def reset_placement(obj):
    """Setzt obj.Placement auf Identity (Position (0,0,0), Achse (0,0,1), Winkel 0)."""
    obj.Placement = App.Placement(App.Vector(0, 0, 0), App.Rotation(App.Vector(0, 0, 1), 0))


class ResetPlacementCommand:
    """Befehl: setzt das Placement aller ausgewählten Objekte auf Identity zurück."""

    def GetResources(self):
        return {
            # Wiederverwendetes FreeCAD-Kern-Icon (src/Gui/Icons/Std_Placement.svg) - kein
            # eigenes Asset noetig, FreeCADs BitmapFactory loest den Namen selbst auf.
            'Pixmap': 'Std_Placement',
            'MenuText': 'FCProject: Placement zurücksetzen',
            'ToolTip': 'Setzt Position (0,0,0) und Achse/Winkel (0,0,1 / 0°) der ausgewählten Objekte zurück'
        }

    def Activated(self):
        doc = App.ActiveDocument
        main_win = Gui.getMainWindow()
        if not doc:
            QtWidgets.QMessageBox.warning(main_win, "FCProject", "Bitte öffne zuerst ein Dokument.")
            return

        selection = Gui.Selection.getSelection()
        if not selection:
            QtWidgets.QMessageBox.warning(
                main_win, "FCProject", "Bitte wähle zuerst ein oder mehrere Objekte aus."
            )
            return

        doc.openTransaction("FCProject: Placement zurücksetzen")
        for obj in selection:
            reset_placement(obj)
        doc.commitTransaction()
        doc.recompute()

        names = ", ".join(o.Label for o in selection)
        App.Console.PrintMessage(
            f"FCProject: Placement von {len(selection)} Objekt(en) zurückgesetzt: {names}\n"
        )
        if main_win:
            main_win.statusBar().showMessage(
                f"FCProject: Placement von {len(selection)} Objekt(en) zurückgesetzt.", 5000
            )

    def IsActive(self):
        return App.ActiveDocument is not None


Gui.addCommand('FCProject_ResetPlacement', ResetPlacementCommand())
