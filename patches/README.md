# FreeCAD-Core-Patches

Diese Patches beheben Bugs in der lokal gebauten FreeCAD-Installation
(`/home/maxx/freecad/freecad-source`, `/home/maxx/freecad/install`), die beim
Arbeiten mit FCProject aufgefallen sind. Sie gehören nicht zu FCProject selbst,
sondern zu FreeCAD - werden hier nur abgelegt, damit sie nach einem `git pull`,
`git stash` oder einer Neuinstallation von FreeCAD nicht verloren gehen.

## Periodisches Update (`update-and-rebuild-freecad.sh`)

Zieht die neuesten Commits von `github.com/FreeCAD/FreeCAD` (main), wendet
alle Patches aus diesem Ordner in der richtigen Reihenfolge neu an, baut neu
und installiert - automatisiert genau den Ablauf, der weiter unten unter
"Anwenden" beschrieben ist, plus `git pull`. Bricht bei jedem unerwarteten
Zustand (unbekannte lokale Änderungen, Patch passt nicht mehr, Build
scheitert) sofort ab, statt etwas stillschweigend zu überschreiben oder zu
ignorieren.

```bash
./patches/update-and-rebuild-freecad.sh            # echt ausführen
./patches/update-and-rebuild-freecad.sh --dry-run   # nur anzeigen, was passieren würde
```

Nutzt dafür den CMake-Preset `FC-dev` aus
`freecad-source/CMakeUserPresets.json` (zeigt bewusst auf den bestehenden
`build/`-Ordner, von dem FCProjects `CMakeLists.txt` selbst abhängt - nicht
auf `build/debug`/`build/release` wie FreeCADs eigene Standard-Presets, die
sonst einen zweiten, abweichenden Build-Baum anlegen würden). Derselbe
Preset funktioniert auch in VS Codes CMake-Tools-Panel, falls dort statt per
Skript gebaut werden soll - beide arbeiten dann auf demselben Stand.

Logs landen unter `patches/update-logs/` (git-ignoriert).

