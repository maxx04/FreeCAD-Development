# FreeCAD 26.3 Assembly Solver – mit Fokus auf den realen Source-Code

Dieser Artikel betrachtet den Assembly-Solver aus Sicht des tatsächlichen FreeCAD-Codes und nicht nur aus Sicht eines allgemeinen CAD-Modells. Dabei stehen die realen Klassen und Kernbereiche im Mittelpunkt:

- `src/Mod/Assembly/App/AssemblyObject.cpp`
- `src/Mod/Assembly/JointObject.py`
- `src/Mod/Assembly/App/AssemblyLink.*` (wo relevant)
- das zugrunde liegende `OndselSolver`-Subsystem

Das Ziel ist nicht, eine exakte Zeile-für-Zeile-Dokumentation der FreeCAD-Source-Basis zu liefern, sondern die Kernlogik verständlich zu machen: Wo wird ein Joint gespeichert, wie wird der Recompute ausgelöst, wie wird der Solver gestartet und wie entsteht daraus eine neue Festlegung von Placements und Zustandsvariablen.

## 1. Die reale Architektur im Überblick

Die Assembly-Mechanik ist in FreeCAD in mehrere Schichten unterteilt:

1. Dokument-/Objekt-Schicht
   - `AssemblyObject`
   - `JointObject`
   - `App::Link`
   - Referenz- und Document-Graph

2. Joint-/Constraint-Schicht
   - Typen wie `Distance`, `Revolute`, `Slider`, `Cylindrical`, `Fixed`
   - `Reference1`, `Reference2`
   - `Offset1`, `Offset2`, `Placement1`, `Placement2`
   - `onChanged` / `preSolve` / `matchJCS`

3. Numerische Solver-Schicht
   - Aufbau von Residuen
   - Berechnung des Jacobian
   - Newton-/Least-Squares-Schritt
   - `OndselSolver` als Backend

4. GUI-/View-Schicht
   - Qt/PySide6-Task-Dialoge
   - Joint-Auswahl und -Editor
   - `Gui.updateGui()` / `ViewObject.clearIsolate()`

Diese Schichten laufen nicht unabhängig, sondern bilden einen echten Datenfluss:

GUI -> JointObject -> AssemblyObject -> solve() -> OndselSolver -> Placement update -> GUI redraw

## 2. AssemblyObject: die zentrale Stelle des Solve-Flows

In FreeCAD ist `AssemblyObject` der zentrale Knoten einer Baugruppe. Es verwaltet nicht nur den Graphen von Teilen und Joints, sondern startet auch die eigentliche Lösung.

Aus Sicht der Architektur ist `AssemblyObject::solve()` der Kernpunkt. Dort wird typischerweise das folgende Muster durchlaufen:

- Joints aus dem Assembly-Graph holen
- Referenzen auflösen und prüfen
- gefundene Joint-Objekte als Constraints in den Solver-Graph eintragen
- Zustand des Systems aufbauen
- numerische Iteration starten
- neue Placements verarbeiten und zurückschreiben

In den Debug- und Patch-Untersuchungen dieses Projekts tauchen diese Namen mehrfach auf:

- `AssemblyObject::solve()`
- `jointParts()`
- `fixGroundedParts()`
- `findPlacement()`
- `matchJCS()`

Das ist die Stelle, an der der eigentliche Kinematik-Graph mit der solverbasierten Berechnung zusammenläuft.

### Grundsätzliche Logik von `solve()`

Die Struktur ist sehr typisch für CAD-Solver:

1. Hole aktuelle Topologie
2. Prüfe, welche Elemente verbunden sind
3. Erzeuge oder aktualisiere die Constraint-Graphen
4. Stelle den Zustandsvektor `Q` zusammen
5. Löse mit dem numerischen Backend
6. Schreibt neue Positionen / Rotationen zurück

Das ist nicht „nur ein Render-Refresh“, sondern eine echte System-Iteration.

## 3. JointObject: die Definition der Beziehung

`JointObject` (in der Python-Seite des Assembly-Workbench) ist die Sicht, die der Anwender und die GUI unmittelbar sehen. Es trägt die konkrete Beziehung zwischen zwei Objekten.

Typische Eigenschaften sind:

- `Type`
- `Reference1`
- `Reference2`
- `Placement1`
- `Placement2`
- `Offset1`, `Offset2`
- `Distance`, `Angle`, `Limit*`
- `State`

In den FreeCAD-Assembly-Patches dieses Projekts tauchen sehr viele dieser Felder auf, weil sie genau den realen Fehlerpfad illustrieren:

