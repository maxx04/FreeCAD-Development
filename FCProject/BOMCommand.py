# Macro Version: 1.0.0 - FCProject: BOMCommand für den eigenständigen Symbolleisten-Button
import os
import FreeCAD as App
import FreeCADGui as Gui
from PySide6 import QtWidgets
from BOMManager import BOMManager

class BOMExportCommand:
    def GetResources(self):
        import os
        icon_path = os.path.join(os.path.dirname(__file__), 'resources', 'icons', 'bom_export.svg')
        return {
            'Pixmap': icon_path,
            'MenuText': 'FCProject: Stückliste (BOM) exportieren',
            'ToolTip': 'Generiert eine Excel-konforme CSV-Stückliste aus dem aktiven Dokument'
        }

    def Activated(self):
        active_doc = App.ActiveDocument
        main_win = Gui.getMainWindow()

        if not active_doc:
            QtWidgets.QMessageBox.warning(main_win, "FCProject BOM", "Bitte öffne zuerst das Dokument, das du scannen möchtest!")
            return

        # Den Projektpfad ermitteln (Arbeitsverzeichnis)
        target_dir = os.getcwd()
        folder_name = os.path.basename(target_dir)

        if not folder_name.startswith("PROJ_"):
            # Fallback falls os.getcwd() nicht im Projektordner steht
            if active_doc.FileName:
                target_dir = os.path.dirname(active_doc.FileName)
            else:
                QtWidgets.QMessageBox.warning(main_win, "FCProject BOM", "Das Projekt wurde noch nicht initialisiert (Nutze Button 1)!")
                return

        try:
            # Stücklisten-Manager starten und Export triggern
            manager = BOMManager(active_doc)
            csv_result_path = manager.export_to_csv(target_dir)
            
            if csv_result_path:
                QtWidgets.QMessageBox.information(
                    main_win, "FCProject: BOM Export", 
                    f"Stückliste für '{active_doc.Label}' erfolgreich generiert!\n\n"
                    f"Datei: {os.path.basename(csv_result_path)}\n"
                    f"Ordner: {target_dir}"
                )
        except Exception as e:
            QtWidgets.QMessageBox.critical(main_win, "FCProject BOM", f"Fehler beim Stücklisten-Export: {str(e)}")

    def IsActive(self):
        return App.ActiveDocument is not None

Gui.addCommand('FCProject_ExportBOM', BOMExportCommand())
