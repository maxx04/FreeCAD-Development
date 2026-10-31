# Erkenntnisse aus der Assembly-Solver-Sandbox, die FCProject betreffen

Stand 2026-10-31. Übernommen aus dem Sandbox-Repo `assembly-solver-sandbox` (Branch
`solver-sandbox`, Doku dort: `docs/ARCHITECTURE.md`, `docs/CONSTRAINTS.md`). Hier steht nur, was
für die FCProject-Werkzeuge (PartExchange, Import-Komponente, BOM, DocObserver, Makros) und
ihre Tests direkt nutzbar ist.

## 1. Umgebung (seit 2026-10-31 ohne Dev)

- **FreeCAD Dev wurde am 2026-10-31 gelöscht**: `/home/maxx/freecad/freecad-source`,
  `/home/maxx/freecad/install`, `freecad-dev-profile`, `run-freecad-dev.sh`, Startmenü-Eintrag.
  Geblieben: `/home/maxx/freecad/App_weekly` (Vanilla) und die Logos.
- **FCProject ist seit 2026-10-31 auf die Sandbox umgestellt:**
  - Sandbox-Profil: `freecad-sandbox-profile/Mod/FreeCAD-Development` ist ein **Symlink auf dieses
    Repo** (vorher Git-Klon von GitHub). Änderungen wirken nach einem FreeCAD-Neustart, ohne
    install oder push.
  - `CMakeLists.txt`/`CMakePresets.json`: `FC_SOURCE_DIR`/`FC_LIB_DIR` zeigen auf
    `/home/maxx/freecad-sandbox/freecad-source` bzw. `/home/maxx/freecad-sandbox/install/lib`.
    Kein `FC_MOD_DIR`-Fallback mehr; `install` tut nur etwas, wenn `FC_MOD_DIR` gesetzt ist.
    `FCProjectCore.so` benutzt der Python-Code nicht mehr (BOM rein in Python).
  - `.vscode`: Python-Pfade und Debug-Start auf die Sandbox.
  - `patches/update-and-rebuild-freecad.sh` ist stillgelegt; Startskript und Desktop-Eintrag für
    Dev sind entfernt.
  - Vanilla lädt FCProject weiter als Git-Klon (`git pull` nach dem Push).
- **Vanilla** = `/home/maxx/freecad/App_weekly/freecad.App` (Weekly-AppImage), Profil
  `App_weekly/freecad-weekly-profile`.
- **Sandbox** = `/home/maxx/freecad-sandbox/install`, Start
  `/home/maxx/freecad-sandbox/run-freecad-sandbox.sh`, Profil
  `/home/maxx/freecad-sandbox/freecad-sandbox-profile`, Logs `/home/maxx/freecad-sandbox/logs`.
  Die 4 Makros aus dem alten Dev-Profil liegen jetzt in `freecad-sandbox-profile/Macro`.
- **Qt6/PySide6** der Sandbox kommt aus einer eigenen, entpackten KDE-Neon-Umgebung
  (`/home/maxx/Dokumente/FreeCAD-Development/neon-qt6-pyside6/root`), ohne Systemeingriff. Ein
  cmake-Reconfigure braucht `LD_LIBRARY_PATH=.../root/usr/lib/x86_64-linux-gnu`.

## 2. Testen ohne GUI-Klicks (Xvfb)

- Sandbox-Testrahmen: `assembly-solver-sandbox/standalone-check/kinematic-tests/common/run-test.sh
  <install-Ordner|AppImage> <skript.py>` startet FreeCAD **mit GUI** unter Xvfb, eigenes
  Testprofil, `--log-file`. Funktioniert auch für Skripte außerhalb des Repos (so laufen die
  MotionProfiles-Addon-Tests).
- **Nie die Konsolenausgabe auswerten, immer die Logdatei**: `print()` eines GUI-Prozesses landet
  über die Report-View-Umleitung, nicht verlässlich auf stdout.
- **Keine zwei `run-test.sh` parallel**: beide benutzen dasselbe Xvfb-Display, Tests schlagen
  dann zufällig fehl.
- Vorgehen bei Bugs: erst analytisch, dann in Vanilla nachstellen, dann gepatcht. Vor jeder
  Aussage „auch in Vanilla“ gegen die Weekly-AppImage prüfen.
- Testdateien: feste, git-getrackte Ausgangs-`.FCStd` (Fixturen), der Test arbeitet nur auf
  einer Kopie. Echte Projekte (PROJ_CNC3018) nur als Kopie in einem temporären Ordner öffnen.

## 3. Joints per Skript anlegen

- **Sub-Element doppelt:** `joint.Reference1 = (obj, ["Face1", "Face1"])`, nicht `["Face1"]`.
  Sonst leerer Referenzbereich im Dialog und „invalid Reference … list index out of range“
  (`UtilsAssembly.isRefValid(ref, 2)`).