- kaputte Joint-Referenzen (`Reference1`/`Reference2` auf `None`)
- Falsche Verarbeitung beim Bearbeiten eines Joints im Dialog
- `clearIsolate()` beim Schließen des Dialogs
- `matchJCS()` bei Slider-Joints bei erstem Recompute

Das zeigt einen wichtigen Punkt:

Der Joint ist nicht nur ein „Symbol“ im Baum. Er ist ein aktiver Zustand, der im Lauf des Solves gelesen, bewertet und verändert wird.

## 4. Der echte Datenfluss: von der GUI bis zum Solver

### 4.1 Python-GUI-Schicht

Im Task-Dialog (`TaskAssemblyCreateJoint`, bzw. in der Arbeit mit `JointObject`) laufen typischerweise diese Schritte:

1. Der Benutzer wählt Elemente aus.
2. Der Dialog füllt `Reference1`, `Reference2`, `Type`, etc.
3. Die Änderungen werden in die Joint-Properties übernommen.
4. Es wird ein Recompute ausgelöst.
5. `AssemblyObject` bearbeitet den Graphen.

### 4.2 C++-Solver-Schicht

In `AssemblyObject.cpp` wird die Assembly dann als Graph ausgelesen. Dabei gibt es typischerweise eine logische Kette wie:

- `solve()` startet Kinematik-Berechnung
- `jointParts()` verarbeitet Joints und Teilbeziehungen
- `findPlacement()` findet die passende Transformation zwischen den referenzierten Koordinatensystemen
- `fixGroundedParts()` und andere Helper behandeln feste/Root-Objekte

Das ist der Punkt, an dem die Relation aus der Python-/GUI-Definition in eine echte numerische Bewertung übersetzt wird.

### 4.3 OndselSolver-Schicht

Das Backend `OndselSolver` übernimmt die eigentliche numerische Korrektur. Hier werden die Constraint-Gleichungen aus den Joints in die Form eines Systems gebracht:

- residuals
- Jacobian
- update vectors
- iterative linearization / solve

Das Interessante ist: Der Solver selbst ist nicht „der Feind“, sondern das System bekommt beim ersten Recompute oder bei einem inkonsistenten Startzustand falsche Ausgangswerte. Genau das wurde im Projekt mehrfach als Ursache identifiziert: Ein schlecht initialisierter State, insbesondere bei Slider-Ketten, kann dazu führen, dass die Kette auf eine falsche Default-Lösung kollabiert.

Das heißt:

Der tatsächliche Fehler liegt oft nicht im Solver selbst, sondern im initialen Zustand oder in der Reihenfolge der Constraint- und Recompute-Initialisierung.

## 5. Warum genau `matchJCS()` und `onChanged` so wichtig sind

Ein praktisch entscheidender Punkt in FreeCAD 26.3 ist die Verbindung zwischen Property-Änderung und Pre-Solve-Mechanik.

Wenn ein Joint-Property verändert wird, kann ein Callback ausgelöst werden, etwa:

- `onChanged(joint, "Offset2")`
- `preSolve()`
- `matchJCS()`

Dort wird die interne Interpretation des Joint-Zustands neu gebildet. Das ist wichtig, weil die Berechnung des Solvers nicht aus einer „statischen“ Joint-Definition allein folgt, sondern aus einem aktuellen, live aktualisierten Zustandsbild.

In der Praxis führt die falsche Reihenfolge dazu, dass:

- ein Joint noch nicht als „verbunden“ im Solver kennt,
- ein Teil als „frei“ behandelt wird,
- die lokale JCS-/Achsen-Relation falsch interpretiert wird,
- der Solver einen 6-DOF-Snap auf eine ungültige Default-Konfiguration macht.

Das ist genau die Ursache, die dieses Projekt in seinen Patch-Notizen als Slider-Ketten-Kollaps beim ersten Recompute beschrieben hat.

## 6. Reale Funktionen und ihre Rollen

Wichtige Kandidaten im realen Codepfad:

### `AssemblyObject::solve()`

Startpunkt für die eigentliche Baugruppenlösung. Reagiert auf Statusänderungen und startet den Anwender- bzw. System-Lauf.

### `jointParts()`

Verarbeitet Joints und ihre zugehörigen Körper/Referenzen. Hier wird die Topologie in den numerischen Graph übernommen.

### `findPlacement()`

