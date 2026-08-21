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

10. **Redundant-Constraint-Warnung nennt keinen eindeutigen/auffindbaren Namen**
    (2026-08-17, `AssemblyObject::isMbDJointValid()`): beim Ziehen eines Teils
    bündelt der Solver fest verbundene Teile; ist ein Joint dabei
    selbstreferenzierend (beide Enden landen im selben MbD-Teil), wird er
    ignoriert und über die Konsole protokolliert, z.B.
    `Assembly: Ignoring joint (Projekt.FCStd#Parallel) because its parts are
    connected by a fixed joint bundle. This joint is a conflicting or
    redundant constraint.` Die Meldung baute sich bisher aus `getFullLabel()`
    (`Dokument#Label`) - genau dasselbe Problem wie Fix 8, nur in der
    C++-Seite statt in `JointObject.py`: FreeCADs Standard-Label ist für
    JEDEN gleichartigen Joint identisch (z.B. "Parallel" für jeden
    Parallel-Joint), bei mehreren betroffenen Joints in derselben Baugruppe
    war so nicht erkennbar, welcher gemeint ist. Erster Versuch:
    `getFullName()` (`Dokument#Name`, z.B. `...#Joint005`) - zwar eindeutig,
    aber bei verschachtelten Baugruppen (PDM-Standardfall: jede
    Unterbaugruppe hat ihre EIGENE, lokal bei 0 beginnende Joint-
    Nummerierung) trotzdem nicht auffindbar, ohne jede Unterbaugruppe
    einzeln nach dem passenden Namen zu durchsuchen - `Joint005` allein
    verrät nicht, dass er z.B. in `Halterbaugruppe` sitzt statt im
    Top-Level der Baugruppe. Endgültiger Fix: neue freie Funktion
    `getJointContextName()` (Äquivalent zu `getContext()` aus Fix 8, aber in
    C++) baut den vollen Pfad über die Eltern-Kette (`InList`, jeweils
    erster Eintrag) auf, z.B. `Projekt.FCStd#Halterbaugruppe.Joint005` -
    zeigt direkt, in welcher (ggf. mehrfach verschachtelten) Unterbaugruppe
    der Joint sitzt.

