import FreeCADGui as Gui

class HelloWorldCommand:
    def GetResources(self):
        return {'MenuText': 'Hello World', 'Accel': 'Ctrl+Shift+H'}

    def Activated(self):
        from PySide6 import QtWidgets
        QtWidgets.QMessageBox.information(None, "FCProject", "Profi-Modus aktiv!")

# Das hier ist wichtig für die Workbench-Integration:
Gui.addCommand('FCProject_HelloWorld', HelloWorldCommand())
