# FreeCAD-Kernbug: Slider-Joint-Ketten verlieren ihre Position bei erzwungenem Kalt-Recompute

**Status: Ursache eingegrenzt, GitHub-Issue-Text fertig (siehe unten), noch nicht gepatcht/eingereicht.**

## ⚠️ Korrektur (2026-08-09, zweite Untersuchungsrunde)

Die erste Version dieser Untersuchung verdächtigte `AssemblyObject::ensureIdentityPlacements()`.
**Das war falsch** - Testartefakt der Aufrufreihenfolge im ersten Reproduktionsskript
(`repro_real_file.py`, dort historisch belassen). `ensureIdentityPlacements()` ist nachweislich
ein reiner No-Op für alle Objekte in der betroffenen Datei (`ElementCount=0` bei allen Links,
die Funktion greift laut Quellcode nur bei `ElementCount>0`). Isoliert bestätigt in
`repro_trigger1_doubleclick.py` und `repro_trigger2_setactiveobject.py`.

## Symptom

Beim Bearbeiten/Erstellen eines Joints (z. B. einer Gleitverbindung) in einer Baugruppe mit
bereits vorhandenen Joints springen andere, nicht am Joint beteiligte Bauteile dauerhaft auf
eine falsche Position. Nutzer-Repro: eine Kette aus 7 `App::Link`-Panels (PDM-Muster: jedes
Bauteil sein eigenes `.FCStd`-Dokument), über 6 Gleitverbindungen verbunden - beim Öffnen
*jedes* Joint-Dialogs sprangen mehrere Panels auf dieselbe Position.

## Tatsächliche Ursache (eingegrenzt, Mechanismus nicht abschließend bewiesen)

Der Auslöser ist **kein einzelner Funktionsaufruf**, sondern folgendes Muster:

1. Irgendetwas markiert das Dokument als "touched" (Objekt in den Edit-Modus bringen via
   `ViewObject.doubleClicked()`/`setActiveObject()`, ein Objekt löschen, o. ä.).
2. Der **nächste** `recompute()` ist dadurch kein No-Op mehr, sondern ein **kompletter
   "Kalt-Solve"** des gesamten Baugruppen-Graphen (im Gegensatz zu einem `assembly.solve(False)`,
   der die bereits zwischengespeicherten JCS-Werte nutzt und immer sauber bleibt).
3. Bei diesem Kalt-Solve haben Slider-Joints **ohne explizit gesetzten Distanz-/Offset-Wert**
   keine Information, um die zuvor durch interaktives Ziehen entstandene Position
   wiederherzustellen, und kollabieren auf eine (beliebige, aber constraint-gültige)
   Default-Lösung - hier: Koinzidenz mit der Nachbarposition in der Kette.

**Wichtig:** Das ist eine Arbeitshypothese für den *Mechanismus*, kein bewiesener Fakt - der
Trigger selbst (Punkte 1+2) ist dagegen mehrfach unabhängig bestätigt (siehe Kontrollmatrix).

## Reproduktion (Kontrollmatrix, zweite Runde)

| Skript | Setup | Ergebnis |
|---|---|---|
| `repro_trigger1_doubleclick.py` | `assembly.ViewObject.doubleClicked()` GANZ ALLEIN, kein weiterer Aufruf | ❌ **Kollabiert bereits** |
| `repro_trigger2_setactiveobject.py` | Nur `setActiveObject('Assembly', ...)`, kein recompute danach | ✅ Bleibt korrekt |
| `repro_trigger2_setactiveobject.py` | `setActiveObject(...)` **+ danach** `assembly.recompute(True)` | ❌ **Kollabiert, byte-identisch zu doubleClicked()** |
| `repro_trigger3_delete_recompute.py` | Kein Gui/ActiveObject/doubleClicked - nur `doc.removeObject(...)` + `doc.recompute()` | ❌ **Kollabiert ebenfalls** (dritter, unabhängiger Trigger) |
| `repro_minimal_2panel.py` | Reduziert auf Ground+2 Panels, 4 Joints, nur `doc.recompute()` | ❌ **Kollabiert zuverlässig - minimalster Fall** |
| `repro_control_solve_direct_stays_clean.py` | Direkter `assembly.solve(False)`-Aufruf (umgeht Dependency-Graph) | ✅ **Bleibt immer sauber** |
| `repro_control_no_joints.py` | Alle Joints entfernt | ✅ No-Op |
| `repro_control_plain_recompute.py` | Reines `recompute()` auf frisch geöffneter, konvergierter Datei | ✅ No-Op (nichts ist "touched") |
| `repro_control_minimal_synthetic.py` | Synthetische Links ohne Joints | ✅ No-Op |

→ Gemeinsamer Nenner aller fehlschlagenden Fälle: **Dokument wird "touched", danach ein
vollständiger Graph-Recompute.** Nicht `ensureIdentityPlacements()`, nicht der Solver an sich
(`solve(False)` bleibt sauber).

