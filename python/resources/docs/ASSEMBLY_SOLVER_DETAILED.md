# Assembly Solver – technische Details (FreeCAD 26.3)

Diese technische Ergänzung geht über die kurze Einführung hinaus und zeigt, wie der Assembly-Solver formal arbeitet, wie Constraints in Gleichungen überführt werden und wie ein einfacher Newton-Iteration-Solver für kleine Beispiele implementiert werden kann. Außerdem wird das Zusammenspiel mit der Qt/PySide6-GUI erläutert, wie Recompute- und Solve-Aufrufe typischerweise im Event-Loop eingebunden werden.

Hinweis: Die Beispiele sind bewusst kompakt und verwenden NumPy für die numerische Linearisierung und Lösung. FreeCADs interner Solver (z. B. OndselSolver) ist leistungsfähiger, nutzt ähnliche mathematische Prinzipien, erweitert sie aber um robuste Matrixfaktorisierung, Regularisierung, Dämpfung und Heuristiken für kinematisch unterbestimmte Systeme.

## 1. Mathematisches Modell

Eine Assembly besteht aus N starrer Körper. Jeder Körper i hat eine Platzierung, beschrieben durch einen Teilvektor q_i aus dem globalen Zustandsvektor Q.

- Für rein translationsbasierte Betrachtung: q_i = [x_i, y_i, z_i]
- Vollständig starrer Körper: q_i = [x_i, y_i, z_i, rx_i, ry_i, rz_i] (z. B. rotatorische Parameter als Rodrigues-/Euler-/Quaternion-Parameter)

Der gesamte Zustandsvektor ist Q = [q_1, q_2, ..., q_N]^T.

Constraints (Joints) werden als Gleichungen formuliert:

g_k(Q) = 0,  für k = 1..M

Beispiel-Typen und typische Formen:

- Distance-Joint (Abstand d zwischen zwei Punkte-Paaren auf Körper 1 und 2):
  g(Q) = ||p2(Q) - p1(Q)|| - d = 0

- Coincidence (Koinzidenz zweier Punkte):
  g(Q) = p2(Q) - p1(Q) = 0  (vektorwertig, 3 Gleichungen)

- Revolute (gemeinsame Achse z und gleiche Position orthogonal zur Achse): Kombination aus Koinzidenz + 2 Orthogonalitäts-Bedingungen

Allgemein: g: R^n -> R^m, n = dim(Q), m = Anzahl Gleichungen (Restriktionen).

Ziel des Solvers: finde Q so, dass g(Q) ≈ 0 (innerhalb Toleranz). Praktisch iterativ:

Newton-Raphson (klassisch):

1. Gegeben Q^t, berechne Residuum r = g(Q^t).
2. Berechne Jacobian J = dg/dQ (m × n Matrix).
3. Löse lineares System J * ΔQ = -r (oder in überbestimmten Fällen Löse J^T J ΔQ = -J^T r).
4. Update Q^{t+1} = Q^t + α * ΔQ (mit mögliches Dämpfungsfaktor α ∈ (0,1]).
5. Wiederhole bis Konvergenz.

Für numerische Stabilität und unterbestimmte/überbestimmte Fälle werden Pseudoinverse, Levenberg–Marquardt oder QR/SVD-Faktorisierungen genutzt.

## 2. Kleines, erklärtes Beispiel: Zwei Körper, Distance-Joint (nur Translationen)

Aufbau:
- Körper A hat Position p1 = (x1,y1,z1)
- Körper B hat Position p2 = (x2,y2,z2)
- Constraint: ||p2 - p1|| = d

Residuum:

r(Q) = norm(p2 - p1) - d

Jacobian (Ableitungen nach den 6 Unbekannten x1,y1,z1,x2,y2,z2):

Let v = p2 - p1, L = ||v||.

∂r/∂p1 = -v / L
∂r/∂p2 = +v / L

Also ist J = [ -v/L, +v/L ] (1 × 6 Matrix)

Lineares Update ΔQ aus J ΔQ = -r ist ein 1×6 System; übliche Wahl ist die kleinste Norm-Lösung (Pseudoinverse):

ΔQ = -J^T * (J J^T)^{-1} * r

Für dieses sehr einfachen Fall kann man die Verschiebung auf die beiden Körper proportional aufteilen oder ein Körper als geerdet behandeln (Δp1 = 0) und nur Δp2 bestimmen.

### Python-Beispiel (NumPy)

Das folgende Beispiel löst das Distance-Constraint nur auf den Translationen mit Newton-Schritten.