- **ViewProvider nicht vergessen:** `JointObject.ViewProviderJoint(joint.ViewObject)` wird nur
  vom Dialog gesetzt. Fehlt er, stürzt das Neuladen in `execute()` ab
  (`'int' object has no attribute 'redrawJointPlacements'`) und Doppelklick-Bearbeiten geht
  nicht. Auch in Vanilla so.
- **Detach1/Detach2 = True** friert `Placement1/2` ein: Drehen/Versatz im Dialog ändert dann nur
  `Offset2`, die Lage bleibt. Kein Bug, aber verwirrend beim Prüfen von Testdateien.
- Beim Skript-Aufbau `SolveInJointCreation`/`SolveOnRecompute` ausschalten, sonst löst und
  dreht FreeCAD schon beim Anlegen.

## 4. Referenzen durch PartDesign-Body (wichtig für PartExchange)

- Nach einem Teiletausch auf einen Body mit `BaseFeature` (importierte Geometrie) referenzieren
  Joints z.B. `Link` + `"BaseFeature.Edge9"`. Upstream-FreeCAD rechnet die Placement des
  BaseFeature dabei **doppelt** ein (`findPlacement()` relativ zum Link, `getGlobalPlacement()`
  läuft den ganzen Pfad) – Schraube stand 90° quer (BG75, 2026-10-13).
- In der Sandbox behoben (`AssemblyUtils::getJcsReferenceGlobalPlacement()`), in Vanilla nicht.
  Für PartExchange heißt das: Referenzen auf Body-Unterfeatures in Vanilla meiden bzw. nach dem
  Tausch die JCS-z-Achse gegen die Kantenachse prüfen, nicht nur „Joint erfüllt“.

## 5. Verschachtelte Baugruppen: Original vs. Spiegel

- **Originale nie verändern:** Eine eigenständige Quelldatei (Teil oder Unter-BG) behält ihre
  Placement (meist 0,0,0). Jede Link-Instanz in einer Eltern-BG hat ihre eigene Placement.
- **Der Sandbox-Solver schreibt nur Spiegel** (die Objekte im Dokument der aktiven BG), nie die
  Originale im Unterdokument. Werkzeuge, die Lagen lesen/setzen (PartExchange, Import), müssen
  den **Spiegel der aktiven BG** benutzen. Die GUI-Auswahl kann das rohe Quellobjekt liefern
  statt des Spiegels (siehe FCProject-Notiz „Selection: rohes Quellobjekt statt Mirror-Link“).
- **Mehrere Instanzen derselben Unter-BG:** FreeCAD benennt den zweiten Spiegelsatz um
  (`BoxB` → `BoxB001`). Zuordnung Spiegel ↔ Quelle **nur über Zeiger**
  (`AssemblyLink`-`objLinkMap`/`LinkedObject`), nie über Name oder Label.
- **Gelenk-Instanzen:** Ein Gelenk in einer Unter-BG existiert in der Eltern-BG je Einbau einmal,
  unterschieden durch den `nestingPrefix` (z.B. `CNC3018_037_A_TraegerBaugruppe_Z.`).
  Sandbox-API: `asm.getJointInstances()` → `[(joint, prefix)]`,
  `UtilsAssembly.getJointInstancesOfType(asm, ["Revolute", ...])`,
  `UtilsAssembly.jointInstanceDisplayName(joint, prefix)`; Motion-Verweis auf eine Instanz:
  `motion.Joint = (joint, [prefix])`. In Vanilla gibt es nur die Gelenke selbst
  (`getJointsOfType`).
- **Starr/Flexibel** legt nur das einbauende Dokument fest; tiefere Spiegel übernehmen es
  (Regel C1).
- **Erdung ist Kontext-Eigenschaft:** Jede BG braucht eine Erdung. Eingebaut und angebunden wird
  die interne Erdung der Unter-BG nur im Kontext deaktiviert, die Datei bleibt unverändert.
  Ein `GroundedJoint` wird dabei **nie gelöscht**, nur deaktiviert (ReadOnly). Eine lose
  eingefügte Unter-BG bleibt an ihrer Ablage-Position fest, bis zum ersten Gelenk zur restlichen
  BG (Regeln C3, C5, C6).
- **Grenzen** sind Konstruktionsvorgabe des Originals: Ändert sich das Original, wird die Lage
  der Instanz nicht nachgezogen, die Grenzen schon (sonst Warnung im Ausgabefenster).

## 6. Dateien und Verweise

