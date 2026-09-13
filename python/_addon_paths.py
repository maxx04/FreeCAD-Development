# FCProject: liefert den Pfad dieses Addons robust, ohne auf __file__ in InitGui.py angewiesen
# zu sein.
#
# FreeCADs Mod-Lader fuehrt InitGui.py per exec(compile(...)) aus, nicht per normalem import -
# __file__ ist darin deshalb NICHT definiert (siehe Python-Doku zu exec(): ohne eigenes
# globals-Dict erbt der exec'te Code den Namensraum der aufrufenden Funktion, die selbst kein
# __file__ definiert). Dieses winzige Hilfsmodul wird dagegen ganz regulaer importiert -
# python/ steht dank package.xmls <subdirectory>python</subdirectory> bereits automatisch auf
# sys.path (FreeCADs eigener App/FreeCADInit.py: DirMod.process_metadata()) - und bekommt
# dadurch ein korrektes __file__. Derselbe Trick wie im sheetmetal-Addon
# (SheetMetalTools.py: "mod_path = os.path.dirname(__file__)").
import os

PYTHON_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(PYTHON_DIR)