```python
import numpy as np

# Zielabstand
d = 10.0

# Startkonfiguration (p1, p2)
p1 = np.array([0.0, 0.0, 0.0])
p2 = np.array([8.0, 0.0, 0.0])  # momentan zu nahe

# Zustandsvektor Q = [p1, p2]
Q = np.hstack([p1, p2])

def residual(Q):
    p1 = Q[:3]
    p2 = Q[3:6]
    v = p2 - p1
    return np.linalg.norm(v) - d

def jacobian(Q):
    p1 = Q[:3]
    p2 = Q[3:6]
    v = p2 - p1
    L = np.linalg.norm(v)
    if L == 0:
        # singulärer Fall: kleine Störung geben
        v = np.array([1e-8, 0.0, 0.0])
        L = np.linalg.norm(v)
    j_p1 = -v / L
    j_p2 = +v / L
    J = np.hstack([j_p1, j_p2]).reshape(1, 6)
    return J

# Newton-Iteration
for i in range(10):
    r = residual(Q)
    print(f"Iter {i}: residual={r}")
    if abs(r) < 1e-6:
        break
    J = jacobian(Q)
    # kleinste-Norm-Lösung via Pseudoinverse
    # ΔQ = -J^T (J J^T)^{-1} r
    JJt = J @ J.T
    dQ = -J.T * (r / JJt)
    # optional damping
    alpha = 0.8
    Q = Q + alpha * dQ.ravel()

print('Ergebnis p1=', Q[:3], 'p2=', Q[3:6])
```

Dieses Beispiel behandelt beide Körper gleich. Alternativ kann p1 festgehalten werden (A als Ground) und nur p2 aktualisiert. Dann wäre die Unbekannte nur p2 und die Newton-Schritte trivialer.

## 3. Kleines Beispiel: Slider-Joint (eine DOF frei)

Slider-Joint erlaubt relative Translation entlang einer Achse u (Einheitsvektor) zwischen zwei Körpern; alle orthogonalen Komponenten sind fixiert.

Constraint: die Projektion des Vektors v = p2 - p1 auf orthogonale Ebene muss 0.

Mathematisch: Wähle zwei orthogonale Richtungen u1,u2 orthogonal zu Schiebe-Achse u.

g(Q) = [ u1·(p2-p1), u2·(p2-p1) ]^T = 0

Dies sind 2 Gleichungen (reduziert die 6 Relativen DOF um 2), die verbleibende DOF entlang u bleibt frei (oder wird durch zusätzlichen Distance/Limit bestimmt).

Jacobian ist aus den partiellen Ableitungen der Skalarprodukte zusammengesetzt: ∂g/∂p1 = -[u1,u2]^T, ∂g/∂p2 = +[u1,u2]^T.

## 4. Überbestimmte / unterbestimmte Systeme

