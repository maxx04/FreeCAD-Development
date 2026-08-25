# FreeCAD-Kernbug: Joint in einer zweifach eingebetteten flexiblen Sub-Baugruppe wird beim
# interaktiven Ziehen komplett ignoriert

**Status: sauber isoliert, minimales Repro-Paket vorhanden, in unveränderter FreeCAD-Weekly-
AppImage bestätigt (echter Upstream-Bug, nicht durch eigene Patches verursacht) - noch nicht
upstream eingereicht.**

## Bestätigung in unveränderter Vanilla-AppImage (2026-08-25)

Dasselbe Repro-Paket (`minimal-repro.zip`) in `FreeCAD_weekly-2026.08.05-Linux-x86_64.AppImage`
geöffnet (keine eigenen Patches, keine eigene Kompilierung) - **identisches Verhalten**: BoxB
lässt sich zwei Ebenen tief frei ziehen und bleibt auch nach komplettem Recompute an der
zufälligen Stelle stehen. Damit ausgeschlossen, dass einer unserer eigenen (teils bereits wieder
deaktivierten) Assembly-Patches diesen Bug verursacht - reiner FreeCAD-Kernbug.

## Symptom

Wird eine flexible `Assembly::AssemblyLink` selbst NOCHMAL als flexible AssemblyLink in ein
drittes Dokument eingebettet (zwei Verschachtelungsebenen statt einer), verlieren Joints, die
INNERHALB der tiefsten Sub-Baugruppe definiert sind, beim interaktiven Ziehen im 3D-Fenster
jegliche Wirkung - das betroffene Teil lässt sich in JEDE Richtung frei bewegen (nicht nur
entlang der vom Joint erlaubten Freiheitsgrade), und bleibt auch nach einem **kompletten
Dokument-Recompute dauerhaft** an der falschen Stelle stehen.

Das ist die Ursache hinter den ganzen "Baugruppe zerschossen"-Vorfällen dieser Woche mit
Motor67/68 in `CNC3018_037_A_TraegerBaugruppe_Z.FCStd` (siehe
[[project_fcproject_motor68_traegerbg_integration]]).

## Repro-Paket (`minimal-repro.zip`)

Drei Dokumente, ineinander verschachtelt:

```
MinimalReproGrandTop.FCStd
  └─ Assembly001 (flexible AssemblyLink -> MinimalReproTop#Assembly)
       ├─ BoxC, BoxD (Top-Level-Teile von MinimalReproTop, gespiegelt)
       │    Joints: Gleitverbindung (BoxC-BoxD), StarrerVerbund (BoxA-BoxD)
       └─ unterAssembly (flexible AssemblyLink -> MinimalReproSub#Assembly, gespiegelt)
            ├─ BoxA, BoxB
            └─ Joints: Gleitverbindung/Joint003 (BoxA-BoxB, Slider)
```

- `MinimalReproSub.FCStd`: BoxA (geerdet) + BoxB, verbunden über einen Slider-Joint.
- `MinimalReproTop.FCStd`: bettet Sub als flexible AssemblyLink ein (Spiegel von BoxA geerdet),
  plus zwei EIGENE Top-Level-Teile BoxC (geerdet)/BoxD, verbunden per Slider (BoxC-BoxD) und
  Fixed-Joint (BoxA-BoxD, ueber die Grenze Top-Level<->eingebettete Sub-Baugruppe hinweg).
- `MinimalReproGrandTop.FCStd`: bettet Top NOCHMAL als flexible AssemblyLink ein (Spiegel von
  BoxC geerdet) - **zwei Ebenen tief**.

## Kontrollmatrix (2026-08-25, live durchgetestet)

