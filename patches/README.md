# FreeCAD-Core-Patches

Diese Patches beheben Bugs in der lokal gebauten FreeCAD-Installation
(`/home/maxx/freecad/freecad-source`, `/home/maxx/freecad/install`), die beim
Arbeiten mit FCProject aufgefallen sind. Sie gehören nicht zu FCProject selbst,
sondern zu FreeCAD - werden hier nur abgelegt, damit sie nach einem `git pull`,
`git stash` oder einer Neuinstallation von FreeCAD nicht verloren gehen.

## freecad-assembly-jointobject.patch

Betrifft `src/Mod/Assembly/JointObject.py` (Assembly-Workbench):

1. **Cross-Document-Crash beim Joint-Erstellen** (`MakeJointSelGate.allow`):
   Hovern/Klicken auf eine LCS/Origin-Achse eines Teils, das per `App::Link`
   aus einem anderen Dokument eingebunden ist (Standard-Architektur in FCProjects
   PDM-Workflow: ein Teil = eine eigene .FCStd-Datei), führte zu
   `Base.FreeCADError: Cannot check an object from another document with this group`,
   weil `Assembly::AssemblyObject.hasObject()` keine Cross-Document-Prüfung
   unterstützt.

2. **Distance/Angle/Offset/Rotation wird im Joint-Dialog nicht übernommen**
   (`TaskAssemblyCreateJoint.__init__`):
   `QuantitySpinBox.valueChanged` ist in C++ auf `double` und `Base::Quantity`
   überladen; PySide6 bindet in diesem Build aber nur die `Base::Quantity`-
   Variante nach Python, die es nicht marshallen kann
   (`TypeError: Cannot call meta function ... parameter 0 of type "Base::Quantity"
   cannot be converted`). Der Python-Slot wurde dadurch nie aufgerufen, der
   eingegebene Wert ging verloren. Fix: stattdessen `textChanged` (QString)
   verbinden, das `QuantitySpinBox` an derselben Stelle direkt nach dem
   internen Value-Update emittiert (`QuantitySpinBox::updateFromCache`).

### Anwenden

Nach einem frischen Checkout/Build von FreeCAD:

```bash
cd /home/maxx/freecad/freecad-source
git apply /home/maxx/Documents/FreeCAD-Development/FCProject/patches/freecad-assembly-jointobject.patch
cp src/Mod/Assembly/JointObject.py /home/maxx/freecad/install/Mod/Assembly/JointObject.py
```

(Reines Python, kein Rebuild von FreeCADGui nötig - Kopieren in `install/`
reicht für sofortige Wirkung.)

## freecad-cmake-disable-tests.patch

Betrifft `CMakeLists.txt`. `ENABLE_DEVELOPER_TESTS` zieht `add_subdirectory(tests)`
nach, was `find_package(GTest REQUIRED)` voraussetzt. GTest ist auf dieser
Maschine nicht installiert, daher schlägt die CMake-Konfiguration sonst fehl.
Kommentiert `add_subdirectory(tests)` aus.

## freecad-navigation-qbytearray-fix.patch

Betrifft `src/Gui/PreferencePages/DlgSettingsNavigation.cpp` und
`src/Mod/Start/Gui/GeneralSettingsWidget.cpp`. `QByteArray data(style.first.getName())`
ist mit dem hier verwendeten Compiler/Qt6 mehrdeutig, weil `Base::Type::getName()`
kein `const char*` mehr direkt liefert, das eindeutig auf einen der
`QByteArray`-Konstruktoren passt. Fix: explizit `.data()` und `.size()`
übergeben.

## freecad-propertyeditor-qstring-fix.patch

Betrifft `src/Gui/propertyeditor/PropertyEditor.cpp`. `QString::operator+=`
mit einem `std::string`-Argument (Rückgabe der lokalen `indent()`-Hilfsfunktion)
ist mit dem hier verwendeten Qt6/Compiler nicht eindeutig auflösbar
(`error: no match for 'operator+=' (operand types are 'QString' and 'std::string')`).
Fix: explizit über `QString::fromStdString(...)` konvertieren. Trat erstmals
beim Umstieg von 1.2.0dev auf 26.3.0dev auf (neuer Code in `getPropUses`/
`getPropUsesObj`/`getPropUsesDoc`).

### Anwenden (alle Patches, nach frischem Checkout/Pull)

```bash
cd /home/maxx/freecad/freecad-source
git apply /home/maxx/Documents/FreeCAD-Development/FCProject/patches/freecad-assembly-jointobject.patch
git apply /home/maxx/Documents/FreeCAD-Development/FCProject/patches/freecad-cmake-disable-tests.patch
git apply /home/maxx/Documents/FreeCAD-Development/FCProject/patches/freecad-navigation-qbytearray-fix.patch
git apply /home/maxx/Documents/FreeCAD-Development/FCProject/patches/freecad-propertyeditor-qstring-fix.patch
cp src/Mod/Assembly/JointObject.py /home/maxx/freecad/install/Mod/Assembly/JointObject.py
```
