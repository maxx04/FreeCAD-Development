# FCProject: Repariert haengengebliebenes Selectable=False - bekannter FreeCAD-Bug beim Joint-
# "Isolate"-Feature (Transparent/Wireframe/Hidden): waehrend der Joint-Bearbeitung werden alle
# nicht isolierten Bauteile unauswaehlbar gemacht; wird der Dialog geschlossen, ohne "Isolate"
# manuell auf "Disabled" zurueckzustellen, bleibt das dauerhaft (auch in der Datei gespeichert)
# haengen - siehe patches/freecad-assembly-jointobject.patch Fix 5. Der Patch deckt nur den EINEN
# dort gepatchten Ausstiegspfad ab; find_stuck_objects() wird deshalb zusaetzlich automatisch vor
# jedem Speichern aus DocObserver.py aufgerufen (robuster als jeden FreeCAD-internen Ausstiegspfad
# einzeln zu patchen). Dieser Befehl hier bleibt als manuelles Werkzeug fuer bereits betroffene,
# schon gespeicherte Altdateien bzw. zum sofortigen Reparieren ohne extra Speichervorgang.
import FreeCAD as App
import FreeCADGui as Gui
from PySide6 import QtWidgets


def find_stuck_objects(doc):
    """Sammelt alle Objekte im Dokument, deren ViewObject.Selectable faelschlich auf False steht."""
    stuck = []
    for obj in doc.Objects:
        vobj = getattr(obj, "ViewObject", None)
        if vobj is not None and hasattr(vobj, "Selectable") and vobj.Selectable is False:
            stuck.append(obj)
    return stuck


class SelectableRepairCommand:
    """Befehl: macht im aktiven Dokument haengengebliebene, unauswaehlbare Bauteile wieder
    auswaehlbar (siehe Modul-Docstring fuer die Bug-Ursache)."""

    def GetResources(self):
        import os
        icon_path = os.path.join(os.path.dirname(__file__), 'resources', 'icons', 'selectable_repair.svg')
        return {
            'Pixmap': icon_path,
            'MenuText': 'FCProject: Auswählbarkeit reparieren',
            'ToolTip': 'Macht Bauteile, die durch den Joint-Isolate-Bug unauswählbar hängen geblieben sind, wieder auswählbar'
        }

    def Activated(self):
        doc = App.ActiveDocument
        main_win = Gui.getMainWindow()
        if not doc:
            QtWidgets.QMessageBox.warning(main_win, "FCProject", "Bitte öffne zuerst ein Dokument.")
            return

        stuck = find_stuck_objects(doc)
        if not stuck:
            if main_win:
                main_win.statusBar().showMessage("FCProject: Keine unauswählbaren Bauteile gefunden.", 4000)
            App.Console.PrintMessage("FCProject: Keine unauswählbaren Bauteile im aktiven Dokument gefunden.\n")
            return

        for obj in stuck:
            obj.ViewObject.Selectable = True

        names = ", ".join(o.Label for o in stuck)
        App.Console.PrintMessage(
            f"FCProject: {len(stuck)} Bauteil(e) wieder auswählbar gemacht: {names}\n"
        )
        if main_win:
            main_win.statusBar().showMessage(f"FCProject: {len(stuck)} Bauteil(e) repariert.", 5000)

    def IsActive(self):
        return App.ActiveDocument is not None


Gui.addCommand('FCProject_RepairSelectable', SelectableRepairCommand())
