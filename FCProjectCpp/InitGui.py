import FreeCADGui as Gui
import FCProjectCpp # Das ist jetzt dein C++ Modul

class FCProjectCppWorkbench(Gui.Workbench):
    def Initialize(self):
        # Wir erzeugen eine Instanz deiner C++ Klasse
        self.gui_obj = FCProjectCpp.InitGui()
        self.gui_obj.initialize()
        
    def Activated(self):
        self.gui_obj.activated()

Gui.addWorkbench(FCProjectCppWorkbench())