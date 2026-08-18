# FreeCAD 26.3 Assembly Solver – kurz erklärt

Der Assembly Solver ist der Teil von FreeCAD, der aus einer Menge von Bauteilen und ihren Beziehungen eine konsistente Baugruppe baut. Er ist das Herzstück der Assemblies: Ohne Solver wäre eine Baugruppe nur eine Ansammlung von Objekten, die zwar im 3D-Raum liegen, aber nicht logisch zueinander verbunden sind.

In FreeCAD 26.3 ist dieser Vorgang eng mit den Assembly-Joints und der internen Zustandsbeschreibung der Bauteile verbunden. In der Praxis bedeutet das: Wenn du ein Teil ziehst, drehen, ausrichten oder in einer Kette mit anderen Teilen verbinden willst, berechnet der Solver die passende Position so, dass alle definierten Beziehungen erfüllt sind.

## 1. Was macht der Solver?

Der Solver übernimmt drei zentrale Aufgaben:

1. Er liest die vorhandenen Joints.
2. Er bewertet den aktuellen Zustand der Baugruppe.
3. Er verschiebt und rotiert die beteiligten Teile so lange, bis die definierten Einschränkungen erfüllt sind.

Kurz gesagt:

- Ein Teil hat eine Position und Orientierung im Raum.
- Ein Joint beschreibt eine Beziehung zwischen zwei Teilen.
- Der Solver verändert die Positionen und Rotationen, bis diese Beziehungen stimmen.

Beispiele für typische Beziehungen:

- Zwei Flächen sollen aufeinander liegen.
- Ein Teil soll auf einer Achse gleiten.
- Ein Teil soll um eine Achse drehen.
- Zwei Objekte sollen einen festen Abstand zueinander haben.
- Ein Winkel soll exakt eingehalten werden.

Das ist der Kern des Baugruppen-Solvers: Er löst ein Gleichungssystem, das aus den Joint-Bedingungen entsteht.

### Typischer Ablauf

1. Ein Assembly-Objekt wird gebaut.
2. Teile werden per Links oder Referenzen eingebunden.
3. Joints werden zwischen den Objekten gesetzt.
4. Der Solver bekommt den aktuellen Zustandsvektor.
5. Er prüft, welche Freiheitsgrade noch offen sind.
6. Er berechnet eine neue, gültige Stellung.
7. Die dazugehörigen Placements werden übernommen.

In FreeCAD 26.3 ist das konkret an den Assembly-Mechanismen und an den C++/Python-Knoten rund um `AssemblyObject::solve()` und `jointParts()` zu sehen; im Hintergrund greift die Logik auf den Solver-Stack aus der Assembly-Architektur zurück.

### Warum ist das wichtig?

Ohne Solver wäre eine Baugruppe nur statisch. Mit Solver wird sie dynamisch:

- Bauteile können logisch am Baugruppenmodell „hängen“.
- Änderungen an einem Teil propagieren sich durch die Verbindung.
- Joints geben der Baugruppe kinematische Bedeutung.
- Die Gesamtstruktur bleibt konsistent, auch wenn einzelne Teile verschoben werden.

Das macht Assembly-Design in FreeCAD nicht nur zu einer Geometrie-Konstruktion, sondern zu einer echten kinematischen Beschreibung.

## 2. Hauptbeteiligte: Joints und Q

Wenn man die Assembly-Mechanik vereinfacht, dann sind die zwei wichtigsten Akteure:

- Joints: die Regeln und Einschränkungen
- Q: der Gesamtzustand der Baugruppe

### Joints

Joints sind die eigentlichen „Verbindungen“ in der Baugruppe.

Sie sagen nicht nur „dieses Teil ist hier“, sondern auch:

- wie zwei Objekte zueinander ausgerichtet sind,
- welche Bewegungsfreiheit noch bleibt,
- welche Achsen und Ebenen relevant sind,
- welche Beziehung der Solver erfüllen muss.

Typische Joint-Typen sind unter anderem:

- Fixed: Teil ist unveränderlich mit dem Referenzteil verbunden.
- Revolute: Drehung um eine Achse erlaubt.
- Slider: Gleitbewegung entlang einer Achse erlaubt.
- Cylindrical: Drehung und Translation entlang derselben Achse.
- Distance / Angle: Abstand oder Winkel wird fest vorgegeben.

