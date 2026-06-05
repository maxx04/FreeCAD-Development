import FreeCADGui as App
import FCProjectCpp 

class FCProjectWorkbench(App.Workbench):
    MenuText = "FCProject"
    
    def Initialize(self):
        # 1. HIER wird die Brücke gebaut!
        # Wir instanziieren die C++ Klasse und speichern sie in 'self.gui_obj'
        self.gui_obj = FCProjectCpp.InitGui() 
        
        # 2. Jetzt kannst du die Initialisierung aus C++ aufrufen (falls nötig)
        self.gui_obj.initialize()
        # Initialisierung der C++ Brücke
        self.gui_obj = FCProjectCore.InitGui()

        
        # 3. Hier dann deine Python-Commands und Toolbars laden
        # ... (deine vorhandenen Commands hier)
        
        self.appendToolbar("FCProject Tools", [
            "FCProject_ProjectManager", 
            # ... usw
        ])

    def Activated(self):
        # 4. Zugriff auf C++ Logik, wenn das Modul aktiviert wird
        if hasattr(self, 'gui_obj'):
            self.gui_obj.activated()
        
        # ... deine restliche Python-Logik (JSON Check etc.)

# Workbench registrieren
def setup_workbench():
    # Prüfe, ob die Workbench schon existiert
    workbenches = App.listWorkbenches()
    if "FCProject" not in workbenches:
        App.addWorkbench(FCProjectWorkbench())
    else:
        App.Console.PrintMessage("FCProject: Workbench existiert bereits, überspringe Registrierung.\n")

# Workbench registrieren
setup_workbench()