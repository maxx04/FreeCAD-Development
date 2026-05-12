# Korrigierte Version für FCProject
import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtWidgets  # FreeCAD 1.1 liefert PySide meist so aus

class HelloWorldPanel:
    """Ein einfaches Panel für die Seitenleiste (TaskPanel)."""
    def __init__(self):
        # Wir erstellen ein Standard Qt Widget
        self.form = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.form)
        
        label = QtWidgets.QLabel("FCProject aktiv!")
        # Optional: Ein bisschen Styling für das Addon-Gefühl
        label.setStyleSheet("font-weight: bold; color: #2e86c1; font-size: 14px;")
        
        btn = QtWidgets.QPushButton("OK - Verstanden")
        btn.clicked.connect(self.accept)
        
        layout.addWidget(label)
        layout.addWidget(btn)
        layout.addStretch() # Schiebt alles nach oben
        
    def accept(self):
        # Schließt das TaskPanel in der Seitenleiste
        Gui.Control.closeDialog()

# Der Rest (HelloWorldCommand) bleibt gleich, 
# stelle nur sicher, dass Gui.Control.showDialog(HelloWorldPanel()) 
# in der Activated-Methode steht.