Sucht die passende Platzierung / Transformation zwischen referenzierten Koordinatensystemen. Das ist der Kern, wenn verschiedene LCS/Origins oder App::Link-Referenzen aus unterschiedlichen Dokumenten oder Umgebungen zusammenspielen.

### `fixGroundedParts()`

Sorgt dafür, dass geerdete oder feste Teile nicht frei im System herumrutschen. Das ist ein zentraler Teil der Stabilisierung der Lösung.

### `matchJCS()`

Abgleich eines Joint-Coordinate-System (JCS) mit dem aktuellen System. Gerade bei Slider- und Cylindrical-Joints ist dieser Schritt kritisch, weil er die Schiebeachse und die Restbedeutung der Freiheitsgrade entscheidet.

## 7. Noch präziser: was in der Kette passiert

Die echte Sequenz kann man vereinfacht so modellieren:

1. Benutzer/GUI ändert Joint-Param.
2. Python-Dialog setzt `Reference1/Reference2`, `Offset` etc.
3. Document-Recompute wird ausgelöst.
4. `AssemblyObject` sammelt Joints.
5. Für jeden Joint wird ein numerischer Constraint erzeugt.
6. `OndselSolver` bekommt die Constraint-Liste.
7. Der Solver erzeugt Residuen und Jacobianblöcke.
8. Iteration berechnet ΔQ.
9. `Placement`/`Transform` der Teilobjekte wird aktualisiert.
10. GUI wird redrawet.

Die genaue Reihenfolge ist entscheidend, weil die Zwischenzustände zwischen 4 und 8 nichts mit „fertiger Geometrie“ zu tun haben. Sie sind nur Zwischenmodelle im Solving-Prozess.

## 8. Was die Patch-Workflows in diesem Projekt zeigen

Die dokumentierten Probleme und Fixes in diesem Repository zeigen eine sehr reale Sicht auf die Code-Mechanik. Besonders relevant sind:

- Cross-document joint references
- invalid `Reference1`/`Reference2` after creation
- selection reset in joint task dialogs
- clearIsolate / GUI update timing
- slider chain issue on first recompute
- `AssemblyObject::solve()` starting without prior joint registration

Das ist genau die Art von Problem, die man nur dann sinnvoll versteht, wenn man die realen Klassen und die Reihenfolge von `JointObject` → `AssemblyObject` → `OndselSolver` kennt.

## 9. Praktische Einordnung

Wenn man den Solver wirklich verstehen will, muss man die drei Ebenen trennen:

1. Datenmodell (JointOobject, References, Placements)
2. Recompute-Graph (AssemblyObject, Graph, dirty flags, propagation)
3. Numerik (Residuals, Jacobian, Newton-Schritte, OndselSolver)

Wenn eine dieser drei Ebenen „falsch“ initialisiert ist, kann die Lösung fehlerhaft sein, obwohl der mathematische Kern grundsätzlich korrekt ist.

## 10. Kurzfassung mit Fokus auf den tatsächlichen Source-Code

Die wichtige Wahrheit ist:

- `JointObject` bildet die UI- und Datenstruktur eines einzelnen Joints.
- `AssemblyObject` organisiert den Gesamtgraphen und startet `solve()`.
- `OndselSolver` löst die numerische Kinematik.
- Die wirkliche Stabilität hängt nicht nur von der Mathematik ab, sondern von der Reihenfolge, den Referenzen und dem initialen Zustandsvektor Q.

Die meisten echten FreeCAD-Assembly-Probleme entstehen nicht durch eine „schlechte Formel“, sondern durch eine falsche Reihenfolge im System:

- Joint-Referenzen noch nicht aufgelöst,
- `matchJCS()` läuft zu früh,
- `solve()` startet ohne vollständigen Joint-Graph,
- GUI-Redraw läuft zu früh.

Diese Beobachtungen sind das, was man in den realen FreeCAD-C++/Python-Quellen immer wieder sieht.

## 11. Fazit

Wer den Assembly-Solver wirklich verstehen will, muss den Blick von „nur einem Joint“ auf den vollständigen Orchestrierungsfluss richten:

- JointObject definiert den Constraint
- AssemblyObject verbindet die Objekte und startet die Lösung
- OndselSolver berechnet die numerische Korrektur
- GUI und Qt steuern, triggern und visualisieren das Ergebnis

Das ist der eigentliche Kern der FreeCAD-26.3-Assembly-Mechanik – und genau das ist der Teil, den man im erfolgreichen Debugging und bei stabilen Baugruppen immer wieder verstehen muss.

---

Datei: resources/docs/ASSEMBLY_SOLVER_SOURCE_CODE.md
