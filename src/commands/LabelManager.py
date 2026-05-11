# Macro Version: 2.0.0 - Modul C: Label Manager (Klassen-Struktur)
import FreeCAD as App
import FreeCADGui as Gui

class LabelCleanerCommand:
    """Klasse für das Säubern von Objekt-Labels in Assemblies."""

    def GetResources(self):
        # Icon und Tooltip für die spätere Workbench-Integration
        return {
            'Pixmap': 'S_Label_Clean', # Platzhalter für ein Icon
            'MenuText': 'Labels säubern',
            'ToolTip': 'Entfernt automatische Suffixe wie 001, 002 von selektierten Objekten'
        }

    def Activated(self):
        """Dieser Code wird ausgeführt, wenn der Button gedrückt wird."""
        doc = App.ActiveDocument
        if not doc:
            return

        selection = Gui.Selection.getSelection()
        if not selection:
            App.Console.PrintMessage("Bitte Objekte zum Säubern auswählen.\n")
            return

        doc.openTransaction("Clean Labels")
        try:
            self._process_labels(selection)
            doc.commitTransaction()
            App.Console.PrintMessage("Labels erfolgreich gesäubert.\n")
        except Exception as e:
            doc.abortTransaction()
            App.Console.PrintError(f"Fehler: {str(e)}\n")
        
        doc.recompute()

    def _process_labels(self, objects):
        """Interne Logik: Entfernt die Suffixe."""
        for obj in objects:
            current_label = obj.Label
            # Logik: Wenn das Label auf Ziffern endet (z.B. P2A001), 
            # versuchen wir den Namen des Original-Bauteils wiederherzustellen.
            # Ein einfacher Weg: Wir nehmen das Label des LinkedObjects, falls es ein Link ist.
            if hasattr(obj, "LinkedObject") and obj.LinkedObject:
                clean_label = obj.LinkedObject.Label
                if obj.Label != clean_label:
                    obj.Label = clean_label
                    App.Console.PrintMessage(f"Gereinigt: {current_label} -> {clean_label}\n")

    def IsActive(self):
        """Bedingung, ob der Button klickbar ist."""
        return not App.ActiveDocument is None

# Für den Test als Makro:
if __name__ == "__main__":
    command = LabelCleanerCommand()
    if command.IsActive():
        command.Activated()
