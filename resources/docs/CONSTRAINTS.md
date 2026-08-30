1. In einem Datei nur ein Objekt (Part, Assambly, Halbzeug)
1. Pattern Objekte: Part, Body, Assembly, Link, oder Elemente mit Shape.
1. Beim suchen links fü Joints sind nur erste LCS zulässig, es wird weiter nicht gesucht.
Es wird der erste direkte Outlink genommen, der ein ECHTES `App::LocalCoordinateSystem` ist (siehe
`AssemblyPatternCreator._is_real_lcs()`). Der automatische `App::Origin`-Container jedes
Objekts zählt seit 2026-08-17 bewusst NICHT mehr mit, obwohl er in FreeCAD selbst technisch von
`App::LocalCoordinateSystem` erbt (`App::Origin: public App::LocalCoordinateSystem`) - er wurde vorher
fälschlich als LCS-Treffer gegriffen und führte bei verschachtelten Baugruppen zu kryptischen
"Sub-object ... Origin.Origin not found"-Konsolenwarnungen beim Pattern (siehe
[[project_fcproject_assembly_pattern_origin_lcs_bug]]). Findet sich gar kein echtes LCS, wird das
Joint für dieses Element jetzt mit einer klaren Warnung übersprungen, statt eine stillschweigend
falsche Identity-Referenz zu verwenden. Pattern vom Pattern (verschachtelte Baugruppen ohne eigenes
LCS) funktioniert dadurch weiterhin nicht zuverlässig - siehe nächster Punkt.
1. **Jedes PDM-Objekt (Typ P/A/R/G/B) soll beim Erstellen ein ECHTES `App::LocalCoordinateSystem`
bekommen** (nicht nur den automatischen `App::Origin`-Container), damit Pattern/Joints eine
verlässliche Referenzgeometrie zum Andocken haben, auch wenn das Objekt verschachtelt (nicht
top-level) verwendet wird - u.a. damit sich auch aus Baugruppen (Typ A) heraus patternen lässt.
**Seit 2026-08-17 umgesetzt**: `Utils.add_local_coordinate_system()` legt ein `Part::
LocalCoordinateSystem` (Identity-Placement, Label "LCS") im jeweiligen Root-Container an - wird von
allen fünf Creatorn (`PartCreator.py`/P, `AssemblyCreator.py`/A, `RAWCreator.py`/R,
`GeometryCreator.py`/G, `PurchasedPartCreator.py`/B) direkt vor dem Speichern aufgerufen.
1. In einem Datei eine Baugruppe
1. **Beim Part/Assembly-Tausch (PartExchange) wird auf Verlinkung INNERHALB DES GESAMTEN
PROJEKTS gesucht, nicht nur in gerade geöffneten Dokumenten.** FreeCADs eigener
"Objektabhängigkeiten"-Warndialog beim Löschen kennt nur GERADE GEÖFFNETE Dokumente - eine
Baugruppe, die ein zu ersetzendes/löschendes Teil direkt referenziert, aber selbst nicht offen
ist, würde dort ungewarnt durchrutschen (Nutzer-Report 2026-08-30). **Umgesetzt**:
`PartExchangeAnalyzer.find_external_project_references()` durchsucht alle `.FCStd`-Dateien im
Projektordner (Konvention: nächster `PROJ_`-Ordner in der Verzeichnis-Hierarchie, siehe
`find_project_root()`) direkt als ZIP nach dem internen Namen des Original-Objekts - ohne die
Dateien selbst zu öffnen, funktioniert also auch für nicht geladene Dokumente. Ergebnis wird im
PartExchange-Fenster als rote Warnung angezeigt, blockiert aber nichts automatisch - der Nutzer
entscheidet selbst, ob er trotzdem fortfährt.
