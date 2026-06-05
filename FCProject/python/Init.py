import FreeCAD

# Richtig: FreeCADGui ist das Modul, nicht FreeCAD.Gui
FreeCAD.Console.PrintMessage("Loading FCProjectCpp Module...\n")

# Wir müssen hier kein Gui importieren, 
# da FreeCAD das automatisch über InitGui.py macht, 
# sobald der Loader läuft.