from PySide6 import QtWidgets
import FreeCADGui as Gui

class FCProjectTaskPanel:
    def __init__(self):
        # Das ist das Herzstück deines Addons
        self.form = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.form)
        
        layout.addWidget(QtWidgets.QLabel("### FCProject: Neues Teil ###"))
        
        self.name_input = QtWidgets.QLineEdit("P1")
        layout.addWidget(QtWidgets.QLabel("Bauteil-Name:"))
        layout.addWidget(self.name_input)
        
        self.btn = QtWidgets.QPushButton("Erstellen & ArticleID setzen")
        self.btn.clicked.connect(self.create_part)
        layout.addWidget(self.btn)
        
        layout.addStretch()

    def create_part(self):
        import FreeCAD as App
        name = self.name_input.text()
        doc = App.activeDocument() or App.newDocument()
        
        # Neues Teil erstellen
        new_part = doc.addObject("App::Part", name)
        # ArticleID hinzufügen
        new_part.addProperty("App::PropertyString", "ArticleID", "FCProject")
        new_part.ArticleID = name
        
        App.Console.PrintMessage(f"FCProject: {name} erstellt.\n")
        doc.recompute()

    def getStandardButtons(self):
        # Zeigt OK und Abbrechen unten am Panel an
        return int(QtWidgets.QDialogButtonBox.Close)
