# FreeCAD-Kernbug: Joint-Referenz in doppelt verschachtelte flexible Unterbaugruppe bricht beim Spiegeln

**Status: Ursache gefunden und mit synthetischem Minimal-Repro (`repro.py`) bewiesen
(2026-08-19). Noch nicht gepatcht** - Fixversuch am 2026-08-19 an der verwandten
Rigid-Group-Variante hat eine Regression verursacht (siehe
[[project_fcproject_redundant_fixed_joint_rigidgroup_fix]]), deshalb hier bewusst erst
sauber verstanden und dokumentiert, bevor erneut Code angefasst wird.

## Symptom

`CNC3018_022_A_CNC3018_GesamtBaugruppe.FCStd` (`~/Dokumente/CAD_Workspace/PROJ_CNC3018/`)
bindet zwei baugleiche Unterbaugruppen ein: `CNC3018_025_A_FuerungsBaugruppe330` (mehrfach)
und `CNC3018_032_A_FuehrungsBaugruppe400`. Beide enthalten selbst wieder eine verlinkte
`Halterbaugruppe` (`Assembly::AssemblyLink`, zweite Verschachtelungsebene) sowie einen
Joint, der ein Teil *innerhalb* dieser Halterbaugruppe mit einem Teil *außerhalb*
verbindet (Führungsschiene). Bei 330 funktioniert die gespiegelte Verbindung in der
Gesamtbaugruppe korrekt - bei 400 nicht: die Halterbaugruppen erscheinen komplett
unverbunden/losgelöst von der Führung, obwohl der Joint strukturell existiert.

## Diagnose

Direkter XML-Vergleich (`unzip -p ... Document.xml`) der beiden gespiegelten
Verbindungs-Joints in der Gesamtbaugruppe:

```
330 (funktioniert):  Reference1: file=""                                   name="Halterbaugruppe"  Sub="Halter.Edge55"
400 (kaputt):        Reference1: file="FuehrungsBaugruppe400.FCStd"        name="Halter002"        Sub="Edge34"
```

Bei 400 zeigt die Referenz **direkt und mit vollem externem Dateipfad** aufs Enkelkind
(`Halter002`, das eigentliche Teil innerhalb der Halterbaugruppe) - bei 330 zeigt sie
**kompakt** auf die direkte Kind-Baugruppe (`Halterbaugruppe`), mit dem Enkelkind nur als
Teil des zusammengesetzten `Sub`-Strings. Diese Kodierung ist schon in der jeweiligen
**Quelldatei selbst** unterschiedlich, nicht erst nach dem Spiegeln entstanden.

Root Cause, zwei zusammenwirkende Stellen:

**1. `UtilsAssembly.getComponentReference()`** (`src/Mod/Assembly/UtilsAssembly.py:1233`) -
entscheidet beim Anlegen eines Joints anhand der Flächenauswahl, wo der Referenzpfad
"stoppt":

```python
if obj.isDerivedFrom("Assembly::AssemblyLink"):
    if hasattr(obj, "Rigid") and not obj.Rigid:
        continue  # ueberspringt die Unterbaugruppe, laeuft bis zum Enkelkind durch
```

Ist die verschachtelte `Halterbaugruppe` als `Rigid=True` eingefügt, stoppt die Funktion
dort (kompakte Referenz). Ist sie `Rigid=False` (flexibel - nötig, damit ihre eigenen
internen Joints/Rigid Groups überhaupt live mitgerechnet werden, siehe
[[project_fcproject_redundant_fixed_joint_rigidgroup_fix]]), überspringt sie die
Unterbaugruppe und läuft bis zum eigentlichen Teil durch (flache Referenz).

**2. `AssemblyLink::synchronizeComponents()`** (`src/Mod/Assembly/App/AssemblyLink.cpp`) -
das `objLinkMap`-Dictionary, über das `handleJointReference()` beim Spiegeln nach außen
externe Objekte auf lokale Kopien umbiegt, wird nur für die **direkten** Top-Level-
Komponenten der gespiegelten Baugruppe gefüllt - nie für Enkelkinder.