| Test | Verschachtelungstiefe | Ergebnis |
|---|---|---|
| Slider BoxA-BoxB komplett INNERHALB einer eingebetteten Sub-Baugruppe (1 Ebene) | 1 | ✅ Sauber - Solve konvergiert, Slider haelt, kein Redundanz-Fehler |
| Fixed-Joint BoxA(gespiegelt)-BoxD ueber Top-Level<->eingebettete-Grenze hinweg (1 Ebene) | 1 | ✅ Sauber - Solve konvergiert (Convergence ~1e-8), Fixed haelt starr |
| Slider BoxA-BoxB, aber Sub jetzt selbst nochmal in GrandTop eingebettet | **2** | ❌ **BoxB laesst sich in JEDE Richtung frei ziehen, bleibt nach komplettem Recompute dauerhaft an der (beliebigen) gezogenen Stelle stehen** |
| BoxA (Teil der Grounding-Kette, an jeder Ebene neu geerdet) ziehen, dann Recompute | 2 | ✅ Springt korrekt zurueck - die Grounding-Kette selbst funktioniert auch 2 Ebenen tief |

**Wichtig, ausdruecklich ausgeschlossen:** kein Slider-Distance-Artefakt (siehe das verwandte,
separate Problem in `bugreport-ensureIdentityPlacements/`) - BoxB bleibt nicht etwa nur
"irgendwo entlang der erlaubten Achse" stehen, sondern buchstaeblich exakt an der gezogenen
Stelle, AUCH abseits der Achse (verdreht/seitlich versetzt). Der Joint wird also nicht bloss
unterbestimmt gelassen, sondern komplett ignoriert.

## Vermuteter Mechanismus (aus dem Live-Log rekonstruiert)

Waehrend des interaktiven Ziehens (`preDrag()`) loest **ausschliesslich** die AEUSSERSTE
Assembly (`MinimalReproGrandTop`) wiederholt neu - im Log erscheint bei jedem Zieh-Frame nur
`Solving 'MinimalReproGrandTop#Assembly'`, kein einziges `Solving 'MinimalReproTop#Assembly'`
oder `Solving 'MinimalReproSub#Assembly'` dazwischen. Der Slider-Joint, der BoxB haelt, lebt
aber INNERHALB von `MinimalReproSub`s eigenem `AssemblyObject` - dessen `solve()` wird waehrend
des Ziehens schlicht nie aufgerufen, BoxB hat in diesem Moment also niemanden, der es haelt.

Bei einem KOMPLETTEN Dokument-Recompute (nicht nur Loslassen) lösen dagegen alle drei Ebenen
brav nacheinander (Sub -> Top -> GrandTop, bestaetigt im Log: alle drei "finished successfully",
inklusive korrekt erkanntem Slider-Joint in Sub) - trotzdem bleibt BoxB falsch stehen. Das
deutet darauf hin, dass der abschliessende volle Solve zwar "sauber durchlaeuft", die zuvor
waehrend des Ziehens im Umgehung des inneren Solvers geschriebene (ungueltige) Placement aber
nicht als Fehler erkennt/korrigiert - vermutlich weil ein AssemblyLink beim Spiegeln seiner
Kinder deren Placement direkt uebernimmt, bevor/ohne dass das eigene, innere `solve()` sie noch
einmal validiert.

## Naechste Schritte

- [x] Minimal-Repro als GitHub-Issue bei FreeCAD/FreeCAD eingereicht (2026-08-25):
  https://github.com/FreeCAD/FreeCAD/issues/32171
- [ ] Root Cause im C++-Code lokalisieren (`AssemblyLink::updateContents()` /
  `ViewProviderAssembly::preDrag()` sind die naheliegendsten Ansatzpunkte, siehe
  `patches/freecad-assembly-grounded-joint-nested-flex.patch` fuer bereits vorhandene, verwandte
  Untersuchungen an `AssemblyLink.cpp`).
- [ ] Bis dahin: PlacementGuard-Workaround (siehe `python/PlacementGuardFeature.py`) bleibt die
  einzige zuverlaessige Methode fuer mehrfach verschachtelte flexible Baugruppen wie
  TraegerBaugruppe_Z/Motor67/68.