`freecad-CMakeUserPresets.json` ist eine reine Sicherungskopie von
`freecad-source/CMakeUserPresets.json` - die Datei ist von FreeCADs eigenem
`.gitignore` ausgeschlossen (Standard-CMake-Konvention, "lokal, nicht fürs
Repo gedacht") und würde sonst genauso unbemerkt verlorengehen wie die
Umgebungs-Patches vorhin. Das Skript stellt sie bei Bedarf automatisch
wieder her.

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

7. **Slider-Ketten kollabieren beim ersten Recompute nach dem Laden**
   (2026-08-10, `Joint.matchJCS()`): eine Baugruppe mit mehreren Panels, über
   Gleitverbindungen (Slider) kettenartig verbunden (PDM-Standardfall: jedes
   Panel = eigenes `.FCStd`, per `App::Link` eingebunden, typischerweise mit
   individuellen, zuvor interaktiv gezogenen Y-Positionen), verlor beim ersten
   `recompute()` nach dem Öffnen der Datei alle individuellen Positionen -
   jedes Panel sprang auf die Position des geerdeten ersten Panels der Kette.
   Ursache: beim ersten Recompute hat `AssemblyObject::solve()` (C++,
   `jointParts()`) noch keinen einzigen Joint beim mbD-Solver registriert. In
   der parallel laufenden normalen Dokument-Rekompute-Kaskade wertet aber
   jeder Slider-Joint seine per `ExpressionEngine` gebundene `Offset2`-
   Property neu aus, was `onChanged(joint, "Offset2")` auslöst - und weil
   `"Slider"` in `JointUsingPreSolve` steht, ruft das `preSolve()`/
   `matchJCS()` auf. `matchJCS()` fragt `assembly.isPartConnected()` ab; da
   der Solver den Joint noch nirgends als "verbunden" führt, wird das zweite
   Panel als frei behandelt und per **vollem 6-DOF-Snap** exakt auf das
   Koordinatensystem des ersten Panels gelegt - inklusive der Schiebeachse,
   die bei einem Slider aber gerade *frei* bleiben muss (das ist die einzige
   erlaubte Bewegungsrichtung des Joints). Der Fehler pflanzt sich Joint für
   Joint die ganze Kette entlang fort. Diagnostiziert per echter
   C++-Instrumentierung im selbstgebauten FreeCAD (Base::Console-Checkpoints
   in `AssemblyObject.cpp`/`OndselSolver`, zurückverfolgt bis vor
   `AssemblyObject::execute()`) plus einer zweiten, tieferen Fable-Recherche,
   die den exakten Python-Mechanismus in `matchJCS()` fand - der Ondsel-Solver
   selbst (Newton-Raphson) ist nachweislich unschuldig, er bekommt nur schon
   ein kaputtes Ausgangsmodell.
   Fix: für `JointType == "Slider"` wird `transform_plc` nicht mehr aus der
   vollen JCS-Differenz berechnet, sondern nur aus Rotation + den beiden
   Achsen senkrecht zur lokalen Z-Achse (der Schiebeachse) - die
   Z-Komponente (aktueller Schiebe-Versatz) bleibt unangetastet erhalten,
   statt auf 0 relativ zum fixierten Teil gezwungen zu werden. Betrifft nur
   den Slider-Zweig; alle anderen Joint-Typen verhalten sich unverändert.
   Live gegen den selbstgebauten FreeCAD 26.3 getestet mit dem 7-Panel-Repro
   aus `patches/bugreport-ensureIdentityPlacements/standalone_repro/` -
   alle Y-Positionen bleiben nach `recompute(True)` erhalten.
   (Cylindrical hat dieselbe freie Z-Translation und ist vom selben
   Mechanismus vermutlich ebenfalls betroffen, wurde aber bewusst NICHT
   mitgefixt - kein bestätigter Repro-Fall dafür, Scope absichtlich auf
   Slider beschränkt.)

8. **Diagnose-Meldung bei kaputter Joint-Referenz nennt keinen eindeutigen
   Namen** (2026-08-14, `getContext()`): beim Öffnen eines Assembly-Dokuments
   migrieren `migrationScript4`/`migrationScript2` alte/kaputte Joint-Referenzen
   und protokollieren Fehlschläge über die Konsole, z.B.
   `Assembly joint 'Baugruppe.Abstand' has an invalid 'Reference2' or related
   attributes. 'NoneType' object is not subscriptable`. `getContext()` baute den
   Objekt-Pfad in der Meldung bisher aus `Label` statt `Name` - das hilft aber
   nicht beim Wiederfinden, weil FreeCADs Standard-Label für JEDEN so erzeugten
   Distance-Joint identisch "Abstand" lautet (analog "Winkel", "Koinzident" etc.
   bei anderen Typen) - bei mehreren kaputten Joints in derselben Baugruppe war
   so nicht unterscheidbar, welcher gemeint ist (siehe Fix 9 - der eigentliche
   Grund für die kaputte Referenz war ein separater Bug, keine unvollständige
   Erstellung). Fix: `getContext()` nutzt jetzt durchgehend `Object.Name` (immer
   eindeutig, z.B. `Joint013`) statt `Label` - direkt per
   `App.ActiveDocument.getObject("Joint013")` wiederfindbar. Betrifft nur die
   beiden Diagnose-Meldungen in `migrationScript2`/`migrationScript4` (einzige
   Aufrufer von `getContext()`), keine Funktionsänderung an der eigentlichen
   Migration/Joint-Logik.

9. **Joint-Referenzen gehen durch bloßen Klick daneben verloren**
   (2026-08-14, `TaskAssemblyCreateJoint.clearSelection()`): beim Bearbeiten
   eines bestehenden Joints lädt `updateTaskboxFromJoint()` dessen 2 gespeicherte
   Referenzen in `self.refs` und markiert sie in der 3D-Ansicht als Auswahl.
   Solange der Dialog offen ist, lauscht ein Selection-Observer auf jeden
   Auswahl-Wechsel; `clearSelection()` wird von `Gui.Selection` bei JEDEM Leeren
   der globalen Auswahl aufgerufen - unabhängig vom Grund (Klick auf leeren Raum
   in der 3D-Ansicht, ein anderes Tree-Element ausgewählt, ...). Der Handler
   leerte bisher bedingungslos `self.refs` und rief darüber `updateJoint()` ->
   `setJointConnectors()` auf, was sofort - noch vor OK/Accept, lautlos, ohne
   Bestätigung - `Reference1`/`Reference2` auf `None` schrieb. Ein einziger,
   völlig harmlos wirkender Klick neben ein bereits vollständiges Teil beim
   bloßen Betrachten eines Joints zerstörte ihn also permanent, sobald das
   Dokument danach gespeichert wurde. Nutzer-Repro: mehrere zuvor intakte
   "Abstand"-Joints (`Reference1`/`Reference2` beide gültig gesetzt) hatten nach
   einer Bearbeitungssitzung plötzlich beide Referenzen auf `None` - reproduziert
   durch Vergleich des Dokumentzustands vor/nach der Sitzung
   (`Reference1`/`Reference2` direkt per Skript ausgelesen). Fix: ein bereits
   vollständiger Pick (>= 2 Referenzen) wird nicht mehr durch ein bloßes Leeren
   der globalen Auswahl verworfen - einzelne Referenzen lassen sich weiterhin
   gezielt durch erneutes Anklicken abwählen (`removeSelection()`), nur das
   komplette, unbeabsichtigte Leeren eines bereits fertigen Joints wird jetzt
   ignoriert. Noch nicht live in der GUI nachgetestet (nur durch Code-Analyse
   verifiziert plus Vorher/Nachher-Vergleich der echten Projektdatei) - bitte
   beim nächsten Bearbeiten eines Joints gegenprüfen.

### Anwenden

Nach einem frischen Checkout/Build von FreeCAD:

```bash
cd /home/maxx/freecad/freecad-source
git apply /home/maxx/Dokumente/FreeCAD-Development/FCProject/patches/freecad-assembly-jointobject.patch
cp src/Mod/Assembly/JointObject.py /home/maxx/freecad/install/Mod/Assembly/JointObject.py
```

(Reines Python, kein Rebuild von FreeCADGui nötig - Kopieren in `install/`
reicht für sofortige Wirkung.)

## freecad-assembly-link-delete-hang.patch

Betrifft `src/Mod/Assembly/App/AssemblyLink.{cpp,h}`. FreeCAD hängt sich
(100% CPU auf dem Hauptthread, keine weitere Report-View-Ausgabe) beim
Löschen eines Bauteils auf, das Teil einer mehrfach verlinkten
Unterbaugruppe ist (`Assembly::AssemblyLink`) - reproduziert 2026-08-16
("loeschfehler"-Bugreport, siehe unten).

Ursache: `AssemblyLink::synchronizeComponents()` legt fehlende Spiegel-
Objekte über `doc->addObject(...)` an, was synchron `onChanged(&Group)` ->
`updateContents()` auf sich selbst UND (über `getInList()`) auf jede
andere `AssemblyLink`-Instanz auslöst, die auf diese verweist - die
Kaskade kann also zwischen mehreren Instanzen hin- und herspringen, nicht
nur in sich selbst rekursieren. Wird eine Komponente der Quell-Baugruppe
gerade gelöscht, während eine `AssemblyLink`-Instanz sie noch spiegelt,
findet `synchronizeComponents()` nie ein stabiles Match und legt bei
jedem Wiedereintritt einen neuen Spiegel-Versuch an - endlos.

Fix: `static bool updatingContents`-Wiedereintritts-Sperre (geteilt über
alle Instanzen, siehe Kommentar im Header) um `updateContents()`.
Verschachtelte Aufrufe werden zum No-Op; der äußerste Aufruf läuft normal
durch, ein eventuell übersprungener Sync holt sich der nächste reguläre
`execute()`/Recompute nach.

Vollständiger Stacktrace + Analyse: `patches/bugreport-loeschfehler/README.md`.

### Anwenden

```bash
cd /home/maxx/freecad/freecad-source
git apply /home/maxx/Dokumente/FreeCAD-Development/FCProject/patches/freecad-assembly-link-delete-hang.patch
cmake --build build --target Assembly -- -j$(nproc)
cp build/Mod/Assembly/AssemblyApp.so /home/maxx/freecad/install/lib/AssemblyApp.so
```

(C++, betrifft `AssemblyApp.so` - Rebuild des `Assembly`-Targets nötig,
reines Kopieren wie bei den Python-Patches reicht hier nicht.)

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
git apply /home/maxx/Dokumente/FreeCAD-Development/FCProject/patches/freecad-assembly-jointobject.patch
git apply /home/maxx/Dokumente/FreeCAD-Development/FCProject/patches/freecad-assembly-link-delete-hang.patch
git apply /home/maxx/Dokumente/FreeCAD-Development/FCProject/patches/freecad-cmake-disable-tests.patch
git apply /home/maxx/Dokumente/FreeCAD-Development/FCProject/patches/freecad-navigation-qbytearray-fix.patch
git apply /home/maxx/Dokumente/FreeCAD-Development/FCProject/patches/freecad-propertyeditor-qstring-fix.patch
cp src/Mod/Assembly/JointObject.py /home/maxx/freecad/install/Mod/Assembly/JointObject.py
cmake --build build --target Assembly -- -j$(nproc)
cp build/Mod/Assembly/AssemblyApp.so /home/maxx/freecad/install/lib/AssemblyApp.so
```