- **.FCStd-Kompatibilität ist Pflicht:** keine neuen dauerhaft gespeicherten Properties ohne
  Rücksprache; eine Datei aus Vanilla, Sandbox oder App muss in den anderen ohne Fehler öffnen.
  Zusätzliche Properties eines Addons nur additiv, in eigener Gruppe (so macht es
  MotionProfiles).
- **DocObserver/Verweis-Umbiegen (2026-10-27, BG22 hing):** Der FCProject-Datei-Beobachter hatte
  in BG75 die Verweise vom aktuellen Motor `CNC3018_067_A_NEMA17x33.FCStd` auf die alte Kopie
  `CNC3018_067_A_SchrittMotor NEMA17x33 III.FCStd` umgebogen. Der Motor stand danach als zwei
  verschiedene Dokumente in BG22, der Solver hing in der Redundanzsuche. Ursache: Das
  Umbenennen per `saveAs` ließ die alte Datei liegen, nicht geöffnete Dateien verwiesen weiter
  darauf. **Seit 2026-10-31 behoben:** `DocObserver.rename_document_with_references()` stellt
  alle Verweise im Projektordner um (XLink-Einträge in `Document.xml`, absolute Pfade in
  Tabellenzellen) und macht die alte Datei zur `.FCBak`; Test `tests/fc_docobserver_rename_check.py`.
- **„Link broken“/„Exception opening file … [stoi]“/„Material not found“:** eine von FreeCAD
  selbst geschriebene Materialdatei im Profil (`Material/PET-Generic.FCMat`) hatte
  `UseObjectColor: ""` (leerer Bool). Wert `0` behebt es. Relevant für `MaterialUtils`/BOM.
- Insert-Component (Datei-Öffnen-Knopf) hat einmal einen echten SIGSEGV ausgelöst, nicht
  reproduziert.
- Beim Öffnen kann der erste Solve vor dem Ende des Ladens laufen („no grounded part found“).
  Die Sandbox löst beim Einlesen nicht mehr; in Vanilla hilft ein Recompute.

## 7. Solver-Verhalten, das man als Werkzeug-Autor kennen sollte

- **180°-Mehrdeutigkeit:** OndselSolver legt Fixed/Slider/Dreh-/Zylindergelenke in Vanilla nur
  über Richtungskosinusse fest; Newton landet auf der Lösung nahe der Startlage (auch 180° um y
  oder z). Ein Teil kann so „umgeklappt“ gespeichert werden. Sandbox: eindeutige Gelenke,
  Variante deckungsgleich/„umgekehrt“ wie `flipOnePart()`. Planar/Parallel noch offen.
  Kreiskanten haben einen festen Startpunkt – daraus entsteht keine Mehrdeutigkeit.
- **Gelenkgrenzen:** Vanilla prüft sie nur beim Ziehen. Sandbox auch beim Solve und in der
  Simulation (hält am Anschlag an, meldet Gelenk und Zeit).
- **Simulation:** Bilder liegen nur im Speicher (`asm.numberOfFrames()`,
  `asm.updateForFrame(k)`), Bild 0 = Ausgangslage, Bild k = Start + (k−1)·Schritt. Ein Solve
  verwirft sie. Motion-Formeln: `+ - * / ^`, `sin`, `cos`,
  `piecewise(time, functions(...), transitions(...))`; `spline(...)` lässt die Simulation
  scheitern.
- Bei Solver-Merkwürdigkeiten zuerst den eigenen Code verdächtigen, nicht OndselSolver.

## 8. Addon-Entwicklung (aus MotionProfiles)

- Knopf in fremde Werkbank-Symbolleiste: `Gui.addWorkbenchManipulator` mit
  `{"append": cmd, "toolBar": "Assembly"}` (`"toolItem"` funktionierte nicht).
- Matplotlib im Aufgabenfenster: Canvas-Unterklasse, die `RuntimeError` in `showEvent`/
  `_draw_idle` abfängt („Internal C++ object already deleted“ nach dem Schließen), und
  `wheelEvent` mit `event.ignore()`, sonst scrollt das Fenster über dem Diagramm nicht.
- Lange Rechnungen: FreeCAD-Sequencer (`Base::SequencerLauncher`) zeigt Fortschritt in der
  Statusleiste, Esc bricht ab, die Oberfläche bleibt bedienbar.
- Platzierungen vor einer Vorschau sichern/zurücksetzen:
  `UtilsAssembly.saveAssemblyPartsPlacements()` / `restoreAssemblyPartsPlacements()` (auch
  Vanilla).

## 9. Upstream

- FreeCAD-AI-Policy: Issue- und PR-Texte schreibt der Nutzer selbst; Claude liefert nur
  Faktenblätter. Zwei PRs wurden deswegen geschlossen (#33672/#33673).
- Im Sandbox-Repo ist `origin` FreeCAD-Upstream – dorthin nie pushen.