## Offene Fragen

- **Rein synthetischer Nachbau (generische `Part::Box`/`PartDesign::Body`, gleiche Topologie)
  reproduziert NICHT** (mehrere Versuche, u. a. `test_minimal_v3_topology.py`,
  `test_final_theory.py` - nicht ins Repo übernommen, da nur Negativbefunde ohne Repro-Wert).
  Irgendein Detail der echten Bauteil-Geometrie/-Referenzen scheint zusätzlich nötig zu sein
  (Kandidat: der erste Distance-Joint der echten Datei referenziert eine benutzerdefinierte
  Datum-Ebene in einem "Skelett_Body", keine einfache `Origin`-Ebene).
- **Dokumentübergreifende Architektur (PDM-Muster) scheint notwendig** - identische Topologie
  im selben Dokument (getestet mit direkten `Part::Box` und mit lokalen `App::Link`)
  reproduziert nicht. Auch das aber nicht isoliert von der übrigen echten Geometrie bestätigt.
- Exakte Codestelle im Solver (`AssemblyObject::solve()`/`jointParts()`/`OndselSolver`), die die
  Default-Lösung beim Kalt-Solve wählt, ist nicht instrumentiert/lokalisiert (bräuchte einen
  lokalen Rebuild mit Logging - bewusst nicht gemacht, siehe unten).

## Nicht gemacht

C++-Instrumentierung/Rebuild von `AssemblyObject.cpp` - als zu aufwendig/riskant im Verhältnis
zum bereits erreichten Erkenntnisstand eingeschätzt. Nächster nötiger Schritt, falls die
Wurzelursache abschließend geklärt werden soll: `solve()`/`jointParts()`/`fixGroundedParts()`
in einer lokalen Kopie mit Logging der Joint-Placement1/2-Werte vor/nach jedem
`findPlacement()`-Aufruf versehen, neu bauen, Trigger 2 gegen den `repro_minimal_2panel.py`-Fall
laufen lassen.

## GitHub-Issue-Entwurf (Englisch, noch NICHT eingereicht)

> Titel und Text unten sind zum Einreichen vorbereitet - Freigabe durch den Nutzer nötig,
> bevor irgendetwas an FreeCAD/FreeCAD auf GitHub gepostet wird.

---

**Title:** Assembly: chained Slider joints across App::Link parts silently lose their solved position on the next graph recompute (position collapses onto neighbouring part)

**FreeCAD version:** 26.3.0, Libs: 26.3.0devR47833 (git main, commit `0475b124bef1705ad45a548fc0314ada56915d93`, built 2026/07/26)

**Environment:** Ubuntu 24.04 (kernel 7.0.0), self-built from source (CMake), Qt6/PySide6.

**Steps to reproduce** (using an assembly with the same structural pattern as our production
file - one part per external `.FCStd` document, linked via `App::Link`, chained by Slider
joints with no explicit Distance/Offset driving the slide position):

1. Create 3 separate documents: `Ground.FCStd`, `Panel.FCStd` (a simple body), and an
   `Assembly.FCStd` containing an `Assembly::AssemblyObject`.
2. In the assembly, add `App::Link` instances: one linking to `Ground`'s body, and (at least)
   two linking to `Panel`'s body - call them `Panel0` and `Panel1`.
3. Ground `Panel0` to `Ground` fully (3 orthogonal `Distance` joints on the XY/YZ/XZ origin
   planes, or equivalent), so `Panel0` has 0 remaining DOF relative to `Ground`.
4. Create a `Slider` joint between `Panel0` and `Panel1` (`Origin.Y_Axis.` on both sides),
   leaving `Offset2` at its default (0) - i.e. do **not** give the joint any numeric value
   that determines the sliding position.
5. Manually position `Panel1` along the slide axis by setting its `Placement` directly
   (simulating interactive dragging in the 3D view) to a value distinct from `Panel0`'s, e.g.
   `Panel0.Placement.Base.y = -85`, `Panel1.Placement.Base.y = -50`.
6. Save and close the document, then reopen it. Confirm `Panel1` is still at Y=-50.
7. Trigger **any** of the following, all of which force a full recompute of the previously
   up-to-date assembly graph without the user dragging anything:
   - Double-click the Assembly object in the tree to enter Edit mode, or
   - `Gui.ActiveDocument.ActiveView.setActiveObject('Assembly', assemblyObj)` followed by
     `assembly.recompute(True)`, or
   - Delete an unrelated object in the document and call `doc.recompute()`.

**Expected behaviour:** `Panel1` stays at Y=-50 (its last known/saved, still-valid position -
the Slider joint has no numeric property that says otherwise, so its previously solved
position should be treated as a valid equilibrium and preserved).

