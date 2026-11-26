1. In einem Datei nur ein Objekt (Part, Assambly, Halbzeug)
   Gilt für die eigenen PDM-Artikel (Dateiname = ArticleID = Label; Umbenennen, Nummern,
   Teiletausch hängen an der Datei). Seit 2026-11-24 kommen die Werkzeuge aber auch mit Dateien
   zurecht, die mehrere Objekte enthalten (fremde/importierte Dateien): Schnitt-Sketch ordnet den
   Link nach Objekt zu (`_find_top_level_link_for`), DocObserver fragt dann nicht nach dem
   Umbenennen, RetrofitLCS rüstet alle PDM-Objekte nach, die Import-Komponente lässt wählen.
   Test: `tests/fc_multi_object_file_check.py`.
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
1. **Beim Ersatzteil-Referenz-Klick (PartExchange) wird bei Fehlschlag nur GENAU EINE Ebene
höher gesucht, nicht beliebig weit.** Wird als Ersatzteil ein einzelnes internes
PartDesign-Feature gewählt (z.B. "BaseFeature" statt des ganzen Body - bewusst zulässig,
kann in Konstruktion benutzt werden), soll eine später am selben Body hinzugefügte
Geschwister-Referenz (z.B. eine neue Bohrung "Pocket") trotzdem als gültig erkannt werden.
`PartExchangeAnalyzer.find_reference_root_and_path()` versucht deshalb bei Fehlschlag GENAU
EINMAL den direkt umschließenden `getParentGeoFeatureGroup()` (Body/Part) als Ersatz-Root -
kein Schleifen-Aufstieg über mehrere Ebenen. Findet sich das Element auch dort nicht, gilt
die Referenz als ungültig ("gehört nicht zu").
1. **Beim Umbenennen eines Part/Assembly-Objekts (RenamePartCommand) wird nur INNERHALB des
eigenen PROJ_-Ordners automatisch repariert.** `rename_pdm_object()` findet projektweite
Referenzen zwar über denselben Mechanismus wie PartExchange
(`PartExchangeAnalyzer.find_external_project_references()`), passt davon aber NUR die
Kandidaten an, deren Pfad innerhalb des per `find_project_root()` ermittelten PROJ_-Ordners
liegt. Wird dasselbe Teil auch in einem ANDEREN Projekt verwendet, bleibt diese Verlinkung
bewusst unangetastet (siehe TODO.md, 2. Prio: dafür soll stattdessen Hilfe zur manuellen
Reparatur angeboten werden) - ein automatischer Eingriff über Projektgrenzen hinweg ist
ausdrücklich nicht gewünscht.
1. **Alle eigenen Feature-/Command-Module werden in `InitGui.py` SOFORT beim Programmstart
importiert (`_import_feature_modules()`, direkt nach `FreeCADGui.addWorkbench(...)`), nicht
mehr erst beim ersten Aktivieren der FCProject-Werkbench.** Grund (2026-11-08): eine neue
FreeCAD-Kernpruefung (`App::PropertyPythonObject::isAllowedModule()`) blockiert beim Laden
eines Dokuments den automatischen Import eines Proxy-Moduls (z.B. `SectionSketchFeature` fuer
ein `App::FeaturePython`-Objekt), wenn dieses Modul noch nicht in `sys.modules` steht UND sein
Dateipfad nicht auf FreeCADs eigener Positivliste (`FreeCAD.__ModDirs__`) steht - was im Sandbox-
Profil (`Mod/FreeCAD-Development` ist ein SYMLINK auf dieses Repo) wegen des dadurch aufgeloesten
realen Pfads der Fall ist. `Workbench.Initialize()` laeuft aber erst beim ERSTEN Aktivieren der
Werkbench - wurde vorher ein Dokument mit eigenen FCProject-Objekten geladen (z.B. direkt beim
Programmstart via Kommandozeile/Datei-Historie, ohne die Werkbench zu wechseln), schlug das
Laden dieser Objekte fehl ("blocked import of module ... Only modules from FreeCAD or installed
addons are permitted"). Da `InitGui.py` laut FreeCAD-Log fuer JEDES installierte Addon ohnehin
schon beim Programmstart per `exec()` ausgefuehrt wird, reicht es, den Import dort direkt
(ausserhalb der Klasse) aufzurufen - das Modul steht dann schon vor jedem Dokument-Laden in
`sys.modules`, was laut `isAllowedModule()` IMMER erlaubt ist, unabhaengig vom Pfad-Check.
`Initialize()` ruft dieselbe Funktion zusaetzlich weiterhin auf (billiges No-Op dank Python-
Modul-Cache), falls der Start-Import aus irgendeinem Grund nicht geklappt haben sollte.
1. **Jeder direkte STEP-Datei-Import im PDM-Creator (Typ P "Halbzeug" per Datei, Typ B
Kaufteil) folgt der GLOBALEN FreeCAD-Einstellung "Zusammensetzung von Objekten"
(`Edit → Einstellungen → Import-Export → STEP`, intern `UseLinkGroup`) - es wird KEINE eigene
Import-Option erzwungen.** `PartCreator.py`/`PurchasedPartCreator.py` rufen `Import.insert()`
ohne zusätzliche Parameter auf; ob der Importer dabei eine flache Objektliste oder eine
Link-Gruppen-/Baugruppenstruktur mit eigenen Origins erzeugt, hängt also vom jeweils aktiven
FreeCAD-Profil ab und kann sich zwischen Maschinen/Profilen unterscheiden. Funktional
unkritisch: `PurchasedPartCreator._collect_solids_from_refs()`/`_solids_from_shape()` holen
sich die Volumenkörper unabhängig von der Struktur (live mit UseLinkGroup aktiv UND inaktiv
getestet, Typ P 2026-11-06) - nur das Aussehen des (danach wieder verworfenen bzw. zu einem
einzelnen Body reduzierten) Zwischenergebnisses variiert.
1. **Schnitt-Sketch: Ordner, Teilschnitte und Gesamtschnitt entstehen auf DOKUMENTEBENE, nicht in der
Baugruppen-Gruppe** (Nutzerwunsch 2026-11-11, erweitert 2026-11-24). Gründe:
(a) *Zyklus:* hängt die Referenz selbst von der Baugruppe ab (typisch eine Datum-Ebene mit
`AttachmentSupport = (Baugruppe, 'Origin.XZ_Plane.')`), ergibt Baugruppe → (Group) Schnitt → Datum-Ebene →
Baugruppe einen Zyklus: FreeCAD meldet bei jedem Recompute "The graph must be a DAG", alle Beteiligten
bleiben "still touched after recompute".
(b) *Phantom-Erdungen:* die an die Referenz angehefteten Sketches haben eine schreibgeschützte Placement
(`AttachExtension` setzt das bei jedem Recompute/Laden neu), und `AssemblyObject::syncGroundedJoints()` erdet
jedes GeoFeature der Baugruppen-Gruppe mit schreibgeschützter Placement ohne Erdung - pro Sketch ein eigener
GroundedJoint (live beobachtet 2026-11-24 in `CNC_STK_003_A_Steuerbox`: GroundedJoint für jeden
Teilschnitt und den Gesamtschnitt). Grundsatz des Nutzers: geerdet wird nur die Schnittebene, die Sketches
sind daran gebunden (angeheftet) und brauchen keine eigene Erdung. Ausserhalb der Gruppe sieht der Solver
die Sketches nicht.
Umgesetzt in `SectionSketchFeature._section_belongs_in_assembly()`; die Kinder folgen immer dem Ordner.
**Einschränkung:** Ausserhalb der Gruppe fehlt die eigene Placement der Baugruppe (GeoFeatureGroups wenden sie
kumulativ auf Mitglieder an), deshalb gilt das nur bei Identity-Placement der Baugruppe - sonst bleibt der
Schnitt in der Gruppe, es gibt eine Warnung, und (a)/(b) treten auf. Bestehende Schnitte werden nicht
umgezogen. Alternative gegen (a): Datum-Ebene direkt an das Ursprungs-Ebenen-Objekt anheften
(`AttachmentSupport = [(Origin.XZ_Plane-Objekt, "")]`), nicht an die Baugruppe + Unterelement.
1. **Binder im Teil auf Geometrie aus der Baugruppe, die dieses Teil einbaut, nur als Sync-Binder**
(Nutzerauftrag 2026-11-26). Ein normaler SubShapeBinder mit `Support`/`Context` auf die Baugruppe
erzeugt einen Kreis über die Dateien (Teil → Baugruppe → Teil, "Document::getDependentDocuments: The
graph must be a DAG"), keine Bindungsart vermeidet das. Der Sync-Binder (`SyncBinder.py`, Befehle
"Sync-Binder anlegen" / "Sync-Binder aktualisieren") ist ein normaler, synchronisierter Binder auf ein
verstecktes Halte-Objekt in DERSELBEN Teil-Datei (`<Binder>_SyncQuelle`), `Relative = False`, ohne
Context; die Quelle steht nur als Text (`SyncDatei`, `SyncObjekt`, `SyncPfad`, `SyncQuellen`). Die
Baugruppe rechnet von oben nach unten: nach jedem Neuberechnen schreibt sie die Quellgeometrie in der
gelösten Lage (auch durch verschachtelte Unterbaugruppen/Spiegel) in Body-Koordinaten der Teil-Instanz
in das Halte-Objekt (`Synchronisiert`, Standard an; sonst nur per Befehl). Teilweise geladene
Teil-Dateien werden dafür vollständig nachgeladen (FreeCAD speichert Änderungen an ihnen sonst nicht).
"Sync-Binder aktualisieren" wandelt normale Binder mit Context auf die aktive Baugruppe auf Nachfrage
um; Verweise von Skizzen auf Binder-Elemente bleiben erhalten. Beim Ziehen mit der Maus folgt der
Binder erst nach dem Loslassen. Wird das Teil allein geöffnet, lädt der Sync-Binder (wie die
Verknüpfung eines normalen Binders) die Baugruppe unsichtbar mit und aktualisiert sich sofort; fehlt die
Baugruppen-Datei, bleibt die zuletzt kopierte Form.
Test: `tests/fc_sync_binder_check.py`.