11. **`AssemblyObject::solve()` meldet praktisch nichts über die Konsole**
    (2026-08-18, in `assembly-solver-sandbox` entwickelt, siehe dortige
    `SANDBOX_NOTES.md`): weder ein erfolgreicher Solve noch ein mangels
    geerdetem Teil komplett übersprungener Solve
    (`groundedObjs.empty() -> return -6`) gaben bisher irgendeine
    Konsolen-Ausgabe - nur echte Exceptions (`catch`-Blöcke) wurden
    gemeldet. Im PDM-Alltag mit vielen verschachtelten Baugruppen blieb
    dadurch oft unklar, ob/wann der Solver überhaupt gelaufen ist und was
    er dabei festgestellt hat (z.B. redundante Joints, siehe Fix 10) - vor
    allem beim stillen Fehlschlagen aus Nutzersicht ("Solver muckt
    überhaupt nicht", Nutzer-Zitat). Fix: drei neue `Base::Console()`-Meldungen
    in `solve()`:
    - `Assembly: Solving '<Name>'...` beim Start,
    - `Assembly: Solve of '<Name>' skipped - no grounded part found.` als
      Warnung, falls gar nicht gerechnet werden konnte,
    - `Assembly: '<Name>' computed (N joint(s), M grounded part(s): <Namen>).`
      nach erfolgreicher MbD-Berechnung (Namen der geerdeten Teile seit
      Fix 13),
    - abschließend entweder `Assembly: Solve of '<Name>' finished
      successfully.` oder (als Warnung, mit Namen über `getJointContextName()`
      aus Fix 10) `Assembly: Solve of '<Name>' finished with N redundant
      joint(s): <Namen>.`.

    Einzige Codeänderung in diesem Patch, die `AssemblyObject.cpp` statt
    `JointObject.py` betrifft - braucht deshalb (anders als Fix 1-9) einen
    Rebuild des `Assembly`-Targets, siehe "Anwenden" unten.

12. **"Baugruppe lösen" (Z) tut manchmal buchstäblich gar nichts**
    (2026-08-18, `CommandSolveAssembly.Activated()`, per Zusatz-Logging in
    `assembly-solver-sandbox` live diagnostiziert): der Befehl rief bisher
    nur `assembly.recompute(True)` auf. `DocumentObject.recompute()`
    überspringt aber `execute()` (und damit den darin aufgerufenen `solve()`,
    siehe Fix 11), wenn das Objekt nicht bereits als "touched" markiert ist -
    das `True`-Argument bedeutet nur "rekursiv in Abhängigkeiten", nicht
    "erzwinge trotzdem". War die Baugruppe gerade nicht touched (z.B. direkt
    nach einem vorherigen erfolgreichen Solve), lief `recompute(True)` ohne
    jeden Fehler durch, löste aber **keinen** tatsächlichen Solve aus - im
    Gegensatz zum Ziehen eines Teils (`preDrag()`), das `solve()` immer
    direkt aufruft. Nutzer-Symptom: "beim Drücken Z passiert nichts" +
    "Regenerieren der Baugruppe und Bewegen eines Teils bringen zwei
    unterschiedliche Ergebnisse" - beides dieselbe Ursache. Fix:
    `assembly.touch()` vor `recompute(True)`, erzwingt zuverlässig einen
    echten `execute()`-Lauf, ohne `execute()`s sonstiges Verhalten
    (`Part::execute()`, Signal-Emissionen etc.) durch einen direkten
    `solve()`-Aufruf zu umgehen. Reines Python (`CommandSolveAssembly.py`),
    kein Rebuild nötig - nur Kopieren wie bei Fix 1-9.

13. **Solver-Meldungen aus Fix 11 nannten nur Anzahlen, keine Namen**
    (2026-08-19, Nutzerwunsch: "Ausgabe in Solver vervollständigen wo der
    soll Namen für Grounded parts ausgeben, bzw. Teilnehmer Rigid Group"):
    `computed (N joint(s), M grounded part(s))` sagte nicht, WELCHE Teile
    das waren - gerade bei "M grounded part(s)" verwirrend, weil
    `getGroundedParts()` das `Origin`-Objekt IMMER automatisch mitzählt,
    auch ganz ohne eigenen `GroundedJoint` (siehe
    [[project_fcproject_redundant_fixed_joint_rigidgroup_fix]] fürs
    verwandte Redundanz-Thema). Fix: `computed(...)`-Meldung nennt jetzt die
    Namen aller geerdeten Teile (über `getJointContextName()` aus Fix 10,
    für Konsistenz bei verschachtelten Baugruppen); zusätzlich eine neue
    Meldung pro aktiver Rigid Group (`rebuildRigidClusters()`/
    `rigidMembersByRep`, siehe RigidGroup-Feature) mit deren Mitgliedern:
    `Assembly: rigid group '<Name>' (N Teil(e)): <Namen>.`. Dafür
    `getJointContextName()` (und die zwei neuen `joinContextNames()`-
    Overloads für `vector`/`unordered_set`) im anonymen Namespace vor
    `solve()` statt erst vor `isMbDJointValid()` platziert, da jetzt von
    beiden Stellen gebraucht. Wie Fix 10/11 in `AssemblyObject.cpp` -
    braucht einen Rebuild des `Assembly`-Targets.

14. **"1 grounded part(s)" mit leerer Namensliste direkt nach dem Laden**
    (2026-08-19, sofort beim Live-Test von Fix 13 aufgefallen):
    `getGroundedParts()` steckte `Origin.getValue()` bisher ungeprüft in
    `groundedSet` - direkt beim Öffnen einer Datei (bevor der
    Assembly-`Origin` initialisiert ist, siehe auch
    [[project_fcproject_freecadcmd_zero_joints_cold_load]] fürs verwandte
    "0 joint(s)"-Symptom auf demselben frühen Ladepfad) ist das `nullptr`
    und zählte trotzdem als "1 Teil" mit - fiel erst durch Fix 13 auf, weil
    die Namensausgabe den Nullpointer korrekt überspringt, die Anzahl davon
    aber unberührt blieb (Diskrepanz Zahl vs. Namen). Fix: `Origin.getValue()`
    nur einfügen, wenn tatsächlich gesetzt. Wie Fix 13 in `AssemblyObject.cpp`.

15. **Geerdete Teile in einer eigenen Zeile statt komma-getrennt**
    (2026-08-19, Nutzerwunsch: "jede grounded Part auch eine neue Zeile"):
    die `computed(...)`-Meldung aus Fix 13 listete alle geerdeten Teile
    komma-getrennt in einer einzigen, bei vielen Teilen unhandlich langen
    Zeile. Jetzt eine Kopfzeile mit den Anzahlen, gefolgt von je einer
    `Assembly:   grounded part: <Name>`-Zeile pro Teil. Die Rigid-Group-
    Mitgliederliste bleibt bewusst komma-getrennt in einer Zeile (typischerweise
    deutlich kürzer, eine Gruppe pro Meldung). Wie Fix 13/14 in
    `AssemblyObject.cpp`.

**Hinweis (2026-08-18, `update-and-rebuild-freecad.sh`-Lauf):** Upstream hat
mit "Assembly: Add RigidGroup (#29605)" (11. Aug 2026) `AssemblyObject.cpp`
strukturell verändert (neue `rebuildRigidClusters()`/
`syncActiveRigidGroupPlacements()`/`updateRigidPlacementCache()`-Aufrufe in
`solve()`) - der `.cpp`-Hunk dieses Patches passte danach nicht mehr
(`JointObject.py` und `CommandSolveAssembly.py` waren unberührt und passten
weiter). Von Hand an die neue `solve()`-Struktur nachgezogen und den Patch
neu generiert; inhaltlich unverändert (gleiche drei Meldungen, gleiches
`getJointContextName()`). Dabei außerdem einen Bug im Skript selbst
gefunden: `AssemblyObject.cpp` und `CommandSolveAssembly.py` fehlten in
dessen `FEATURE_PATCHED_FILES`-Liste, wodurch Schritt 1 sie nicht
zurücksetzte (Ursache des "unerwartete lokale Aenderungen"-Abbruchs an
diesem Tag) und Schritt 7 `CommandSolveAssembly.py` nie nach `install/`
kopierte - beides in `update-and-rebuild-freecad.sh` behoben.

### Anwenden

Nach einem frischen Checkout/Build von FreeCAD:

```bash
cd /home/maxx/freecad/freecad-source
git apply /home/maxx/Dokumente/FreeCAD-Development/FCProject/patches/freecad-assembly-jointobject.patch
cp src/Mod/Assembly/JointObject.py /home/maxx/freecad/install/Mod/Assembly/JointObject.py
cp src/Mod/Assembly/CommandSolveAssembly.py /home/maxx/freecad/install/Mod/Assembly/CommandSolveAssembly.py
cmake --build build --target Assembly -- -j$(nproc)
cp build/Mod/Assembly/AssemblyApp.so /home/maxx/freecad/install/lib/AssemblyApp.so
```

(Fix 1-9 und 12 sind reines Python, würden allein durch das Kopieren in `install/`
sofort wirken - seit Fix 10 steckt aber auch eine `.cpp`-Änderung in diesem
Patch, daher jetzt immer beides: kopieren UND das `Assembly`-Target neu
bauen.)

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

### 2. Fix - Joint-Referenz in doppelt verschachtelte flexible Unterbaugruppe

(2026-08-19, siehe `patches/bugreport-rigid-nested-joint-reference/README.md` für die
volle Analyse + synthetisches Minimal-Repro `repro.py`.) Bindet eine Baugruppe eine
verschachtelte Unterbaugruppe als **flexibel** (`Rigid=False`) ein und referenziert ein
Joint darin ein Teil *innerhalb* dieser Unterbaugruppe (ein "Enkelkind" aus Sicht der
äußeren Baugruppe), bleibt die gespiegelte Referenz beim erneuten Einbinden in eine
weitere, übergeordnete Baugruppe auf der externen Quelldatei hängen statt auf die
lokale Kopie umgebogen zu werden - die betroffenen Teile erscheinen dann in der
äußersten Baugruppe komplett unverbunden. Bei `Rigid=True` (identische Verschachtelung)
tritt das nicht auf, da `UtilsAssembly.getComponentReference()` die Referenz dort schon
beim Joint-Anlegen kompakt (auf die direkte Unterbaugruppe) statt flach (direkt aufs
Enkelkind) kodiert.

Ursache: `AssemblyLink::handleJointReference()`s `objLinkMap`-Lookup kennt nur direkte
Kinder der gespiegelten Baugruppe, keine Enkelkinder. Fix: neue Methode
`findLocalAncestor()` läuft bei einem gescheiterten direkten Lookup die
Struktur-Eltern-Kette hoch (über die `Group`-Property der `getInList()`-Kandidaten, nicht
blind `getInList().front()` - das kann auch Joints statt des echten Containers liefern),
bis ein in `objLinkMap` bekannter Vorfahre gefunden wird, und liefert den durchlaufenen
Pfad als `Sub`-Präfix zurück - exakt das Gegenstück zu `getComponentReference()`s eigener
Kodierung. Am 2026-08-19 in einer realen, dreifach verschachtelten Baugruppe
(Gesamtbaugruppe → FuehrungsBaugruppe400 → Halterbaugruppe, alle live vom Nutzer
getestet, nicht nur synthetisch) verifiziert: Referenzen sind nach dem Fix lokal, Solve
läuft fehlerfrei durch, Teile bewegen sich korrekt mit.

**Vorsicht bei Weiterentwicklung:** ein erster Versuch, denselben `objLinkMap`-Mechanismus
auch für das neue RigidGroup-Feature zu erweitern (Mitglieder einer Rigid Group
umtragen), hat eine Regression verursacht (Teile fälschlich zur Löschung markiert, "out
of scope"-Validierung) - dieser Fix hier betrifft nur normale Joint-Referenzen
(`Reference1`/`Reference2`), nicht `ObjectsToRigidGroup`. Siehe
`patches/bugreport-rigid-nested-joint-reference/README.md` für Details.

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

## freecad-filedialog-search-filter.patch

Betrifft `src/Gui/FileDialog.{cpp,h}` (`Gui::FileDialog`, der nicht-native
Öffnen/Speichern-Dialog - wird von FCProject bewusst erzwungen, siehe
`DontUseNativeDialog` in `resources/run-freecad-26.3.sh`, wegen eines
lautlosen Hangs im nativen Dialog auf dieser Maschine).

**Problem** (2026-08-21, Nutzer-Repro): das Feld "Dateiname" validiert bei
jedem Tastendruck den eingegebenen Text als konkreten, existierenden
Dateinamen (Qt-eigenes Verhalten) - eine Wildcard-Maske wie `*Tr*` oder
`*.csv` zum Filtern der Liste eintippen löst darüber nur die Fehlermeldung
"Die Datei konnte nicht gefunden werden" aus, statt zu filtern. Es gibt in
diesem Dialog keine funktionierende Möglichkeit, die Dateiliste nach Namen
zu durchsuchen/filtern.

**Fix:** neues Suchfeld ("Search:") wird als letzte Zeile in den
bestehenden `QGridLayout` des Dialogs eingefügt (unterhalb der
OK/Abbrechen-Buttons - bewusst keine Positionierung *über* den Buttons
versucht, siehe Live-Test-Erkenntnisse unten). Live-Filterung über
`FileDialog::onSearchTextChanged()`, verbunden auf `QLineEdit::textChanged`
statt auf Enter, per `QFileDialog::setNameFilter()` - demselben,
voll unterstützten Mechanismus, den auch das "Dateien des Typs"-Dropdown
selbst benutzt:
- reiner Text ohne `*`/`?` wird automatisch als Teilstring-Suche behandelt
  (`text` -> `*text*`),
- ein Muster mit `*`/`?` wird direkt als Wildcard verwendet (z.B.
  `BOM*.csv`),
- Ordner bleiben immer sichtbar, ganz ohne Zusatzaufwand - Name-Filter
  in `QFileDialog` greifen laut Qt-Doku ohnehin nur auf Dateien, nie auf
  Verzeichnisse,
- beim Leeren des Suchfelds wird der vorherige Filterzustand
  (`nameFilters()`/`selectedNameFilter()`, in `setupSearchFilter()`
  gemerkt) wiederhergestellt.

Betrifft nur den nicht-nativen Dialog (`layout()` liefert dort ein
`QGridLayout*`; beim nativen OS-Dialog bleibt es ein No-Op) - erzwungen
per `DontUseNativeDialog=1`, siehe `resources/run-freecad-26.3.sh`.

**Live-Test-Erkenntnisse vom 2026-08-21** (per Diagnose-Logging in
`setupSearchFilter()` gefunden, siehe `Base::Console().log(...)`-Aufrufe im
Code):
1. Erster Versuch positionierte das Suchfeld *über* den Buttons, indem die
   `QDialogButtonBox` per `grid->getItemPosition()` eine Zeile nach unten
   verschoben wurde - Feld blieb unsichtbar. Vermutete Ursache: die
   Button-Box teilt sich vermutlich eine Grid-Zeile mit anderen Widgets
   (z.B. "Dateiname"), wodurch das neu eingefügte Suchfeld eine bereits
   belegte Zelle überlagert hat. Fix: garantiert kollisionsfrei bei
   `grid->rowCount()` einfügen (erste sicher freie Zeile) - kostet nur die
   optisch etwas unübliche Position unterhalb der Buttons.
2. Selbst danach blieb das Feld unsichtbar, weil `layout()` direkt im
   Konstruktor noch `nullptr` liefert - Qt baut die interne
   Widget-Oberfläche des nicht-nativen Dialogs nachweislich erst verzögert
   beim tatsächlichen Anzeigen auf, nicht schon beim Konstruieren. Fix:
   `setupSearchFilter()` wird aus einem neuen `showEvent()`-Override
   aufgerufen statt aus dem Konstruktor (idempotent via
   `if (searchLineEdit) return;`, da `showEvent()` mehrfach feuern kann).
3. Erste funktionierende Fassung nutzte ein eigenes
   `FileDialogSearchProxyModel : QSortFilterProxyModel`, per
   `QFileDialog::setProxyModel()` eingehängt (mit `filterAcceptsRow()`, das
   Verzeichnisse immer durchwinkt). Feld und Filterung funktionierten,
   erzeugten aber bei jedem Dialogaufbau zweimal die Qt-Warnung
   `QSortFilterProxyModel: index from wrong model passed to mapToSource` -
   vermutlich, weil `setProxyModel()` mitten im bereits laufenden
   Initialisierungsablauf des Dialogs (in `showEvent()`, nach
   `setDirectory()` etc.) das Modell austauscht, während Qt intern noch
   `QModelIndex`-Zustand (Verlauf/aktuelle Auswahl) vom vorherigen
   Standard-Proxy referenziert. Endgültiger Fix: eigenes Proxy-Model
   komplett verworfen, stattdessen `setNameFilter()`/`setNameFilters()`
   direkt auf dem Dialog - Qts eigener, dafür vorgesehener Mechanismus,
   ohne Modellaustausch, ohne die Warnung.

Live gegen den selbstgebauten FreeCAD 26.3 getestet (Nutzer-Bestätigung
2026-08-21: Suchfeld erscheint, Filterung funktioniert, keine Warnung mehr
im Log) - inklusive der drei oben beschriebenen Fehlschläge, bevor der
finale Stand griff.

### Anwenden

```bash
cd /home/maxx/freecad/freecad-source
git apply /home/maxx/Dokumente/FreeCAD-Development/FCProject/patches/freecad-filedialog-search-filter.patch
cmake --build build --target FreeCADGui -- -j$(nproc)
cp build/lib/libFreeCADGui.so /home/maxx/freecad/install/lib/libFreeCADGui.so
```

(C++, betrifft `libFreeCADGui.so` - Rebuild des `FreeCADGui`-Targets nötig,
reines Kopieren wie bei den Python-Patches reicht hier nicht. Der Rebuild
zieht wegen des geänderten Headers viele abhängige `.cpp`-Dateien im
Gui-Modul mit - ca. 1-2 Minuten inkrementell.)

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
git apply /home/maxx/Dokumente/FreeCAD-Development/FCProject/patches/freecad-filedialog-search-filter.patch
cp src/Mod/Assembly/JointObject.py /home/maxx/freecad/install/Mod/Assembly/JointObject.py
cp src/Mod/Assembly/CommandSolveAssembly.py /home/maxx/freecad/install/Mod/Assembly/CommandSolveAssembly.py
cmake --build build --target Assembly -- -j$(nproc)
cp build/Mod/Assembly/AssemblyApp.so /home/maxx/freecad/install/lib/AssemblyApp.so
cmake --build build --target FreeCADGui -- -j$(nproc)
cp build/lib/libFreeCADGui.so /home/maxx/freecad/install/lib/libFreeCADGui.so
```