- Überbestimmt (m > n): mehr Constraints als Freiheitsgrade — typischerweise inkonsistent, Solver minimiert Residuum (Least-Squares) oder meldet Fehler.
- Unterbestimmt (m < n): freie DOFs bleiben — physikalisch oft Bewegungsfreiheit, Solver benötigt zusätzliche Ziele (z. B. Minimierungsfunktion, Regularisierung, Startwert-„Bias").

In FreeCAD wird oft ein gemischter Ansatz verwendet: Newton-Schritte mit Tikhonov-Regularisierung (Levenberg-Marquardt-ähnlich) und heuristischem Festlegen von geerdeten Teilen (Grounds), um Nullraum frei zu lassen.

## 5. Jacobian-Aufbau bei starren Körpern (Rotationen)

Für eine Rotation sei die Platzierung eines Punktes lokal p_local. Die globale Position ist p_global = R(q_rot) * p_local + t(q_trans)

Ableitung nach Rotationsparametern ergibt sich aus der Ableitung der Rotationsmatrix; in Praxis wird häufig eine kleine-Rotations-Approximation genutzt (skew-symmetric operator):

d/dφ (R(φ) p) ≈ ( -[R p]_x )  (für kleine Winkel, wobei [v]_x die Kreuzprodukt-Matrix ist)

So entstehen Einträge im Jacobian, die Rotations-DOFs auf Punkt-Positionen koppeln. Die vollständige Implementierung in FreeCAD nutzt robuste Parameterisierungen (Quaternionen oder Exponential-Koordinaten) und ordnet die Rotations-Teilmatrix entsprechend zu.

## 6. Zusammenspiel mit FreeCAD-Objekten und Qt (Lifecycle)

Typische Ereignisse im GUI-Flow:

1. Benutzer ändert einen Joint-Parameter im Dialog (PySide6 Task-Dialog).
2. Property-Änderung wird von FreeCADs ExpressionEngine/Property-Mechanismus registriert -> `onChanged()`-Callbacks feuern.
3. Für bestimmte Joint-Typen ruft dieser Callback `preSolve()`/`matchJCS()`-Hooks auf, die ggf. Platzhalter-Placements anpassen oder zusätzliche lokale Prüfungen ausführen.
4. Schließlich wird der Assembly-Recompute/Solve angestoßen — entweder direkt `assembly.solve()` (schnell, rechnet lokal) oder ein `recompute()` der ganzen Document-Kaskade (kalt, rekonstruiert Graph).
5. Solver berechnet neues Q.
6. Solver schreibt die neuen Placements/Placements1/2 zurück in die Joint-Properties und/oder die Link-Objekte.
7. GUI erhält Update und rendert die neue Konfiguration.

Wichtig: Der Qt-Eventloop darf durch lange Solver-Läufe nicht blockiert werden. Typische Muster:

- Starten des Solve in einem Hintergrund-Thread (QThread, QRunnable via QThreadPool).
- Während des Solves nur minimaler GUI-Update; nach Abschluss Ergebnisse via Signal an Hauptthread melden und Placements dort setzen.
- Für kurze Solve-Läufe (wenige ms) kann ein synchroner Aufruf tolerierbar sein, aber Interaktivität leidet.

### Beispiel: PySide6 - Solve in Hintergrund und Update im Main-Thread

```python
from PySide6.QtCore import QObject, Signal, QRunnable, Slot, QThreadPool

class SolveResult(QObject):
    finished = Signal(object)  # emit Q when done

class SolverRunnable(QRunnable):
    def __init__(self, assembly_snapshot, result_emitter):
        super().__init__()
        self.assembly_snapshot = assembly_snapshot
        self.emitter = result_emitter

    @Slot()
    def run(self):
        # long-running numerical solve (nicht GUI-thread)
        Q_solution = numerical_solve(self.assembly_snapshot)
        # emitter ist QObject mit Signal; emit im Worker-Thread ist erlaubt
        self.emitter.finished.emit(Q_solution)

# In GUI-Code
result_emitter = SolveResult()
result_emitter.finished.connect(on_solve_finished)  # runs in main thread
runnable = SolverRunnable(assembly_snapshot, result_emitter)
QThreadPool.globalInstance().start(runnable)

# Callback im Hauptthread
def on_solve_finished(Q_solution):
    # schreibe neue Placements in die FreeCAD-Objekte hier (Main-Thread)
    apply_solution_to_document(Q_solution)
    App.ActiveDocument.recompute()
```

Wichtig: Änderungen an FreeCAD-Dokumenten und GUI-Objekten müssen im Main-Thread erfolgen; Worker-Threads dürfen nur reine Numerik/IO machen und ein Ergebnis-Objekt per Signal zurückgeben.

## 7. Typische Integrationsfallen (aus der Praxis von FreeCAD 26.3)

- "Kalt-Solve" vs. "Warm-Solve": ein voller Dokument-Recompute kann dazu führen, dass manche Joints vor dem Solver bereits eine `onChanged`-Reaktion auslösen, die `matchJCS()` aufruft - wenn der Solver noch keine interne Repräsentation der Joints registriert hat, können diese Hooks falsche Annahmen treffen (siehe Slider-Ketten-Bug). Deshalb ist Reihenfolge/Timing kritisch.

- Cross-Document-Referenzen (`App::Link`) können beim ersten Recompute noch nicht vollständig aufgelöst sein; Joint-Referenzen tauchen vorübergehend als `None` auf. Robustere Logik prüft Referenz-Existenz und verzögert endgültige Solve-Schritte bis die Referenzen gültig sind.

- Numerische Robustheit: fast-kolineare Achsen, sehr kleine Abstände, oder vollständig unterbestimmte Subsysteme erfordern Regularisierung (z. B. kleine Diagonalfaktoren in J^T J) und sinnvolle Defaults (Grounding eines oder mehrerer Körper).

## 8. Hinweise zur Implementierung in C++/OndselSolver

FreeCADs OndselSolver implementiert viele der oben beschriebenen Verfahren effizient in C++:

- Aufbau von Residuen- und Jacobian-Blöcken pro Joint
- Zusammensetzen in große, dünnbesetzte Matrizen
- Verwenden von stabilen Faktorisierungen (QR/Sparse-LU/SVD) je nach Struktur
- Dämpfung/Regularisierung für Newton-Schritte
- Heuristiken für Nullraum-Parameter (z. B. bei Gelenkketten)

Durch die C++-Implementierung entfallen viele Python-Overheads, sodass große Baugruppen in akzeptabler Zeit gelöst werden können.

## 9. Weiterführende Experimente

- Ersetze im Python-Beispiel die 3D-Translationen durch 6D-Rigid-Body-States mit kleiner-Rotations-Approximation und baue einfache Punkt-Koinzidenz-Constraints ein.
- Experimentiere mit Levenberg–Marquardt (Δ = -(J^T J + λ I)^{-1} J^T r) für stabilere Konvergenz in stark nichtlinearen Fällen.
- Implementiere ein kleines, sparsames Jacobian-Assembler für typische Joint-Typen und messe Laufzeit/Skalierung.

---

Datei: resources/docs/ASSEMBLY_SOLVER_DETAILED.md