**Actual behaviour:** `Panel1`'s position collapses onto `Panel0`'s position on the slide axis
(here: Y jumps from -50 to -85) as soon as any of the triggers above forces a "cold" recompute
of the assembly - even though nothing was dragged and no joint property was changed. In a chain
of N such Slider joints, every downstream part collapses onto the position of the first
(grounded) part in the chain; the axis perpendicular to the slide (Z in our real file) is
unaffected.

Symptom as originally observed by an end user: finishing a Joint-creation/edit dialog (OK)
snapped the two jointed parts to this collapsed state; Cancel snapped the *entire* assembly
(all parts in the chain) to it - both are instances of the same "forced cold recompute after
the dialog's transaction commit/abort" trigger.

**Reproduced with:**
- A reduced 2-panel extract of a real production assembly (Ground + 2 App::Link parts + 4
  joints) - 100% reliable, no GUI required (plain `App::Document.recompute()` after
  `removeObject()` on an unrelated object is sufficient).
- Isolated at the API level to two independent trigger mechanisms
  (`Gui::MDIView::setActiveObject` + recompute; `App::Document::removeObject` + recompute)
  that share nothing except "the assembly's dependency graph gets marked dirty and then fully
  re-solved".

**Not yet reproduced:** a fully synthetic, from-scratch file using only generic
`Part::Box`/plain `PartDesign::Body` geometry (same joint topology, same cross-document
`App::Link` architecture) - several attempts with matching topology did not trigger the
collapse, so some additional detail of the real part geometry/references (possibly the use of
a custom datum plane rather than an `Origin` plane for the anchoring joint) appears to matter
and hasn't been isolated yet.

**Suspected area:** `src/Mod/Assembly/App/AssemblyObject.cpp`, `solve()` and its helpers
(`jointParts()`, `fixGroundedParts()`), and/or the underlying `OndselSolver`
(`src/3rdParty/OndselSolver/`) - specifically how an unconstrained/underdetermined joint DOF is
seeded/resolved on a full re-solve versus how it was left by an interactive drag.

---

## Dateien in diesem Ordner

- `repro_trigger1_doubleclick.py` - `doubleClicked()` allein reproduziert bereits
- `repro_trigger2_setactiveobject.py` - Bisektion: `setActiveObject()` + `recompute()` ist der Kern
- `repro_trigger3_delete_recompute.py` - dritter, Gui-unabhängiger Trigger (Objekt löschen)
- `repro_minimal_2panel.py` - minimalster, zuverlässigster Fall (Ground + 2 Panels)
- `repro_control_solve_direct_stays_clean.py` - Kontrolle: `solve(False)` bleibt immer sauber
- `repro_control_no_joints.py`, `repro_control_plain_recompute.py`,
  `repro_control_minimal_synthetic.py` - Kontrollen aus der ersten Runde, weiterhin gültig
- `repro_real_file.py` - **historisch**, ursprünglicher (fehlgeleiteter) Reproduktionsversuch,
  siehe Korrektur-Hinweis oben und im Datei-Header

Alle Skripte, die auf echte Panels/Joints zugreifen, brauchen die private Nutzerdatei
`3_Panels_aus_6_auswalbar.FCStd` (nicht im Repo enthalten) - Pfad im Skript anpassen.

## Umgebung zum Ausführen

`FreeCADCmd` kann `JointObject.py` nicht importieren (PySide6-Konflikt mit dem projekteigenen
venv). Skripte, die Joints/`Gui`/`TaskAssemblyCreateJoint` brauchen, laufen mit dem vollen
`FreeCAD`-Binary + Offscreen-Qt:

```bash
source /home/maxx/Documents/FreeCAD-Development/.venv/bin/activate
PYSIDE_QT="${VIRTUAL_ENV}/lib/python3.12/site-packages/PySide6/Qt"
export QT_PLUGIN_PATH="${PYSIDE_QT}/plugins"
export LD_LIBRARY_PATH="${PYSIDE_QT}/lib:/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export PYTHONNOUSERSITE=1
export PYTHONPATH="${VIRTUAL_ENV}/lib/python3.12/site-packages"
export QT_QPA_PLATFORM=offscreen
timeout 60 /home/maxx/freecad/install/bin/FreeCAD -l repro_trigger1_doubleclick.py
```

Skripte ohne Joint-Erzeugung/Gui-Zugriff (`repro_control_plain_recompute.py`,
`repro_control_minimal_synthetic.py`, `repro_trigger3_delete_recompute.py`) laufen einfacher
unter `FreeCADCmd` mit nur `PYTHONPATH`/`PYTHONNOUSERSITE` gesetzt.

FreeCAD-Version: `26.3.0, Libs: 26.3.0devR47833` (selbst gebaut, siehe `../../CMakeLists.txt`
und Projekt-Memory für den Build-Kontext).
