import FreeCADGui


class FCProjectWorkbench(FreeCADGui.Workbench):
    # Wir nutzen ein eingebautes Icon, das garantiert existiert
    Icon = FreeCADGui.getIcon("freecad") 
    MenuText = "FCProject"
    ToolTip = "Professionelles Projektmanagement"

    def Initialize(self):
        # Hier laden wir unsere Commands-Datei
        import Commands
        # Liste der Commands, die in die Toolbar sollen        
        self.appendToolbar("FCProject Tools", ["FCProject_CreatePart"])


    def GetClassName(self):
        return "Gui::PythonWorkbench"

FreeCADGui.addWorkbench(FCProjectWorkbench())
