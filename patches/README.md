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

3. **Gleiches Problem bei den Limit-Spinboxen** (2026-08-08 nachgetragen,
   gemeldet als Bug in der Gleitverbindung/"Slider"-Joint):
   `limitLenMinSpinbox`/`limitLenMaxSpinbox`/`limitRotMinSpinbox`/
   `limitRotMaxSpinbox` (Weg-/Winkel-Begrenzung bei Cylindrical/Slider/
   Revolute-Joints) wurden beim ursprünglichen Fix übersehen und hingen noch
   am kaputten `valueChanged` - gleicher Fehler
   (`onLimitLenMinChanged`/`onLimitLenMaxChanged` etc. wurden nie aufgerufen,
   Weg-Limits gingen verloren). Gleicher Fix: `textChanged` statt
   `valueChanged`.

4. **Zweites Bauteil nach Joint-Erstellung nicht mehr ziehbar** (2026-08-08,
   `TaskAssemblyCreateJoint.accept()`): bei einer dokumentübergreifenden
   Referenz (PDM-Standardfall: Teil = eigenes `.FCStd`, per `App::Link`
   eingebunden) kann die persistente Element-Referenz (`Reference1`/
   `Reference2`) direkt nach dem ersten Recompute noch nicht auflösbar sein
   (`"?"` im Elementnamen). `execute()` wirft dafür bewusst eine Exception
   ("Broken link in..."), der Joint geht in den Fehlerzustand
   (`"Invalid" in joint.State`) und wird von
   `AssemblyObject::getJoints()` komplett aus dem Verbindungsgraphen entfernt
   - das zweite Bauteil lässt sich danach lautlos nicht mehr ziehen, ohne
   sichtbaren Fehler in der Oberfläche. Nutzer-Workaround war manuelles
   Suppress/Unsuppress des Joints (erzwingt eine erneute Referenz-Auflösung,
   die im zweiten Anlauf meist gelingt). Fix automatisiert genau das **nur
   wenn der Fehlerfall tatsächlich eintritt** (kein blinder Fallback bei
   jeder Joint-Erstellung) und protokolliert es immer sichtbar über die
   FreeCAD-Konsole (`PrintWarning` beim Auto-Fix-Versuch, `PrintError` falls
   auch der zweite Anlauf fehlschlägt - dann muss manuell geprüft werden).

5. **Bauteile bleiben nach Joint-Bearbeitung dauerhaft nicht mehr auswählbar**
   (2026-08-09, `TaskAssemblyCreateJoint.deactivate()`): der Joint-Dialog hat
   ein "Isolate"-Feature (Dropdown Transparent/Wireframe/Hidden/Disabled), das
   beim Bearbeiten eines Joints alle Bauteile außer den zwei gerade
   referenzierten unauswählbar/ausgeblendet macht (`Selectable = False`), um
   die Positionierung zu erleichtern. Das Zurücksetzen (`clearIsolate()`)
   wurde bisher nur ausgelöst, wenn man die Dropdown manuell auf "Disabled"
   zurückstellte - schloss man den Dialog per OK/Abbrechen während Isolate
   noch aktiv war, blieb `Selectable = False` auf den nicht isolierten
   Bauteilen für immer hängen (der Wiederherstellungs-Backup existiert nur im
   RAM des ViewProviders und geht beim Schließen/Speichern des Dokuments
   verloren - `Selectable = False` wird dann fest in die `.FCStd`-Datei
   geschrieben). Nutzer-Repro: Baugruppe mit 7 kettenartig über
   Gleitverbindungen verbundenen Panels, nach mehreren Joint-Bearbeitungen
   waren nur noch 3 der 7 Panels auswählbar. Fix: `deactivate()` (wird von
   sowohl `accept()` als auch `reject()` aufgerufen) ruft jetzt unbedingt
   `assembly.ViewObject.clearIsolate()` auf - sicherer No-Op, wenn ohnehin
   keine Isolation aktiv war. Nebenbefund beim Live-Test: `clearIsolate()`
   ändert Visibility/Selectable mehrerer Objekte synchron beim Schließen des
   Dialogs - ohne expliziten Redraw blieben die betroffenen Bauteile in der
   3D-Ansicht bis zur nächsten Mausbewegung unsichtbar (Coin3D zeichnet erst
   beim nächsten Event neu). Zusätzlich `Gui.updateGui()` danach aufgerufen -
   gleiches Muster bereits in `CommandCreateSimulation.py` verwendet.

6. **Bauteile springen kurz auf Placement (0,0,0)** (2026-08-09, direkt beim
   Live-Test von Fix 5 aufgefallen): der erste Versuch, `Gui.updateGui()`
   direkt nach `clearIsolate()` in `deactivate()` aufzurufen, saß an der
   falschen Stelle - `deactivate()` läuft in `accept()`/`reject()` **vor**
   der eigentlichen Commit-/Recompute-Sequenz
   (`generatePropertySettings()`/`Gui.doCommand()`/`recompute()` in
   `accept()`, `abortCommand()`/`recompute()` in `reject()`). Das sofortige
   Durchpumpen der Qt-Eventqueue an dieser frühen Stelle löste einen
   verfrühten Redraw/Recompute mit dem noch nicht fertig committeten
   Joint-Zwischenzustand aus - sichtbar als kurzes Zurückspringen der
   Bauteile auf Placement (0,0,0), bei "Abbrechen" betraf es alle Bauteile.
   Fix: `Gui.updateGui()` aus `deactivate()` entfernt, stattdessen ganz am
   Ende von `accept()` (nach `commitCommand()`) und `reject()` (nach dem
   finalen `recompute()`) aufgerufen - erst wenn der Joint-Zustand
   vollständig fertig ist.

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
