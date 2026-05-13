# Macro Version: 1.3.0 - FCProject: Native Workbench Commands & TaskPanel
import os
import debugpy
import FreeCAD as App
import FreeCADGui as Gui
# Modul-Import für plattform- und versionsunabhängiges Qt
try:
    # Standardweg für FreeCAD 1.1 (Qt6)
    from PySide6 import QtWidgets, QtCore, QtGui
except ImportError:
    # Fallback-Sicherungen für ältere Versionen
    try:
        from PySide2 import QtWidgets, QtCore, QtGui
    except ImportError:
        from PySide import QtWidgets, QtCore, QtGui



# --- DEBUGGER SETUP ---
# Unterdrückt die Validierungswarnung für Python 3.11+
os.environ["PYDEVD_DISABLE_FILE_VALIDATION"] = "1"

def start_debugger():
    try:
        # Port 5678 für VS Code Remote Attach
        debugpy.listen(("localhost", 5678))
    except RuntimeError:
        # Debugger läuft bereits
        pass

start_debugger()

# --- TASK PANEL KLASSE ---
class FCProjectTaskPanel:
    """Das Seitenmenü für FCProject Operationen."""
    def __init__(self):
        # Basis-Widget erstellen
        self.form = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.form)
        
        # Titel
        title = QtWidgets.QLabel("### FCProject Editor ###")
        layout.addWidget(title)
        
        # Eingabe für Bauteilname
        layout.addWidget(QtWidgets.QLabel("Bauteil-Name / ArticleID:"))
        self.name_input = QtWidgets.QLineEdit("P1")
        layout.addWidget(self.name_input)
        
        # Button zum Erstellen
        self.create_btn = QtWidgets.QPushButton("Neues Teil anlegen")
        self.create_btn.clicked.connect(self.create_part)
        layout.addWidget(self.create_btn)
        
        layout.addStretch() # Alles nach oben schieben

    def create_part(self):
        """Erstellt ein App::Part mit automatischer ArticleID."""
        name = self.name_input.text()
        doc = App.activeDocument() or App.newDocument("FCProject_Doc")
        
        # 1. Neues Part-Objekt (Container) erstellen
        new_part = doc.addObject("App::Part", name)
        
        # 2. Custom Property 'ArticleID' hinzufügen
        if not hasattr(new_part, "ArticleID"):
            new_part.addProperty("App::PropertyString", "ArticleID", "FCProject", "Eindeutige ID für die Stückliste")
        
        # 3. Werte setzen
        new_part.ArticleID = name
        new_part.Label = name
        
        doc.recompute()
        App.Console.PrintMessage(f"FCProject: Bauteil '{name}' erfolgreich mit ArticleID erstellt.\n")

    def getStandardButtons(self):
        # Zeigt nur einen Schließen-Button am unteren Rand des TaskPanels
        return QtWidgets.QDialogButtonBox.Close





# --- COMMAND KLASSEN (Für die Toolbar) ---

class FCProject_CreatePart_Command:
    """Befehl zum Öffnen des FCProject TaskPanels."""
    
    def GetResources(self):
        return {
            'Pixmap': 'freecad', # Nutzt das Standard FreeCAD Icon
            'MenuText': 'FCProject: Teil erstellen',
            'ToolTip': 'Öffnet das Panel zur automatisierten Bauteilerstellung'
        }

    def Activated(self):
        # Hier wird das TaskPanel in der Seitenleiste geöffnet
        panel = FCProjectTaskPanel()
        Gui.Control.showDialog(panel)

    def IsActive(self):
        # Der Button ist nur aktiv, wenn ein Dokument existiert oder erstellt werden kann
        return True

# --- REGISTRIERUNG ---
# Diese Namen müssen exakt mit denen in InitGui.py übereinstimmen!
Gui.addCommand('FCProject_CreatePart', FCProject_CreatePart_Command())

App.Console.PrintMessage("FCProject: Commands erfolgreich geladen.\n")