Zusammen: bei `Rigid=True` zeigt die Referenz von Anfang an nur auf ein direktes Kind
→ `objLinkMap`-Lookup trifft → Spiegeln funktioniert. Bei `Rigid=False` zeigt die
Referenz auf ein Enkelkind → `objLinkMap`-Lookup trifft nie → Referenz bleibt auf die
externe Quelldatei zeigen, der gespiegelte Joint wirkt nicht.

**Wichtig:** Beides sind offiziell gleichwertige, unterstützte Optionen beim Einfügen
einer Unterbaugruppe (Checkbox "als starre Baugruppe importieren"). Dass nur eine davon
bei weiterer Verschachtelung funktioniert, ist ein Bug, kein Bedienfehler.

## Minimal-Repro (`repro.py`)

Baut zwei winzige, eigenständige Dokument-Paare (Unterbaugruppe mit einem Teil,
eingebunden in eine Außenbaugruppe) - einmal mit `Rigid=True`, einmal mit `Rigid=False` -
und ruft `UtilsAssembly.getComponentReference()` mit identischer Auswahl-Situation
(`"SubLink.InnerPart.Face1"`) auf:

```
=== Rigid=True ===
  getComponentReference(...) -> component = SubLink, new_sub = 'InnerPart.Face1'
    -> KOMPAKT: zeigt auf SubLink selbst - Spiegeln nach aussen funktioniert.

=== Rigid=False ===
  getComponentReference(...) -> component = InnerPart, new_sub = 'Face1'
    -> FLACH: zeigt direkt auf InnerPart (Enkelkind) - objLinkMap beim Spiegeln kennt
       das nicht -> BUG.
```

Ausführen: `freecadcmd patches/bugreport-rigid-nested-joint-reference/repro.py`
(erzeugt temporäre `.FCStd`-Dateien unter `repro_docs/` im selben Ordner, nicht Teil des
Repros selbst - können nach dem Lauf gelöscht werden).

## Fix - noch offen

Zwei denkbare Ansatzpunkte, keiner bisher umgesetzt:

- **a) `handleJointReference()` mehrstufig machen:** wenn `objLinkMap.find(externalComponent)`
  fehlschlägt, die Eltern-Kette von `externalComponent` (`getInList()`) hochlaufen, bis ein
  Vorfahre gefunden wird, der in `objLinkMap` steckt - dann die Referenz analog zu
  `getComponentReference()`s eigener Logik auf diesen Vorfahren + zusammengesetzten
  `Sub`-Pfad umschreiben.
- **b) `objLinkMap` rekursiv befüllen:** beim Aufbau in `synchronizeComponents()` auch
  Enkelkinder (rekursiv durch verschachtelte `AssemblyLink`/`AssemblyObject`-Gruppen)
  eintragen, mit demselben lokalen Ziel wie ihr jeweiliger direkter Container.

Beide Varianten sind nicht trivial - der erste Live-Versuch an der eng verwandten
Rigid-Group-Variante (gleicher `objLinkMap`-Mechanismus, siehe
[[project_fcproject_redundant_fixed_joint_rigidgroup_fix]]) hat eine Regression
verursacht (Teile faelschlich zur Loeschung markiert, "out of scope"-Validierung). Vor
einem erneuten Versuch: nur an Kopien testen, nicht an echten Projektdateien - `freecadcmd`
allein reicht zur Verifikation nicht (siehe
[[project_fcproject_freecadcmd_zero_joints_cold_load]]), Struktur-Checks wie in `repro.py`
(reine Property-Inspektion nach `recompute()`, ohne auf wiederholte `solve()`-Läufe
angewiesen zu sein) sind aber zuverlässig.

## Offene Fragen / mögliche Nacharbeit

- Nicht bei FreeCAD upstream eingereicht (kein GitHub-Issue/PR bisher) - `repro.py` ist
  dafür vorbereitet.
- Ungeklärt, ob Variante (a) oder (b) der sauberere Fix ist, oder ob beide zusammen
  gebraucht werden (z.B. falls Enkelkinder selbst wieder Enkelkinder haben - 3+ Ebenen).