Ein Joint nutzt dabei normalerweise lokale Koordinatensysteme (LCS/Origin/Connector-Bezug), damit die Verbindung an definierten Ebenen oder Achsen festgemacht wird. Genau dort entsteht die geometrische Semantik der Baugruppe.

Wichtig: Joints produzieren nicht nur sichtbare Beziehungen, sondern auch mathematische Restriktionen. Der Solver versucht, diese Restriktionen gleichzeitig zu erfüllen.

### Q

Q ist der Zustandsvektor der Baugruppe bzw. der beweglichen Teile. Vereinfacht ausgedrückt:

- Q enthält die aktuelle Position und Rotation aller relevanten Objekte.
- Es ist die „momentane Konfiguration“ der Baugruppe.
- Der Solver verändert Q, bis alle Joint-Bedingungen erfüllt sind.

Ein einfacher Gedanke:

- Ein einzelnes Teil hat 6 Freiheitsgrade: 3 Translationen + 3 Rotationen.
- Eine Baugruppe mit mehreren Teilen hat entsprechend viele Einträge im Zustandsvektor.
- Joints nehmen einige dieser Freiheitsgrade weg.
- Der Solver versucht, die noch freien Variablen so zu bestimmen, dass die Einschränkungen stimmen.

Eine grobe Form sieht ungefähr so aus:

- Q = [x, y, z, rx, ry, rz, ...]

für alle Teilzustände in der Baugruppe.

Der Solver bewertet dann die Residuen bzw. Abweichungen der aktuellen Konfiguration von den durch die Joints vorgegebenen Bedingungen. Wenn Abweichungen bestehen, wird Q angepasst.

### Die Beziehung zwischen Joints und Q

Die Logik ist praktisch:

- Joints definieren Gleichungen und Constraints.
- Q ist der Vektor, der diese Gleichungen löst.
- Der Solver arbeitet wie eine Maschine, die Q so verändert, dass die Constraints erfüllt werden.

Man kann es so formulieren:

- Joints geben die Regeln vor.
- Q beschreibt den aktuellen Zustand.
- Der Solver findet den Zustand, der zu den Regeln passt.

Das ist die zentrale Idee jeder Assembly-Mechanik: Beziehungen zwischen Teilen werden als Gleichungen ausgedrückt, und ein Solver findet die passende Lösung.

## 3. Was bedeutet das für FreeCAD 26.3?

In FreeCAD 26.3 ist die Assembly-Logik deutlich transparenter geworden: Die Baugruppe wird nicht mehr bloß als Geometrie-Container betrachtet, sondern als ein System mit Zuständen, Joints und eindeutigen Kinematik-Regeln.

Das zeigt sich unter anderem daran, dass der Assembly-Graph und der Solve-Call selbst in den Recompute- und Joint-Prozessen eine zentrale Rolle spielen. Wenn ein Joint oder eine Platzierung verändert wird, muss der Solver erneut laufen. Dabei kann die Lösung vollständig neu erfolgen oder nur lokal aktualisiert werden, je nach Situation.

Die praktische Folge:

- Ein Joint ist mehr als nur eine grafische Verbindung.
- Ein Solver-Lauf ist mehr als nur ein geometrischer Neuaufbau.
- Der Zustand einer Baugruppe wird aus den Constraints berechnet.

## 4. Fazit

Der FreeCAD-26.3-Assembly-Solver ist der Mechanismus, der eine Baugruppe von „nur genutzter Geometrie“ in ein echtes, regelbasiertes Zusammenspiel von Bauteilen verwandelt.

Die wichtigsten Bestandteile sind:

- Joints: definieren die Beziehungen zwischen Teilen.
- Q: beschreibt den aktuellen Zustand und die beweglichen Freiheitsgrade.
- Der Solver: arbeitet an Q, damit alle Joints konsistent erfüllt werden.

Wer die Dynamik von Assemblies verstehen will, muss diese drei Ebenen im Blick haben: Geometrie, Constraints und Zustand. Genau hier liegt der Kern des Assembly-Solvers.

Wenn du die Baugruppen-Mechanik mit FreeCAD ernsthaft nutzen willst, ist das Grundprinzip immer dasselbe:

- Joints legen die Regeln fest.
- Q beschreibt den aktuellen Zustand.
- Der Solver bringt beides in eine konsistente Lösung.
