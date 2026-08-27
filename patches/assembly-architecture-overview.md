# Assembly-Modul: Architektur-Überblick (Vorbereitung für einen echten Fix von Issue #32171)

Reine Recherche-/Dokumentationsarbeit, keine Code-Änderung. Ziel: ein verlässlicher Überblick
über die Architektur von `src/Mod/Assembly`, bevor in einer zukünftigen Sitzung versucht wird,
die Root Cause des "Nested-Flex-Joint-Detach"-Bugs
(https://github.com/FreeCAD/FreeCAD/issues/32171, lokal gespiegelt in
`patches/bugreport-nested-flex-joint-detach/README.md`) tatsächlich zu reparieren.

Kurzfassung der bereits gefundenen Root Cause (siehe verlinkter Bugreport für die volle
Herleitung, hier nur als Gedächtnisstütze):

1. `AssemblyLink::synchronizeJoints()` spiegelt beim Verschachteln Joints einer eingebetteten
   Baugruppe in die Elternbaugruppe über `assembly->getJoints(false, false)` - der zweite
   Parameter (`subJoints`) ist hier hart auf `false` gesetzt, Joints aus Enkel-Baugruppen (zwei
   oder mehr Ebenen tief) werden dadurch nie mit hochgespiegelt.
2. Mit `subJoints=true` erscheint der tiefe Joint zwar eine Ebene höher, wird aber von
   `AssemblyObject::isMbDJointValid()` als "selbstreferenzierend" verworfen, weil
   `getMovingPartFromRef()` (`AssemblyUtils.cpp`) nur das Top-Level-Objekt einer
   `PropertyXLinkSub`-Referenz liefert, nie deren Sub-Element-Pfad - beide Enden des tiefen
   Joints landen beim `findLocalAncestor()`-Fallback auf demselben Zwischen-Wrapper-Objekt.
3. Die dahinterliegende `objectPartMap`/`getMbDData()`-Struktur in `AssemblyObject.cpp` ordnet
   Teile rein über `App::DocumentObject*`-Pointer einem starren MbD-Körper zu - ganz ohne
   Sub-Pfad-Bewusstsein. Ein echter Fix bräuchte diese Struktur sub-pfad-bewusst (Schlüssel
   `(Objekt, Sub-Pfad)` statt nur `Objekt`).

Alle drei Punkte wurden beim Schreiben dieses Überblicks im aktuellen Code (Stand des lokal
gebauten `freecad-source`, inkl. aller eigenen Patches) noch einmal gegengelesen und bestätigt
gefunden - Belegstellen unten.

## 1. Hauptakteure

### 1.1 `Assembly::AssemblyObject` (`App/AssemblyObject.{h,cpp}`)

Die eigentliche Baugruppe - eine `App::Part`-Unterklasse, die zusätzlich als Fassade zum
Ondsel/MbD-Solver dient. Eine Instanz pro `Assembly::AssemblyObject`-Dokumentobjekt, d.h. **auch
jede verschachtelte Unterbaugruppe hat ihre eigene, komplett unabhängige `AssemblyObject`-Instanz**
mit eigenem `mbdAssembly`, eigener `objectPartMap` usw. - das ist der Kern des gesamten
Nested-Flex-Problems: es gibt keine gemeinsame, geteilte Solver-Welt über Verschachtelungsebenen
hinweg.

Wichtigste Zuständigkeiten/Methoden:

- `solve(bool enableRedo)` (Zeile 211): der eigentliche Solve-Lauf - `ensureIdentityPlacements()`
  → `syncGroundedJoints()` → `makeMbdAssembly()` (frisches `mbdAssembly`, `objectPartMap.clear()`)
  → `rebuildRigidClusters()`/`syncActiveRigidGroupPlacements()` → `fixGroundedParts()` →
  `getJoints(false, true, true)` → `removeUnconnectedJoints()` → `jointParts()` →
  `mbdAssembly->runPreDrag()` → `setNewPlacements()` → `redrawJointPlacements()`.
- `preDrag()`/`doDragStep()`/`postDrag()` (Zeilen 487, 532, 646): der interaktive Zieh-Pfad -
  siehe Abschnitt 2.5, entscheidend für den Bug.
- `getJoints()` (Zeile 1083): sammelt alle aktiven Joints dieser Baugruppe; mit `subJoints=true`
  (Default) rekursiv auch aus direkten `AssemblyLink`-Kindern (`getSubAssemblies()`, Zeile 2620) -
  aber nur, weil jede Sub-Assembly ihrerseits wieder mit Default-Parametern aufgerufen wird, siehe
  Abschnitt 3.
- `getMbDPart()`/`getMbDData()`/`objectPartMap` (Zeilen 129, 139, 278 in der `.h`; Implementierung
  ab Zeile 2408 in der `.cpp`): die Zuordnung "FreeCAD-Objekt → starrer MbD-Solver-Körper", inkl.
  Rigid-Group-Bündelung und (nur während `preDrag`/`bundleFixed=true`) automatischer Bündelung über
  Fixed-Joints. **Das ist die Struktur, die laut Root-Cause-Analyse sub-pfad-bewusst gemacht werden
  müsste** - Details in Abschnitt 3.
- `isMbDJointValid()` (Zeile 2378): der Selbstreferenz-Wächter, der einen Joint verwirft, wenn
  beide Enden auf denselben MbD-Körper abbilden - aktuell der sichtbare Symptomträger des Bugs.
- `rebuildRigidClusters()`/`getRigidRepresentative()`/`getRigidMembers()`/
  `syncActiveRigidGroupPlacements()`/`updateRigidPlacementCache()` (Zeilen 721-921): das
  RigidGroup-Feature (Union-Find über `RigidGroupJoint.ObjectsToRigidGroup`) - **echter
  FreeCAD-Upstream-Code** (siehe Abschnitt 4), keine eigene Arbeit.
- `getGroundedParts()`/`fixGroundedParts()`/`syncGroundedJoints()` (Zeilen 1320, 1380, 2669):
  Erdungs-Logik - ein Teil gilt als geerdet, wenn seine `Placement`-Property `ReadOnly` ist (nicht
  nur wenn ein `GroundedJoint` existiert); `syncGroundedJoints()` legt/löscht `GroundedJoint`-Objekte
  automatisch passend zu diesem ReadOnly-Zustand.
- `getConnectedParts()`/`traverseAndMarkConnectedParts()`/`removeUnconnectedJoints()`/
  `isPartConnected()` (Zeilen 1560-1673): Graph-Erreichbarkeit ausgehend von geerdeten Teilen -
  filtert Joints heraus, die nicht über eine Kette zu einem geerdeten Teil führen.

### 1.2 `Assembly::AssemblyLink` (`App/AssemblyLink.{h,cpp}`)

Der "Container", über den eine Baugruppe eine andere (Unter-)Baugruppe einbindet - ebenfalls eine
`App::Part`-Unterklasse, aber **kein** `AssemblyObject`: sie hat keinen eigenen Solver, sondern
zeigt über `LinkedObject` (ein `App::PropertyXLink`) entweder direkt auf ein `AssemblyObject` oder
auf eine weitere `AssemblyLink` (`getLinkedObject2(recursive)`, Zeile 1132/1154).

Zwei Betriebsmodi über die Property `Rigid` (`App::PropertyBool`):

- **Rigid=true**: die Unterbaugruppe verhält sich wie ein einziges starres Teil - Kinder werden
  1:1 gespiegelt und in `Placement` synchron gehalten (`synchronizeComponents()`), es gibt keine
  eigene `JointGroup` (`ensureNoJointGroup()`).
- **Rigid=false ("flexibel")**: die Unterbaugruppe bleibt intern beweglich - zusätzlich zu den
  Komponenten werden auch die Joints der Unterbaugruppe gespiegelt (`synchronizeJoints()`), damit
  die äußere Baugruppe sie mit-lösen kann. **Das ist der Modus, in dem der Nested-Flex-Bug
  auftritt**, und zwar erst ab zwei Ebenen von Rigid=false-Verschachtelung.

Wichtigste Methoden:

- `updateContents()` (Zeile 321): der zentrale Sync-Einstiegspunkt, aufgerufen aus `execute()`,
  `onChanged(Group)`, `onChanged(Rigid)`, `onDocumentRestored()`. Siehe Abschnitt 2.3.
- `synchronizeComponents()` (Zeile 349): gleicht die Kind-Objekte der Quell-Baugruppe (`Group`
  des gelinkten `AssemblyObject`/`AssemblyLink`) mit denen dieser `AssemblyLink` ab - legt fehlende
  `App::Link`/`Assembly::AssemblyLink`-Spiegel an, entfernt überzählige, pflegt dabei `objLinkMap`
  (Quellobjekt → lokaler Spiegel).
- `synchronizeJoints()` (Zeile 581): spiegelt Joints **positionsbasiert** (Index `i` in beiden
  Joint-Listen muss übereinstimmen) statt über eine stabile ID - ruft für `Reference1`/`Reference2`
  jeweils `handleJointReference()` auf. Nutzt `assembly->getJoints(false, false)` - **hier liegt
  Root-Cause-Punkt 1**.
- `handleJointReference()` (Zeile 971): bildet die externe Referenz (`prop1->getValue()`, ein
  direktes Kind der Quell-Baugruppe) über `objLinkMap` auf den lokalen Spiegel ab; findet sich kein
  direkter Treffer (Enkelkind-Fall), Fallback auf `findLocalAncestor()`.
- `findLocalAncestor()` (Zeile 1059, **eigener Patch**, siehe Abschnitt 4): läuft die
  Struktur-Eltern-Kette hoch, bis ein in `objLinkMap` bekannter Vorfahre gefunden wird, liefert den
  durchlaufenen Pfad als `Sub`-Präfix zurück. Genau dieser Fallback ist es, der beim
  `subJoints=true`-Experiment beide Enden eines tiefen Joints auf denselben Wrapper zusammenfallen
  ließ (Root-Cause-Punkt 2, siehe Bugreport).
- `synchronizeGroundedAndRigidJoints()`/`mapToLocalComponent()` (Zeilen 660, 932, **eigener Patch**,
  aktuell mit auskommentiertem Aufruf) - siehe Abschnitt 4.
- `updateParentJoints()` (Zeile 248): das Gegenstück beim Umschalten Rigid↔Flexibel - schreibt
  bestehende Joint-Referenzen in der **Elternbaugruppe** um (Kind→`this`+Präfix bzw. umgekehrt).

### 1.3 Joint-Proxy-Klassen (`JointObject.py`)

Python-`Proxy`-Objekte auf `App::FeaturePython`-Dokumentobjekten (das eigentliche C++-Objekt ist
generisch, die Fachlogik steckt komplett in Python).

- **`Joint`** (Zeile 183): die "normale", bewegliche Verbindung (Fixed/Revolute/Slider/Ball/...).
  Zentrale Properties: `JointType` (Enum, muss mit dem C++-`enum class JointType` in
  `AssemblyUtils.h` synchron bleiben), `Reference1`/`Reference2` (je ein `App::PropertyXLinkSub`,
  siehe 1.5), `Placement1`/`Placement2` (JCS relativ zum referenzierten Objekt), `Offset1`/`Offset2`,
  `Distance`/`Distance2`/`Angle`, diverse Limit-Properties. `setJointConnectors()` (Zeile 847)
  schreibt `Reference1`/`Reference2` aus einer Auswahl; `matchJCS()` (Zeile 928) positioniert das
  bewegliche Teil beim Erstellen/Bearbeiten eines Joints per Snap auf das Gegenstück (siehe auch
  Fix 7 in `patches/README.md` für einen bekannten Bug in genau dieser Funktion).
- **`GroundedJoint`** (Zeile 1457): kein "richtiger" Joint im MbD-Sinn - eine Property
  `ObjectToGround` (`App::PropertyLinkGlobal`, **kein** Sub-Pfad) markiert ein Teil als geerdet
  und setzt dessen `Placement` auf `ReadOnly`. Wird von `AssemblyObject::syncGroundedJoints()`
  automatisch angelegt/gelöscht, siehe 2.4.
- **`RigidGroupJoint`** (Zeile 1299, Teil des **Upstream**-RigidGroup-Features, siehe Abschnitt 4):
  `ObjectsToRigidGroup` (`App::PropertyLinkList`, ebenfalls **kein** Sub-Pfad) plus
  `RigidPlacements` (`App::PropertyPlacementList`, die beim Erstellen/Suspendieren eingefrorenen
  relativen Placements der Mitglieder zueinander, für Restore beim Reaktivieren).
- Gemeinsam: `GroundedJoint` und `RigidGroupJoint` referenzieren Ziele nur als ganze
  `App::DocumentObject*`, nie mit Sub-Element-Pfad - das ist genau der Grund, warum
  `AssemblyLink::synchronizeJoints()` (positionsbasiert, für `Reference1`/`Reference2` gedacht) sie
  gar nicht mitnehmen kann und eine eigene, zusätzliche Spiegel-Logik
  (`synchronizeGroundedAndRigidJoints()`) nötig war (siehe `patches/README.md`, "GroundedJoint/
  RigidGroupJoint verschwindet bei verschachtelter flexibler Baugruppe").

### 1.4 `App::Link` / `App::LinkGroup` (FreeCAD-Kern, `src/App/Link.{h,cpp}`)

Der allgemeine, nicht-Assembly-spezifische Link-Mechanismus, auf dem `AssemblyLink`/
`synchronizeComponents()` aufbaut: ein `App::Link`-Objekt zeigt über `LinkedObject`
(`App::PropertyLink`) auf ein beliebiges Objekt und übernimmt/überschreibt dessen `Placement`
lokal, ohne das Original zu verändern - die Grundlage für "ein Teil mehrfach in verschiedenen
Baugruppen mit unterschiedlicher Position verwenden". `isLinkGroup()`/`ElementList`/`ElementCount`
sind das Pendant für Arrays gleicher Objekte (z.B. Pattern/Vervielfältigung) - `AssemblyLink`
behandelt diese explizit gesondert (Abgleich über `ElementList`-Reihenfolge statt 1:1-Objektidentität,
siehe `synchronizeComponents()` Zeilen 419-437). `getLinkedObject(bool recurse)` löst rekursiv bis
zum tatsächlichen Ziel auf - wird von `AssemblyLink::mapToLocalComponent()` (eigener Patch) genutzt,
um verschiedene Kopien desselben PDM-Teils über Verschachtelungsebenen hinweg wiederzuerkennen.

### 1.5 `App::PropertyXLinkSub` (FreeCAD-Kern, `src/App/PropertyLinks.h`, ab Zeile 1414)

Der Referenz-Typ von `Joint.Reference1`/`Reference2`: erbt von `PropertyXLink` (das bereits
dokumentübergreifende Links erlaubt), fügt eine Liste von Sub-Element-Pfaden hinzu (`getSubValues()`
/`setSubValues()`, z.B. `"Body.Face1"`). Konzeptionell also **bereits sub-pfad-fähig** - das
Problem ist nicht die Property selbst, sondern dass der Assembly-Code beim Auflösen einer solchen
Referenz für Solver-Zwecke (`getMovingPartFromRef()`, s.u.) den Sub-Pfad-Teil ignoriert und nur
`prop->getValue()` (das Top-Level-Objekt) verwendet.

### 1.6 Freie Funktionen als Klebstoff (`AssemblyUtils.{h,cpp}`)

Kein eigener Zustand, reine Übersetzungsfunktionen zwischen "Referenz/Selektion" und "Objekt":

- `getObjFromRef()` (Zeile 522/619): löst eine `PropertyXLinkSub`-Referenz bis zum **tatsächlichen
  Sub-Feature** auf (z.B. der `PartDesign::Body` hinter einem Edge/Face) - für die JCS-Placement-
  Berechnung gedacht, nicht für Solver-Körper-Identität.
- `getMovingPartFromRef()` (Zeile 717/726): liefert **nur** `prop->getValue()` - das rohe
  Top-Level-Ziel der Referenz, ohne jede Sub-Pfad-Betrachtung. Das ist die Funktion aus
  Root-Cause-Punkt 2.
- `getMovingPartFromSel()` (Zeile 660): das Gegenstück für eine **live Nutzerauswahl** (Objekt +
  Sub-String aus der 3D-Pick-Interaktion, nicht aus einer gespeicherten Property) - läuft den
  Sub-Pfad tatsächlich Schritt für Schritt ab und **überspringt dabei bewusst flexible
  (Rigid=false) `AssemblyLink`-Zwischenstufen** (Zeilen 704-710), um bei der eigentlichen
  beweglichen Teil-Ebene anzukommen. **Bemerkenswerte Asymmetrie, bisher nicht dokumentiert**: es
  gibt im Code bereits eine funktionierende, sub-pfad-bewusste "finde das wirklich bewegliche Teil"-
  Logik - sie wird nur für live Auswahl in der Gui (`Gui/Commands.cpp:342`,
  `Gui/ViewProviderAssembly.cpp:825,893`) verwendet, nie für das Auflösen einer bereits
  gespeicherten Joint-Referenz. Ein echter Fix an `getMovingPartFromRef()` könnte plausibel densel-
  ben Gedanken (Sub-Pfad ablaufen, flexible Zwischen-Assemblies überspringen) wiederverwenden statt
  ihn neu zu erfinden.
- `getAssemblyComponents()` (Zeile 800): rekursive Ermittlung aller "wirklich beweglichen" Teile
  einer Baugruppe - steigt in flexible `AssemblyLink`s hinein, behandelt rigide als atomar. Wird u.a.
  von `getGroundedParts()` genutzt.

### 1.7 `AssemblyGui::ViewProviderAssembly` (`Gui/ViewProviderAssembly.cpp`)

Der ViewProvider zu `AssemblyObject` - **eine Instanz pro `AssemblyObject`**, genau wie beim
`AssemblyObject` selbst (1.1). Zuständig für 3D-Interaktion: Drag-Erkennung
(`canDragObjectIn3d()`), Drag-Modus-Bestimmung (`findDragMode()`), und den eigentlichen
Zieh-Ablauf `initMove()`/`mouseMove()`/`endMove()` (siehe Abschnitt 2.5).

## 2. Zentrale Abläufe

### 2.1 Neue Baugruppe/Teil einfügen (`CommandInsertLink.py`)

`TaskAssemblyInsertLink.onItemClicked()` (Zeile 358):

1. Objekttyp bestimmen: ein `Assembly::AssemblyObject` als Quelle → neues
   `Assembly::AssemblyLink`-Objekt; alles andere → normales `App::Link`
   (`self.assembly.newObject(objType, ...)`, Zeile 407-412).
2. `LinkedObject` auf das Quellobjekt setzen, `Placement` auf die Bildschirmmitte (mit einfacher
   Kollisions-/Versatz-Heuristik für Mehrfach-Einfügungen, Zeilen 430-452).
3. **Erst danach** `Rigid` setzen (Zeile 456-457) - Kommentar im Code erklärt bewusst: dadurch
   greift die Positions-Korrektur-Logik aus `AssemblyLink::onChanged(Rigid)` (Zeile 118 in
   `AssemblyLink.cpp`), die beim Umschalten auf Rigid die aktuelle Kind-Position in eine sinnvolle
   `movePlc` für den Container übersetzt, statt alles auf den Ursprung zurückzuwerfen.
4. Bei der allerersten Einfügung in eine noch ungeerdete Baugruppe: `handleFirstInsertion()`
   (Zeile 468) fragt (bzw. nutzt eine gespeicherte Präferenz) ob automatisch geerdet werden soll -
   bei einer flexiblen `AssemblyLink` wird dabei versucht, das intern bereits geerdete Teil der
   Quell-Baugruppe wiederzufinden (`srcGrounded`, Zeilen 507-533), sonst das erste greifbare Kind.
5. `accept()` (Zeile 148) baut die eigentlichen `newObject("App::Link", ...)`-Befehle als
   Makro-Text und führt sie über `Gui.doCommandSkip()` aus (damit sie im Undo-Stack als
   nachvollziehbare Skript-Zeilen landen, nicht als Rohtransaktion).

Das eigentliche `Assembly::AssemblyLink`-Objekt selbst wird also **nicht** über den generischen
`Gui.doCommand`-Pfad in 5. erzeugt (das betrifft nur normale `App::Link`s), sondern direkt in 1.
über `self.assembly.newObject(...)`.

### 2.2 Joint-Erstellung, Aufbau von Reference1/2

(`CommandCreateJoint.py`/`TaskAssemblyCreateJoint`, hier nicht im Detail gelesen, aber aus
`JointObject.py` und den bekannten Patches rekonstruierbar - siehe `patches/README.md` Fix 1-9 für
sehr detaillierte, live verifizierte Beobachtungen zu genau diesem Ablauf.)

1. Nutzer wählt zwei Referenzelemente (Kante/Fläche/Ursprungsachse) in der 3D-Ansicht oder im Baum
   aus - jede Auswahl ist ein `(Objekt, Sub-String)`-Paar, wobei das Objekt bei PDM-typischen
   Cross-Document-Referenzen ein `App::Link` in einem anderen Dokument sein kann.
2. `Joint.setJointConnectors()` (`JointObject.py` Zeile 847) schreibt daraus `Reference1`/
   `Reference2` (`App::PropertyXLinkSub.setValue(obj, [sub])`) sowie `Placement1`/`Placement2`
   (`findPlacement()`, die lokale JCS-Placement relativ zum referenzierten Objekt).
3. `execute()` (Zeile 825) validiert die Referenzen (u.a. der "Broken link"-Check aus Fix 4 in
   `patches/README.md` für den Fall einer noch nicht auflösbaren Cross-Document-Referenz direkt
   nach dem ersten Recompute).
4. Für den Solver relevant ist ab hier ausschließlich `getMovingPartFromRef()` (Abschnitt 1.6) -
   der Sub-String selbst wird nur für die JCS-Placement-Berechnung (`getObjFromRef()`) gebraucht,
   nicht für die "welcher starre Körper ist das"-Frage.

### 2.3 Verschachteln: `AssemblyLink::updateContents()`

Ausgelöst durch `execute()`, `onChanged(&Group)` (auch fremdausgelöst über `getInList()`, siehe
2.5-relevanter Reentrancy-Kommentar), `onChanged(&Rigid)`, `onDocumentRestored()`. Geschützt durch
den (eigenen, siehe Abschnitt 4) statischen `updatingContents`-Reentrancy-Guard.

```
updateContents()
 └─ synchronizeComponents()      // Kinder abgleichen, objLinkMap aufbauen
 └─ if Rigid:  ensureNoJointGroup()
    else:      synchronizeJoints()
                └─ assembly->getJoints(false, false)     // NICHT rekursiv -> Root Cause 1
                └─ pro Joint: doc->copyObject() oder vorhandenen Spiegel wiederverwenden
                └─ Properties kopieren (Distance, Offset1/2, Limits, ...)
                └─ handleJointReference(Reference1) / handleJointReference(Reference2)
                    └─ objLinkMap-Lookup (direktes Kind)
                        └─ Fallback: findLocalAncestor()   // Enkelkind -> Wrapper + Sub-Präfix
    // (synchronizeGroundedAndRigidJoints() hier auskommentiert, s. Abschnitt 4)
```

`synchronizeJoints()` gleicht **positionsbasiert** ab (Joint `i` der Quelle ↔ Joint `i` des
Spiegels) - es gibt keine stabile Identität zwischen Quell-Joint und gespiegeltem Joint außer der
Listenposition. Das ist für sich genommen fragil (Neuordnung/Löschen mittendrin verschiebt alle
nachfolgenden Indizes), aber nicht die hier untersuchte Root Cause - wird nur der Vollständigkeit
halber erwähnt, falls ein künftiger Fix in dieser Funktion ohnehin etwas umbaut.

### 2.4 Normaler Recompute / `solve()`

`AssemblyObject::execute()` (Zeile 129) ruft nach `App::Part::execute()` `solve(false)` auf, sofern
die Preference `SolveOnRecompute` aktiv ist (Standard: ja). Ablauf von `solve()` (Zeile 211, siehe
auch 1.1):

```
solve()
 ├─ ensureIdentityPlacements()      // LinkGroups müssen Identity-Placement haben
 ├─ syncGroundedJoints()            // GroundedJoint an/abgleichen mit Placement.ReadOnly
 ├─ mbdAssembly = makeMbdAssembly() // frische leere MbD-Welt
 ├─ objectPartMap.clear()
 ├─ rebuildRigidClusters()          // Union-Find über RigidGroupJoint-Mitgliedschaften
 ├─ syncActiveRigidGroupPlacements()
 ├─ groundedObjs = fixGroundedParts()   // -> leer? Abbruch (-6), sonst je 1 MbD-Fixed-Joint zum Weltursprung
 ├─ joints = getJoints(false, true, true)   // rekursiv (subJoints=true) + Verbose-Logging
 ├─ removeUnconnectedJoints(joints, groundedObjs)   // Graph-Erreichbarkeit ab geerdeten Teilen
 ├─ jointParts(joints)              // pro Joint: makeMbdJoint() -> isMbDJointValid() + getMbDData()
 ├─ mbdAssembly->runPreDrag()       // eigentlicher Ondsel/MbD-Solve
 ├─ setNewPlacements()              // objectPartMap zurück in FreeCAD-Placement-Properties schreiben
 └─ redrawJointPlacements(joints) + updateSolveStatus()
```

Wichtig: **jede** `AssemblyObject`-Instanz im Dokument (also auch jede über eine flexible
`AssemblyLink` eingebettete Unterbaugruppe) hat ihre eigene, komplett unabhängige `execute()`/
`solve()`-Kaskade - ein normaler Dokument-Recompute löst sie alle der Reihe nach aus (bestätigt im
Bugreport-Log: bei einem vollen Recompute lösen Sub → Top → GrandTop brav nacheinander). Das ist
der Grund, warum ein kompletter Recompute den Bug nicht zeigt, obwohl der zugrundeliegende
`objectPartMap`-Konstruktionsfehler (Root-Cause-Punkt 3) auch dort prinzipiell zuschlagen würde,
sobald ein Joint tatsächlich über `subJoints=true` in eine Elternbaugruppe hochgespiegelt würde.

### 2.5 Interaktives Ziehen vs. Recompute - warum nur die äußerste Baugruppe löst

Aus `AssemblyGui::ViewProviderAssembly` (Abschnitt 1.7):

- `initMove()` → `tryInitMove()` (Zeile 1040): ermittelt `dragMode`, blendet alle Joints außer dem
  gerade aktiven aus, und ruft `assemblyPart->preDrag(dragParts)` auf (Zeile 1127) - wobei
  `assemblyPart = getObject<AssemblyObject>()` (Zeile 1047) **das `AssemblyObject`-Dokumentobjekt
  ist, das zu genau diesem `ViewProviderAssembly` gehört**.
- `mouseMove()` (Zeile 468 ff.) ruft bei jedem Mausereignis `assemblyPart->doDragStep()` (Zeile
  626, oder `solve()` direkt bei aktivem Rigid-Group-Zwang, Zeile 623) auf derselben Instanz auf.
- `endMove()` (Zeile 1134) ruft `assemblyPart->postDrag()` (Zeile 1164) auf, wieder dieselbe
  Instanz.

Da es pro `AssemblyObject` genau eine `ViewProviderAssembly`-Instanz gibt, und FreeCADs
Gui-Schicht 3D-Mausereignisse während einer Drag-Operation an **den gerade aktiven/editierten**
ViewProvider weiterleitet (der über `Gui::ViewProvider::startEditing()`/`setEdit()` bestimmt wird -
siehe auch den verwandten Absturz-Fund in `patches/README.md`,
"freecad-assembly-viewprovider-null-crash.patch", der genau an dieser `setEdit()`-Stelle ansetzt),
bekommt bei einem Zieh-Vorgang **ausschließlich die aktuell aktive (typischerweise die äußerste)
Baugruppe** ihre `preDrag()`/`doDragStep()`/`postDrag()`-Aufrufe. Innere, über eine flexible
`AssemblyLink` eingebettete `AssemblyObject`-Instanzen haben zwar ihre eigene `ViewProviderAssembly`
und ihren eigenen `mbdAssembly`/`objectPartMap`-Zustand - der wird während dieses Drags aber
schlicht nie berührt, weil ihre `preDrag()`/`doDragStep()` nicht aufgerufen werden.

Das deckt sich exakt mit dem live rekonstruierten Befund im Bugreport (Log zeigt bei jedem
Zieh-Frame nur `Solving 'MinimalReproGrandTop#Assembly'`, nie die inneren Baugruppen) und erklärt,
warum ein Joint, der **innerhalb** einer zwei Ebenen tief eingebetteten Sub-Baugruppe lebt, beim
Ziehen von niemandem gehalten wird - es sei denn, er wurde (über `subJoints=true`,
Root-Cause-Punkt 1) erfolgreich in die äußerste Baugruppe hochgespiegelt, wo er dann aber an
Root-Cause-Punkt 2/3 scheitert.

Bei einem kompletten Dokument-Recompute (nicht Drag) läuft dagegen jede `AssemblyObject`-Instanz
über ihre eigene `execute()`/`solve()`-Kaskade (2.4) - deshalb hält der Slider-Joint dort formal,
das vorher durch den unbewachten Drag geschriebene falsche `Placement` wird aber nicht rückgängig
gemacht, weil kein Mechanismus ein von außen (per Drag) gesetztes `Placement` als "ungültig"
erkennt (`validateNewPlacements()`, Zeile 613, prüft nur, ob sich ein **geerdetes** Teil bewegt
hat - nicht, ob ein von einem inneren, nie aufgerufenen Solver gehaltenes Teil plausibel steht).

## 3. `objectPartMap`/`getMbDPart`/`getMbDData`/`getMovingPartFromRef` - Fundstellen-Katalog

Alle Verwendungsstellen in `AssemblyObject.cpp` (Datei implizit, nur Zeilen angegeben) plus die
beiden Definitionen in `AssemblyUtils.cpp`. Einschätzung bezieht sich auf einen Fix, der
`objectPartMap` (und alles, was von ihr abhängt) von `unordered_map<DocumentObject*, MbDPartData>`
auf einen sub-pfad-bewussten Schlüssel umstellt (z.B. `pair<DocumentObject*, std::string>` oder
einen kanonisierten `(WurzelObjekt, aufgelöster Pfad)`-Typ):

| Zeile(n) | Funktion | Nutzung von `objectPartMap`/verwandtem | Einschätzung für sub-pfad-bewussten Fix |
|---|---|---|---|
| 227 | `solve()` | `objectPartMap.clear()` | unkritisch, reine Lifecycle-Stelle |
| 409 | `generateSimulation()` | `objectPartMap.clear()` | unkritisch |
| 514-519 | `preDrag()` | iteriert alle Einträge, um `offsetPlc` eines gedraggten Teils zu finden | müsste auf neuen Schlüsseltyp umgestellt werden; Logik selbst (linearer Scan) bleibt gleich |
| 543, 555-557 | `doDragStep()` | `getMbDPart(part)`, Lookup von `offsetPlc` für Positions-Korrektur | direkt abhängig von der Schlüssel-Auflösung für `part` - **muss** wissen, mit welchem Sub-Pfad `part` gemeint ist, sonst bleibt das ursprüngliche Symptom (falsches/kollabiertes Teil) bestehen |
| 622-623 | `validateNewPlacements()` | Lookup von `mbdPart`/`offsetPlc` für ein geerdetes Teil | gleiches Muster, unkritischer da nur für geerdete (Top-Level-)Teile gedacht |
| 656 | `savePlacementsForUndo()` | iteriert alle Einträge (`pair.first` als Placement-Schlüssel) | unkritisch, reine Kopie |
| 710 | `exportAsASMT()` | `objectPartMap.clear()` | unkritisch |
| 925-947 | `setNewPlacements()` | iteriert alle Einträge, schreibt `Placement` zurück | **zentral**: hier muss die neue Placement pro (Objekt, Sub-Pfad)-Eintrag korrekt auf das tatsächlich gemeinte Teil zurückgeschrieben werden - bei mehreren verschiedenen Teilen, die versehentlich denselben Schlüssel hätten, würde dies aktuell nur eines der beiden falsch/gar nicht aktualisieren |
| 2200-2237 | `handleOneSideOfJoint()` | `getMbDData(part)` für Marker-Erzeugung je Joint-Seite | **zentral** - hier entscheidet sich, an welchem MbD-Körper der Marker für eine Joint-Seite hängt; mit Sub-Pfad-Bewusstsein müsste `part` hier das tatsächliche Enkelkind sein, nicht der Wrapper |
| 2261-2330 | `getRackPinionMarkers()` | `getMbDData(part1)` analog zu `handleOneSideOfJoint` | gleiche Einschätzung, Spezialfall Rack&Pinion |
| 2333-2376 | `slidingPartIndex()` | vergleicht `getMovingPartFromRef()`-Ergebnisse zweier Joints auf Objekt-Gleichheit | müsste auf den neuen (Objekt, Sub-Pfad)-Vergleich umgestellt werden, sonst können zwei verschiedene Enkelteile fälschlich als "gleiches Teil" erkannt werden |
| **2378-2406** | **`isMbDJointValid()`** | `getMbDPart(part1) == getMbDPart(part2)` | **der unmittelbare Bug-Symptomträger** - Vergleich zweier `shared_ptr<ASMTPart>`; muss nach dem Fix tatsächlich unterschiedliche Ergebnisse für zwei verschiedene Enkelteile liefern, die zufällig über denselben Wrapper aufgelöst wurden |
| **2408-2486** | **`getMbDData()`** | Kernstück: `objectPartMap.find(part)`, RigidGroup-Bündelung (`getRigidRepresentative`/`getRigidMembers`), `bundleFixed`-Fixed-Joint-Bündelung (`addConnectedFixedParts`, rekursiv über `getJointsOfPart()`) | **die eigentliche Umbaustelle** - hier müsste der Schlüsseltyp geändert und alle Konstruktions-/Lookup-Pfade (Rigid-Cluster, Fixed-Bündelung) entsprechend nachgezogen werden; die rekursive `addConnectedFixedParts`-Lambda nutzt ebenfalls `getMovingPartFromRef()`/`getJointsOfPart()` und wäre mitbetroffen |
| 2488-2493 | `getMbDPart()` | dünner Wrapper um `getMbDData(part).part` | folgt automatisch aus obigem |

`getMovingPartFromRef()` selbst (`AssemblyUtils.cpp` Zeilen 717 und 726) ist keine
`objectPartMap`-Konsumentin, sondern deren **Eingabe** - jede der folgenden Stellen ruft sie auf,
um überhaupt erst das `part1`/`part2`-Objekt zu bekommen, das dann bei `objectPartMap`
nachgeschlagen wird. Ein Fix muss zwingend **hier** ansetzen (Rückgabetyp von `(DocumentObject*)`
auf etwas wie `(DocumentObject* wurzel, std::string subPfad)` erweitern), sonst bleibt
`objectPartMap` weiterhin blind gefüttert:

| Zeile(n) | Funktion | Rolle |
|---|---|---|
| 1027-1028 | `getJointOfPartConnectingToGround()` | Identitätsvergleich `part == part1`/`part2` gegen ein übergebenes Teil |
| 1127-1129 | `getJoints()` | Selbstreferenz-Vorfilter (`part1->getFullName() == part2->getFullName()`) - **zweite Stelle mit demselben Symptom wie `isMbDJointValid()`**, aktuell nur textuell durch Logging sichtbar gemacht (FCPROJECT-PATCH 16), nicht behoben |
| 1311-1312 | `getJointsOfPart()` | Identitätsvergleich gegen ein übergebenes Teil |
| 1430 | `isJointConnectingPartToGround()` | wie oben |
| 1536-1537, 1593-1594 | `removeUnconnectedJoints()`/`getConnectedParts()` | Graph-Knoten-Identität für die Erreichbarkeits-Traversierung - zwei verschiedene Enkelteile, die auf denselben Wrapper kollabieren, würden hier als **ein** Knoten behandelt, was Konnektivität vortäuschen oder verschleiern kann |
| 2200, 2261, 2340, 2348-2349 | `handleOneSideOfJoint()`/`getRackPinionMarkers()`/`slidingPartIndex()` | s.o. |
| 2383-2384 | `isMbDJointValid()` | s.o. |

**Fazit dieses Abschnitts:** es gibt keine einzelne, isolierte Stelle, die repariert werden kann -
`getMovingPartFromRef()` ist die gemeinsame Wurzel, aber praktisch jede Solver-nahe Funktion in
`AssemblyObject.cpp`, die "welches Teil ist das eigentlich" fragt, hängt direkt oder indirekt
(über `objectPartMap`) daran. Das bestätigt die bereits im Bugreport dokumentierte Einschätzung,
dass Teil (b) (nur `isMbDJointValid()` reparieren) allein nicht ausreicht.

## 4. Eigene Patches vs. Upstream-Code

Um zu vermeiden, dass ein künftiger Fix-Versuch eigene, bereits laufende Vorarbeit für
"unbekannten Upstream-Code" hält (oder umgekehrt): alle eigenen Ergänzungen sind im Quellcode mit
`FCPROJECT-PATCH`-Kommentaren markiert und lassen sich per `grep -rn "FCPROJECT-PATCH"
src/Mod/Assembly` im lokalen `freecad-source`-Checkout vollständig auflisten. Zusammengefasst:

- **`AssemblyLink.h`/`AssemblyLink.cpp`** (Patch: `freecad-assembly-grounded-joint-nested-flex.patch`,
  vormals zwei getrennte Patches, siehe `patches/README.md`):
  - `static bool updatingContents`-Reentrancy-Guard um `updateContents()` (Header-Kommentar Zeilen
    128-146, Anwendung Zeilen 321-328) - **eigen**, behebt den "loeschfehler"-Hang.
  - `findLocalAncestor()` (Header Zeilen 78-90, Implementierung Zeilen 1059-1105) plus der
    Fallback-Aufruf in `handleJointReference()` (Zeilen 996-1002) - **eigen**, behebt die
    Enkelkind-Referenz-Regression bei Rigid=False-Verschachtelung (siehe
    `bugreport-rigid-nested-joint-reference`).
  - `synchronizeGroundedAndRigidJoints()`/`mapToLocalComponent()` (Header Zeilen 91-108,
    Implementierung Zeilen 660-968) - **eigen**, **aber der Aufruf in `updateContents()` ist
    auskommentiert** (Zeile 344: `// synchronizeGroundedAndRigidJoints();`) - toter Code ohne
    Laufzeitwirkung, siehe Warnhinweis in Abschnitt "Nächste Schritte" unten. Nicht mit
    aktivem Code verwechseln.
- **`AssemblyObject.h`/`AssemblyObject.cpp`** (Patch: `freecad-assembly-jointobject.patch`, Fixes
  10/11/13/14/15/16 laut `patches/README.md`):
  - `getJointContextName()`/`joinContextNames()` (anonymer Namespace, Zeilen 156-208) - **eigen**,
    reine Diagnose-Namensauflösung.
  - Die drei `Base::Console()`-Meldungen in `solve()` (Zeilen 220, 235-239, 279-325) - **eigen**,
    reine Logging-Ergänzung, keine Verhaltensänderung.
  - `verboseLog`-Parameter an `getJoints()` (Header Zeile 169, Implementierung Zeile 1083 sowie die
    `if (verboseLog)`-Blöcke Zeilen 1114-1173) und das Logging in `removeUnconnectedJoints()`
    (Zeilen 1518-1557) - **eigen**, reine Diagnose. **Wichtig für einen künftigen Fix**: dieses
    Logging ist die einzige aktuell vorhandene "sichtbare Beweisführung", dass ein Joint durch
    Selbstreferenz herausfällt - beim Testen eines echten Fixes lohnt es sich, `solve()` einmal mit
    aktivem Logging laufen zu lassen, um zu sehen, ob der vorher verworfene Joint jetzt tatsächlich
    "UEBERNOMMEN" wird.
  - `Origin.getValue()`-Nullprüfung in `getGroundedParts()` (Zeile 1357) - **eigen**, kleiner
    Cold-Load-Fix, unabhängig vom Nested-Flex-Thema.
  - `getJointContextName()`-Verwendung in `isMbDJointValid()`s Warnmeldung (Zeile 2401) - **eigen**
    (nur die Namensauflösung in der Meldung, **nicht** die Vergleichslogik selbst - `getMbDPart(part1)
    == getMbDPart(part2)` in Zeile 2390 ist unverändertes Upstream-Verhalten).
  - **Nicht eigen, reines Upstream** (Merge "Assembly: Add RigidGroup #29605", 11. Aug 2026):
    `rebuildRigidClusters()`, `getRigidRepresentative()`, `getRigidMembers()`,
    `syncActiveRigidGroupPlacements()`, `updateRigidPlacementCache()`, `getRigidGroups()`,
    `requiresRigidSolveForMove()`, die `rigidRepByPart`/`rigidMembersByRep`/`rigidPlacementCache`-
    Member sowie `RigidGroupJoint` in `JointObject.py` - **komplett fremder Code**, trotz
    thematischer Nähe (auch hier gibt es eine Objekt-zu-Objekt-Zuordnung ohne Sub-Pfad) nicht mit
    eigener Arbeit verwechseln.
- **`JointObject.py`** (Patch: `freecad-assembly-jointobject.patch`, Fixes 1-9): 17 kleinere, in
  `patches/README.md` einzeln sehr detailliert beschriebene Fixes (Cross-Document-Crash,
  `QuantitySpinBox`-Signal-Problem, Slider-`matchJCS()`-Kollaps-Bug, `getContext()`-Namensauflösung
  etc.) - **alle eigen**, aber **thematisch nicht mit dem Nested-Flex-Bug verwandt**. Für einen
  Fix an `objectPartMap`/`getMovingPartFromRef` vermutlich irrelevant, außer evtl. `matchJCS()`
  falls ein Fix auch das Positions-Snapping beim Joint-Erstellen innerhalb verschachtelter
  Baugruppen berührt.
- **`freecad-assembly-viewprovider-null-crash.patch`**: reine Absturz-Guards
  (`UpdateSolverInformation()`, `setEdit()`, `updateTaskPanel()` in `ViewProviderAssembly.cpp`) -
  **eigen**, aber komplett orthogonal zum Nested-Flex-Thema (Nullpointer-Checks nach
  Dokument-Reload).

**Zur Vorsicht bei einer Reaktivierung von `synchronizeGroundedAndRigidJoints()`**: dieser Code hat
live einen FreeCAD-Absturz verursacht (Reentrancy-Kaskade über `Base::Interpreter().runString()`-
Aufrufe beim Löschen einer verschachtelten `AssemblyLink`, siehe `patches/README.md`). Ein Fix am
`objectPartMap`-Kern (Abschnitt 3) ist davon **unabhängig** - beide Baustellen sollten nicht in
einem Rutsch angegangen werden, um die Fehlerquelle im Fall eines neuen Absturzes eindeutig
eingrenzen zu können.

## 5. Eigene Einschätzung: Aufwand und möglicher erster Schritt

**Größenordnung eines vollständigen Fixes: groß, mehrere Tage reine Entwicklungszeit plus
mindestens ebenso viel Testzeit.** Begründung:

- Es ist kein lokaler Bugfix, sondern eine Änderung an einer Kern-Datenstruktur
  (`objectPartMap`), die von praktisch jeder Solver-nahen Funktion in `AssemblyObject.cpp`
  gelesen/geschrieben wird (siehe die Fundstellen-Tabelle in Abschnitt 3 - mindestens 10 direkt
  betroffene Funktionen, dazu alle Aufrufer von `getMovingPartFromRef()`).
- Der neue Schlüsseltyp muss mit **mehreren bestehenden Konzepten gleichzeitig** kompatibel
  bleiben, die bereits heute über einfache `DocumentObject*`-Identität arbeiten und nicht ohne
  Kollateralschaden geändert werden dürfen: RigidGroup-Bündelung (Upstream-Feature, Abschnitt 4),
  die `bundleFixed`-Fixed-Joint-Bündelung beim Dragging (`getMbDData()`s
  `addConnectedFixedParts`-Lambda), und die Graph-Erreichbarkeit
  (`getConnectedParts()`/`traverseAndMarkConnectedParts()`).
- Zusätzlich zum reinen App-seitigen Fix müsste **auch Root-Cause-Punkt 1**
  (`AssemblyLink::synchronizeJoints()`s `getJoints(false, false)`) behoben werden, sonst erreicht
  ein tiefer Joint die äußere Baugruppe gar nicht erst - vermutlich `subJoints=true` plus eine
  entsprechende Anpassung an `handleJointReference()`/`findLocalAncestor()`, damit der
  Sub-Pfad-Präfix beim Spiegeln korrekt mitgeführt wird (aktuell wird er nur für die textuelle
  `Sub`-Liste der `PropertyXLinkSub` gepflegt, nicht für eine spätere Solver-Identität).
- Der interaktive Zieh-Pfad (Abschnitt 2.5: nur die äußerste Baugruppe löst) ist eine **dritte,
  im Prinzip unabhängige** Baustelle - selbst mit sub-pfad-bewusster `objectPartMap` und
  korrekt gespiegelten tiefen Joints würde ein Zug an einem Teil in der tiefsten Ebene weiterhin
  nur die äußerste `AssemblyObject`-Instanz lösen lassen. Ob das nach den ersten beiden Fixes
  überhaupt noch ein Problem ist (weil der tiefe Joint dann ja Teil der äußeren, tatsächlich
  lösenden Baugruppe wird), oder ob es weiterhin eine separate Lücke bleibt (z.B. für
  Simulationen/`generateSimulation()`, die pro `AssemblyObject`-Instanz einzeln laufen), ist noch
  nicht untersucht.
- Jede Änderung an dieser Codezone hat in der Vergangenheit bereits zweimal reale Abstürze
  produziert (`synchronizeGroundedAndRigidJoints()`-Reentrancy, siehe Abschnitt 4) - das spricht
  für einen vorsichtigen, in kleinen Schritten mit viel Live-Testing gegen echte verschachtelte
  Baugruppen (nicht nur das synthetische Minimal-Repro) abgesicherten Vorgehen, nicht für einen
  großen Umbau in einem Rutsch.
- Als reiner FreeCAD-Upstream-Bug (im unveränderten Weekly-AppImage bestätigt, siehe Bugreport)
  betrifft ein Fix zudem eine Codezone, die aktives Upstream-Entwicklungsziel ist (RigidGroup kam
  erst am 11. Aug 2026 dazu) - ein lokaler Fix müsste bei jedem `update-and-rebuild-freecad.sh`-Lauf
  gegen etwaige neue Upstream-Änderungen an denselben Funktionen erneut angepasst werden, ähnlich
  wie es beim RigidGroup-Merge bereits mit `freecad-assembly-jointobject.patch` passiert ist.

**Möglicher kleinerer, inkrementeller erster Schritt, der schon für sich genommen Wert liefert:**

Statt sofort `objectPartMap` selbst umzubauen, zunächst **nur** Root-Cause-Punkt 1 + eine reine
**Erkennungs**-Verbesserung an Root-Cause-Punkt 2 angehen, ohne den Joint tatsächlich lösbar zu
machen:

1. `synchronizeJoints()` auf `subJoints=true` umstellen (kleiner, lokal begrenzter Eingriff in
   `AssemblyLink.cpp`), damit tiefe Joints wenigstens strukturell in der äußeren Baugruppe
   ankommen.
2. `isMbDJointValid()` (und den bereits vorhandenen, bisher rein diagnostischen Vorfilter in
   `getJoints()`, Zeilen 1127-1148) so erweitern, dass bei einer erkannten Selbstreferenz **auch
   der jeweils andere, tatsächlich beteiligte Sub-Pfad** mit ausgegeben wird (aus
   `prop->getSubValues()` der beiden `Reference`-Properties) - macht den bereits bestehenden
   Warnhinweis "conflicting or redundant constraint" für Nutzer und Entwickler erkennbar als "das
   ist eigentlich kein echter Konflikt, nur eine bekannte Solver-Einschränkung", ohne den Joint
   scharf zu schalten.

Das liefert **kein** funktionierendes Verhalten (der Joint bleibt weiterhin unwirksam), aber:

- es macht das aktuell stillschweigende Verwerfen für jeden Nutzer/Entwickler sofort sichtbar und
  eindeutig einem bekannten, dokumentierten Sonderfall zuordenbar (statt einer generischen
  "redundant constraint"-Meldung, die nach einem Modellierungsfehler aussieht),
- es ist mit dem heutigen `objectPartMap`-Schema (reine `DocumentObject*`-Schlüssel) vollständig
  kompatibel - kein Risiko für die bereits stabilen RigidGroup-/Fixed-Bündelungs-Pfade,
  entsprechend deutlich risikoärmer zu testen,
  und liefert nebenbei bereits die Diagnose-Infrastruktur (Sub-Pfad-Extraktion aus
  `PropertyXLinkSub`), die ein späterer vollständiger `objectPartMap`-Umbau ohnehin bräuchte.

Der eigentliche, funktionale Fix (sub-pfad-bewusste `objectPartMap` + entsprechend erweiterte
`getMovingPartFromRef()`) bliebe damit als klar abgegrenzter, separater zweiter Schritt bestehen -
mit dann bereits vorhandener, in der Praxis erprobter Sub-Pfad-Extraktion aus Schritt 2 als
Baustein.

## Fix-Konzept: Adressieren statt Kopieren

Nutzer-Vorgabe wörtlich: *"AssemblyLink (flexibel) versucht, interne Joints eine Ebene nach oben zu
kopieren (`synchronizeJoints()`) - genau da sitzt der ganze Bug-Komplex. Bessere und bessere
Abbildung von verschachtelten Joints: ADRESSIEREN statt KOPIEREN!"*

Reine Konzept-/Recherchearbeit, keine Code-Änderung. Alle unten zitierten Zeilennummern wurden beim
Schreiben dieses Abschnitts im lokal gebauten `freecad-source` gegengelesen.

### 0. Vorab: was genau heute kopiert wird

`AssemblyLink::synchronizeJoints()` (`AssemblyLink.cpp`, Zeile 581-645) tut wörtlich das:

```cpp
std::vector<App::DocumentObject*> assemblyJoints = assembly->getJoints(false, false);  // Zeile 591
...
auto ret = doc->copyObject({joint});   // Zeile 607 - ECHTE neue Joint-DocumentObject-Instanz
...
handleJointReference(joint, lJoint, "Reference1");   // Zeile 636 - Referenz umschreiben
handleJointReference(joint, lJoint, "Reference2");   // Zeile 637
```

Jede Verschachtelungsebene legt also ein **physisch eigenständiges** `Joint`-Dokumentobjekt an
(`doc->copyObject()`), das eigene `Reference1`/`Reference2`-Properties trägt, die (über
`handleJointReference()`/`findLocalAncestor()`) auf den jeweils *lokalen* Spiegel-Wrapper
umgeschrieben werden. Der Abgleich ist zudem **positionsbasiert** (Index `i` in
`assemblyJoints`/`assemblyLinkJoints` muss übereinstimmen, Zeile 600) statt über eine stabile
Identität. Genau diese Kopie-Kette ist es, die laut Root-Cause-Punkt 1-3 (Kurzfassung oben)
irgendwann kollidiert oder Information (den echten Sub-Pfad) verliert.

Wichtig für das Folgende: `AssemblyObject::getJoints()` hat mit `subJoints=true` (Default seit dem
bereits vorgeschlagenen kleinen ersten Schritt, s.o.) bereits einen Rekursionspfad in
`getSubAssemblies()` (Zeile 1178-1189) - aber der ruft aktuell `assembly->getJoints()` auf, wobei
`assembly` vom Typ `AssemblyLink*` ist. Das ist **nicht** die 3-Parameter-Methode von
`AssemblyObject` (Zeile 1083), sondern die separate, parameterlose `AssemblyLink::getJoints()`
(`AssemblyLink.cpp` Zeile 1181-1188), die schlicht die **bereits kopierten** Joints aus der
*eigenen* `JointGroup` der `AssemblyLink` zurückgibt. Der Rekursionspfad liest also heute
ausschließlich Kopien, nie das Original tiefer unten. Das ist die konkrete Stelle, an der
"adressieren statt kopieren" ansetzen müsste.

### 1. Konkretes Adressierungsformat

Kein neues Format nötig - FreeCAD hat für genau dieses Problem (mehrstufige Objekt-Verschachtelung)
bereits eine Konvention, und der Assembly-Code nutzt sie an einer Stelle schon korrekt:

- **`Base::Tools::splitSubName()`** (`src/Base/Tools.cpp` Zeile 345-364) zerlegt einen
  Punkt-getrennten String wie `"Part.Part001.Body.Pad.Edge1"` in eine Liste von
  Namensegmenten - dieselbe Konvention, mit der `App::PropertyXLinkSub`/`PropertyXLink` ihre
  `getSubValues()`/`setSubValues()` (`PropertyLinks.h` Zeile 946, 1360, 4738-4745 in
  `PropertyLinks.cpp`) bereits arbeiten: **ein Wurzelobjekt (`prop->getValue()`) + ein
  Punkt-getrennter Sub-String, der beliebig viele Zwischenobjekte durchläuft**, nicht nur ein
  einzelnes Geometrie-Element.
- **`getMovingPartFromSel()`** (`AssemblyUtils.cpp` Zeile 660-715) nutzt exakt dieses Format bereits
  für Verschachtelung über mehrere `AssemblyLink`-Ebenen hinweg - und zwar nicht nur lesend: der
  Aufrufer baut den String beim Abstieg selbst zusammen. `ViewProviderAssembly::collectMovableObjects()`
  (`Gui/ViewProviderAssembly.cpp` Zeile 851-893) hängt bei jeder rekursiv durchquerten
  `AssemblyLink`-Ebene ein weiteres Namenssegment an (Zeile 867:
  `std::string newSubNamePrefix = subNamePrefix + child->getNameInDocument() + "."`) - bei zwei
  verschachtelten flexiblen `AssemblyLink`s entsteht so z.B. `"AssemblyLink1.AssemblyLink2.Box2."`,
  aufgelöst relativ zu einem `selRoot`, der meist das äußerste `AssemblyObject` selbst ist.

**Vorschlag:** Eine "Joint-Adresse" ist exakt dieses bereits existierende Paar
`(App::DocumentObject* wurzel, std::string subPfad)` - **keine neue Datenstruktur**, sondern die
konsequente Fortsetzung dessen, was `Reference1`/`Reference2` als `PropertyXLinkSub` schon heute
lokal (innerhalb der Baugruppe, in der der Joint tatsächlich lebt) speichern. Der einzige
Unterschied zu heute: der Sub-Pfad-String, den eine *äußere* Baugruppe zur Auflösung braucht, ist
nicht der in `Reference1.getSubValues()[0]` gespeicherte lokale String selbst, sondern dieser lokale
String **mit einem vorangestellten Präfix aus den Namen der durchquerten `AssemblyLink`-Objekte**
(`"AssemblyLink1.AssemblyLink2." + localSub`) - dieses Präfix entsteht rein aus der
Container-Struktur (wer enthält wen), nicht aus einer neu zu erfindenden Syntax. Eine strukturierte
Liste von `(AssemblyLink, lokaler Name)`-Paaren (die in der Aufgabenstellung als Alternative genannt
wird) wäre computational äquivalent, aber unnötig - der Punkt-String ist bereits das, was
`PropertyXLinkSub` nativ speichert/exportiert/im XML persistiert (`exportSubName()`/`importSubName()`,
`PropertyLinks.cpp` Zeile 1662, 1764), eine eigene Listenstruktur müsste zusätzlich eine eigene
Serialisierung bekommen, ohne einen erkennbaren Vorteil zu bieten.

### 2. Wiederverwendung von `getMovingPartFromSel()`

Der Kern der Funktion (Zeile 672-714), Segment für Segment abgelaufen:

```cpp
auto names = Base::Tools::splitSubName(sub);
names.insert(names.begin(), obj->getNameInDocument());
bool assemblyPassed = false;
for (const auto& objName : names) {
    obj = doc->getObject(objName.c_str());
    if (!obj) continue;
    if (obj->isLink()) doc = obj->getLinkedObject()->getDocument();       // Zeile 683-685
    if (obj == assemblyObject) { assemblyPassed = true; continue; }        // Zeile 687-691
    if (!assemblyPassed) continue;
    if (obj->isDerivedFrom<App::DocumentObjectGroup>()) continue;          // Zeile 696-698
    if (obj->isLinkGroup()) continue;                                      // Zeile 700-702
    if (obj->isDerivedFrom<Assembly::AssemblyLink>()) {                    // Zeile 705-710
        const auto* pRigid = obj->getPropertyByName<App::PropertyBool>("Rigid");
        if (pRigid && !pRigid->getValue()) continue;   // <-- GENAU DAS wird gebraucht
    }
    return obj;
}
```

Die für "adressieren statt kopieren" entscheidende Zeile ist **705-710**: eine flexible
(`Rigid=false`) `AssemblyLink`-Zwischenstufe wird beim Ablaufen des Pfads einfach **übersprungen**
(`continue`) statt zurückgegeben - der Pfad läuft transparent durch sie hindurch bis zum tatsächlich
beweglichen Teil dahinter. Genau dieses Verhalten fehlt `getMovingPartFromRef()` (Zeile 717-734)
komplett: die Funktion kennt gar keinen Pfad, nur `prop->getValue()` (das Wurzelobjekt), und bricht
dort sofort ab.

**Übertragbarkeit auf gespeicherte Referenzen - drei relevante Unterschiede, keiner davon
grundsätzlich:**

1. `getMovingPartFromSel()` bekommt `obj`+`sub` als **fertigen, vollständigen Pfad ab Dokumentwurzel**
   übergeben (vom Aufrufer in der Gui zusammengebaut, s.o.). Eine gespeicherte `Reference1` kennt nur
   ihren **lokalen** Sub-String relativ zur Baugruppe, in der der Joint tatsächlich als Dokumentobjekt
   lebt - nicht das Präfix der äußeren `AssemblyLink`-Kette, die ihn ggf. gerade einbindet (ein und
   derselbe Joint könnte im Prinzip von mehreren verschiedenen äußeren Ebenen aus adressiert werden,
   je nachdem, wie tief er verschachtelt gerade ist). Das Präfix muss also **von außen mitgegeben**
   werden, nicht aus der `Reference1`-Property selbst rekonstruiert werden.
2. `getMovingPartFromSel()` nimmt `assemblyObject` (die aktuell lösende `AssemblyObject`-Instanz) als
   expliziten Parameter, um zu wissen, ab wo der Pfad überhaupt "zählt" (`assemblyPassed`-Gate,
   Zeile 675, 687-691). `getMovingPartFromRef(App::DocumentObject* joint, const char* pName)`
   (Zeile 726-734) hat aktuell **keinen** `AssemblyObject*`-Parameter - das müsste ergänzt werden
   (mechanisch unproblematisch: jeder heutige Aufrufer ist bereits eine Member-Funktion von
   `AssemblyObject`, `this` ist überall verfügbar, siehe Fundstellen-Katalog Abschnitt 3).
3. `getMovingPartFromSel()` gibt nur das **Zielobjekt** zurück, keinen aufgelösten Sub-Pfad - für die
   reine "wohin ziehen" Frage reicht das. Ein adressierungsbasierter Ersatz für
   `getMovingPartFromRef()` müsste zusätzlich den **verbleibenden, tatsächlich aufgelösten Sub-Pfad**
   mit zurückgeben (nicht nur das Objekt), weil genau dieser fehlende Sub-Pfad die Wurzel von
   Root-Cause-Punkt 2/3 ist (`objectPartMap` kennt aktuell nur Objekt-Identität). Rückgabetyp müsste
   also von `App::DocumentObject*` auf ein Paar/Struct `{DocumentObject* obj; std::string subPath;}`
   erweitert werden.

**Konkreter Ansatzpunkt für eine neue Auflösungsfunktion:** eine neue Funktion in
`AssemblyUtils.{h,cpp}`, z.B. `resolveJointReference(const AssemblyObject* solvingAssembly,
App::DocumentObject* joint, const char* pName, const std::string& nestingPrefix)`, die

- `prop = joint->getPropertyByName<PropertyXLinkSub>(pName)` liest (wie bisher),
- den vollen Adress-String `nestingPrefix + prop->getValue()->getNameInDocument() + "." +
  prop->getSubValues()[0]` bildet (Wurzel = `solvingAssembly` statt `obj` aus der Selektion),
- und dann **denselben Segment-für-Segment-Walk** wie oben (Zeile 672-714) durchläuft - idealerweise
  durch Extraktion dieser Schleife in eine gemeinsame private Hilfsfunktion, die sowohl von
  `getMovingPartFromSel()` (interaktive Selektion) als auch von der neuen
  `resolveJointReference()` (gespeicherte Referenz + Verschachtelungs-Präfix) genutzt wird, statt die
  Logik ein zweites Mal zu duplizieren.

`nestingPrefix` selbst entsteht genau dort, wo aktuell die Kopier-Rekursion sitzt: in
`AssemblyObject::getJoints()`s `subJoints`-Zweig (Zeile 1178-1189). Statt (wie heute)
`assembly->getJoints()` auf der `AssemblyLink` (= gespiegelte Kopien lesen) aufzurufen, müsste dort
**in die tatsächliche verlinkte `AssemblyObject`-Instanz hinabgestiegen** werden (`getLinkedAssembly()`,
bereits vorhanden in `AssemblyLink.cpp` Zeile 584, dort schon für den heutigen Kopiervorgang genutzt)
und bei jedem Abstieg ein weiteres `AssemblyLink`-Namenssegment an `nestingPrefix` angehängt werden -
strukturell identisch zu dem, was `collectMovableObjects()` in der Gui bereits tut (s.o.), nur einmal
zentral im App-Layer statt bei jeder interaktiven Auswahl neu.

### 3. Auswirkung auf `getJoints()`, `isMbDJointValid()`, `objectPartMap`/`getMbDData()`

**`getJoints()`** (Zeile 1083-1192): der `subJoints`-Zweig (1178-1189) ändert seine Datenquelle
grundlegend - von "lies kopierte Joint-Objekte aus der `AssemblyLink`-eigenen `JointGroup`" zu "lies
die Original-Joint-Objekte direkt aus der verlinkten `AssemblyObject`-Instanz, rekursiv, mit
mitgeführtem `nestingPrefix`". Der Rückgabetyp `std::vector<App::DocumentObject*>` reicht dafür nicht
mehr aus, weil ein und dasselbe Original-Joint-Objekt (Pointer-Identität) je nachdem, über welchen
`AssemblyLink`-Pfad man es erreicht, ein *anderes* Präfix bräuchte (relevant z.B. wenn dieselbe
Sub-Baugruppe über zwei verschiedene `AssemblyLink`-Instanzen eingebunden ist - ein durchaus
bestehender, heute schon unterstützter Fall). Realistisch müsste `getJoints()` auf einen Rückgabetyp
wie `std::vector<std::pair<App::DocumentObject*, std::string /*nestingPrefix*/>>` (oder ein kleines
`JointRef`-Struct) umgestellt werden - **eine Signaturänderung, die alle Aufrufer betrifft** (`solve()`
Zeile 284, `removeUnconnectedJoints()`, `jointParts()`, die rekursiven `getJointsOfPart()`-Aufrufe
u.a., siehe Fundstellen-Katalog Abschnitt 3).

**`isMbDJointValid()`** (Zeile 2378-2406): ruft aktuell zweimal `getMovingPartFromRef(joint, ...)`
ohne Kontext auf (Zeile 2383-2384) und vergleicht `getMbDPart(part1) == getMbDPart(part2)`
(Zeile 2390). Müsste zu `resolveJointReference(this, joint, "Reference1", nestingPrefix)` bzw.
`"Reference2"` wechseln (das `nestingPrefix` muss also bis hierhin durchgereicht werden - entweder
als zusätzlicher Parameter an `isMbDJointValid(joint, nestingPrefix)`, oder implizit über den oben
vorgeschlagenen `JointRef`-Rückgabetyp von `getJoints()`, den `jointParts()` dann Schritt für Schritt
weiterreicht) und danach **`getMbDPart()` mit dem vollen `(obj, subPath)`-Paar** aufrufen statt nur
mit `obj` - die reine Vergleichslogik selbst (`==`) bleibt unverändert, nur der verglichene
Schlüsseltyp wird reichhaltiger.

**`objectPartMap`/`getMbDData()`** (`AssemblyObject.h` Zeile 134-139, 278; `.cpp` Zeile 2408-2486):
der Schlüsseltyp der `unordered_map` müsste von `App::DocumentObject*` auf ein
`std::pair<App::DocumentObject*, std::string>` (Wurzelobjekt + aufgelöster Sub-Pfad) oder einen
eigenen kanonisierten Typ mit passendem `std::hash`-Spezialisierung wechseln - das ist exakt die
schon in Abschnitt 3/5 (oben) beschriebene, als "groß" eingeschätzte Umbaustelle. Das Adressierungs-
Konzept **ersetzt diese Umbaustelle nicht**, es liefert ihr nur einen **korrekten, verlustfreien
Eingabewert** (den vollen Sub-Pfad statt nur eines Top-Level-Objekts) - vorher lief diese Umbaustelle
ins Leere, weil `getMovingPartFromRef()` den Pfad gar nicht erst zur Verfügung hatte. Alle in der
Fundstellen-Tabelle (Abschnitt 3) als "zentral" markierten Zeilen (`handleOneSideOfJoint()`,
`getRackPinionMarkers()`, `slidingPartIndex()`, `setNewPlacements()`) bleiben in ihrer Umbaugröße
unverändert - der Unterschied ist nur, **woher** ihr `part`-Argument jetzt kommt.

**Wann eine Adresse aufgelöst werden sollte:** analog zum bestehenden Lebenszyklus von
`objectPartMap` selbst (das an denselben drei Stellen geleert wird: `solve()` Zeile 227,
`generateSimulation()` Zeile 409, `exportAsASMT()` Zeile 710 laut Fundstellen-Tabelle) - **nicht** bei
jedem einzelnen Zugriff neu (das würde bei jedem `doDragStep()`-Mausereignis erneut den kompletten
Pfad-Walk wiederholen, mit demselben CPU-Kostenproblem, das schon beim Verbose-Logging in Fix 16
beobachtet wurde, siehe Header-Kommentar Zeile 162-167 in `AssemblyObject.h`), sondern:

1. **Einmalig beim Aufbau von `getJoints()`** innerhalb von `solve()`/`preDrag()`/
   `generateSimulation()` - das ist ohnehin der einzige Ort, an dem das `nestingPrefix` durch den
   rekursiven Abstieg in `getSubAssemblies()`/`getLinkedAssembly()` überhaupt natürlich anfällt.
2. Das Ergebnis (der aufgelöste `(obj, subPath)`-Schlüssel pro Joint-Seite) wird zusammen mit dem
   Joint durch die restliche `solve()`-Kette (`jointParts()` → `makeMbdJoint()` →
   `handleOneSideOfJoint()`/`isMbDJointValid()`/`getMbDData()`) **mitgeführt statt neu aufgelöst** -
   entweder über den oben vorgeschlagenen erweiterten `getJoints()`-Rückgabetyp, oder (weniger
   invasiv, aber mit doppelter Buchführung) über einen zusätzlichen Cache
   (`std::unordered_map<std::pair<DocumentObject*, std::string /*pName*/>, ResolvedRef>`, analog
   zu `objectPartMap` als weiteres Member) - beide Varianten laufen strukturell auf dasselbe hinaus,
   der Rückgabetyp-Weg ist sauberer, der Cache-Weg ist ein kleinerer Diff.
3. **Invalidierung:** an genau denselben drei Stellen, an denen heute schon `objectPartMap.clear()`
   steht (s.o.) - eine Struktur-Änderung (Objekt hinzugefügt/gelöscht/verschoben, `AssemblyLink`
   umgeschaltet Rigid↔Flexibel) löst ohnehin einen Recompute/neuen `solve()`-Lauf aus, der diese
   Stellen durchläuft. Ein zusätzlicher, eigener Invalidierungsmechanismus wäre nur nötig, falls der
   Cache-Ansatz (Punkt 2, zweite Variante) über eine einzelne `solve()`-Ausführung hinaus leben soll -
   davon wird abgeraten, da eine kurzlebige, pro-Solve-Instanz gültige Auflösung deutlich weniger
   Fehlerpotential hat als ein langlebiger Cache mit eigener Invalidierungslogik (siehe die bereits
   dokumentierte Vorsicht bei `synchronizeGroundedAndRigidJoints()`, Abschnitt 4 - jede zusätzliche
   zustandsbehaftete Struktur in dieser Codezone hat sich bisher als Absturzrisiko erwiesen, sobald sie
   über Reentrancy-Grenzen hinweg gültig bleiben soll).

### 4. Migrationspfad

**Was sich am Speicherformat eines einzelnen Joints NICHT ändert:** `Reference1`/`Reference2`
bleiben ganz normale `App::PropertyXLinkSub`, mit demselben lokalen `(Wurzelobjekt, Sub-String)`-Wert
wie heute - ein Joint speichert weiterhin nur seine *lokale* Referenz, relativ zu der Baugruppe, in
der er als Dokumentobjekt lebt. Es gibt also **kein neues XML-Property-Format zu migrieren** und
keine Änderung an `JointObject.py`s `setJointConnectors()`.

**Was komplett entfällt:** die gesamte Kopier-Maschinerie in
`AssemblyLink::synchronizeJoints()`/`handleJointReference()`/`findLocalAncestor()`
(`AssemblyLink.cpp` Zeile 581-645, 971-1105) - eine flexible `AssemblyLink` bräuchte unter
"adressieren statt kopieren" **gar keine eigene `JointGroup`-Population mehr**, genau wie eine
*rigide* `AssemblyLink` heute schon keine eigene `JointGroup` führt (`ensureNoJointGroup()`,
`AssemblyLink.cpp` Zeile 1107ff., aufgerufen aus `updateContents()` Zeile 333 im Rigid-Zweig). Der
naheliegende Migrationsschritt ist deshalb wörtlich: **denselben `ensureNoJointGroup()`-Aufruf, der
heute nur im Rigid-Zweig von `updateContents()` steht, auch im Flexibel-Zweig aufrufen**, sobald
`synchronizeJoints()` durch die adressierungsbasierte Auflösung ersetzt ist.

**Bereits gespeicherte, kopierte Joint-Objekte in existierenden Projektdateien:** das ist der
eigentlich heikle Teil. Eine gespiegelte Kopie ist im Dokument von einem "echten" Joint aktuell
**nicht unterscheidbar** - `doc->copyObject()` (Zeile 607) erzeugt ein vollwertiges Joint-Objekt
gleichen Typs, ohne Markierung "ich bin eine Kopie von X". Drei Optionen:

1. **Nichtstun / Toleranz:** alte Kopien bleiben einfach als normale, eigenständige Joint-Objekte in
   der `AssemblyLink`-eigenen `JointGroup` liegen. Sobald `ensureNoJointGroup()` (s.o.) beim nächsten
   `updateContents()`-Lauf für diese `AssemblyLink` greift, würden sie beim Aufräumen ohnehin gelöscht
   (`ensureNoJointGroup()` entfernt per Definition alle Inhalte der `JointGroup`) - **das passiert
   also praktisch automatisch beim ersten Laden/Recompute unter neuem Code**, ohne eigenen
   Migrationscode. Voraussetzung: `ensureNoJointGroup()` muss tatsächlich robust mit "JointGroup
   enthält Joints, die gerade noch von `getJoints()`/`solve()` gebraucht werden" umgehen - dafür
   reicht die bestehende Reihenfolge (`synchronizeComponents()` → Rigid/Flexibel-Zweig → nächster
   `solve()`-Lauf danach) vermutlich aus, wäre aber ein konkreter Testfall für die Umsetzung.
2. **Aktive Erkennung einer "verwaisten" Kopie:** wäre nur nötig, falls Nutzer bereits manuell
   Properties an einer kopierten Instanz verändert haben (z.B. `Suppressed` umgeschaltet) - dann
   würde Option 1 diese Änderung stillschweigend verwerfen. Da Joint-Properties laut
   `synchronizeJoints()` (Zeile 616-633) ohnehin bei jedem Sync von der Quelle überschrieben werden
   (Kopien sind heute schon nie eigenständig editierbar, jede manuelle Änderung an einer Kopie würde
   beim nächsten `updateContents()`-Lauf zurücküberschrieben), ist dieses Risiko in der Praxis gering
   - Option 1 dürfte ausreichen.
3. Kein Bedarf für einen expliziten Versions-/Formatwechsel-Marker im Dokument, da das alte Verhalten
   (Kopien in der `AssemblyLink`-`JointGroup`) und das neue Verhalten (keine Kopien, nur Adressierung)
   sich nicht gleichzeitig um dieselben Daten "streiten" - die alte `JointGroup` wird einfach geleert,
   nicht umgeschrieben.

**Schrittweise statt Alles-oder-Nichts - mit einer wichtigen Einschränkung:** global inkrementell
(z.B. "nur neu erstellte Joints nutzen Adressierung, alte weiter kopieren") ist **nicht sinnvoll
möglich**, weil `getJoints()`s `subJoints`-Zweig (Abschnitt 3) pro `AssemblyLink`-Kind entscheiden
muss, ob er dessen `JointGroup` liest (alter Weg) oder in die verlinkte `AssemblyObject`-Instanz
hinabsteigt (neuer Weg) - **beide gleichzeitig für dieselbe `AssemblyLink` anzuwenden würde jeden
Joint doppelt liefern** (einmal als Kopie, einmal als adressiertes Original) und damit einen neuen,
selbstgemachten "redundant constraint"-Fehler erzeugen. Der Umbau ist also **pro einzelner
`AssemblyLink`-Instanz atomar** (entweder ganz alt oder ganz neu für genau dieses eine
Verschachtelungs-Objekt), aber **zwischen verschiedenen `AssemblyLink`-Instanzen im selben Dokument
unabhängig** - eine Datei mit drei verschachtelten Unterbaugruppen könnte während der Umstellung
z.B. zwei bereits migrierte und eine noch alte `AssemblyLink` enthalten, ohne dass sich das
gegenseitig stört (jede löst unabhängig über ihre eigene `AssemblyObject`-Instanz, siehe
Abschnitt 1.1). Praktisch heißt das: die Umstellung lässt sich gut hinter einem Feldkennzeichen an
der `AssemblyLink` selbst gestaffelt einführen (z.B. vorübergehend geprüft anhand des
FreeCAD-Dateiversions-Attributs beim Laden), ist aber **kein** Feature, das man Joint für Joint
einzeln umschalten könnte - die kleinste sinnvolle Migrationseinheit ist eine `AssemblyLink`.

### 5. Aufwands-/Risiko-Vergleich zum bereits dokumentierten kleinen ersten Schritt

**Größenordnung:** mindestens so groß wie der bereits in Abschnitt 5 (oben) grob geschätzte "große"
`objectPartMap`-Umbau (mehrere Tage Entwicklung + mindestens ebenso viel Testzeit) - "adressieren
statt kopieren" **ist keine dritte, zusätzliche Option neben "kleiner Schritt" und "großer
`objectPartMap`-Umbau"**, sondern **der große Umbau selbst, nur mit einem saubereren Ausgangspunkt**:
er liefert dem ohnehin nötigen `objectPartMap`-Schlüsselwechsel (Abschnitt 3, oben) den fehlenden,
korrekten Eingabewert (vollständiger Sub-Pfad statt bloßem Top-Level-Objekt) und macht zusätzlich
Root-Cause-Punkt 1 (`synchronizeJoints()`s fehlende Rekursionstiefe) durch **Streichen** der
betroffenen Kopier-Logik gegenstandslos, statt sie separat zu reparieren (`subJoints=true` allein,
wie im kleinen ersten Schritt vorgeschlagen, wäre bei "adressieren statt kopieren" gar nicht mehr
nötig - es gibt dann keine `AssemblyLink`-eigene `JointGroup` mehr, deren Rekursionstiefe man
anpassen müsste).

**Warum es trotzdem grundsätzlich sauberer/dauerhafter ist statt nur "genauso groß, anders
verteilt":**

- Es beseitigt eine **ganze Fehlerklasse ursächlich** statt sie nachträglich abzufangen: die
  positionsbasierte Index-Kopplung in `synchronizeJoints()` (Zeile 600, oben in Abschnitt 2.3 als
  "für sich genommen fragil" vermerkt), der `findLocalAncestor()`-Kollisionsfall
  (Root-Cause-Punkt 2), und - laut `MEMORY.md` bereits als eigener, vom Nutzer als "echter Bug, nicht
  nur kosmetisch" eingestufter offener Punkt dokumentiert - die **`GroundedJoint`-Vervielfachung**
  (`syncGroundedJoints()` legt für dasselbe Teil wiederholt neue `GroundedJoint`-Objekte an) sowie das
  bereits **live abgestürzte** `synchronizeGroundedAndRigidJoints()` (Abschnitt 4, oben) sind alle drei
  **Symptome derselben Grundursache "Kopieren statt Adressieren"** - auch `GroundedJoint`/
  `RigidGroupJoint` referenzieren ihre Ziele nur über nackte `App::DocumentObject*`
  (`App::PropertyLinkGlobal`/`PropertyLinkList`, Abschnitt 1.3) und bräuchten für eine korrekte
  Abbildung über `AssemblyLink`-Grenzen hinweg im Kern dieselbe Pfad-Auflösung wie `Reference1`/
  `Reference2` - ein Adressierungs-Fix an der einen Stelle würde also plausibel **alle drei
  Baustellen gemeinsam** entschärfen, statt sie einzeln und wiederholt zu flicken.
- Es reduziert langfristig **Code**, statt ihn zu vermehren: die komplette Kopier-/
  Property-Sync-Maschinerie in `synchronizeJoints()`/`handleJointReference()`/`findLocalAncestor()`
  (rund 165 Zeilen, `AssemblyLink.cpp` Zeile 581-645 + 971-1105) entfällt ersatzlos, während der
  "kleine erste Schritt" (`subJoints=true` + Diagnose) diese Maschinerie unverändert weiterleben
  lässt und der spätere `objectPartMap`-Umbau zusätzlichen Code obendrauf legen müsste.
- Es ist **weniger** anfällig für Kollisionen mit Upstream-Änderungen an genau dieser Codezone
  (RigidGroup kam laut Abschnitt 4 erst am 11. Aug 2026 dazu, ist also aktives Entwicklungsziel) -
  eine Streichung von Code braucht bei einem Merge-Konflikt typischerweise weniger Handarbeit als das
  Nachziehen einer parallel gewachsenen Kopier-Logik.

**Warum es trotzdem NICHT der empfohlene nächste Schritt ist, sondern der bereits dokumentierte
kleine erste Schritt zuerst kommen sollte:**

- Der kleine erste Schritt ist mit dem **heutigen** `objectPartMap`-Schema vollständig kompatibel
  (Abschnitt 5, oben: "kein Risiko für die bereits stabilen RigidGroup-/Fixed-Bündelungs-Pfade") -
  "adressieren statt kopieren" ist es nicht: es ändert den `objectPartMap`-Schlüsseltyp, den
  `getJoints()`-Rückgabetyp und entfernt eine seit Langem laufende, mehrfach live gehärtete
  Kopier-Pipeline in einem Zug. Jede dieser drei Änderungen einzeln ist schon nicht trivial risikofrei
  (siehe die zweifache Absturzhistorie in Abschnitt 4) - alle drei gemeinsam in einer Sitzung zu
  verifizieren ist unrealistisch.
- Der kleine erste Schritt liefert **sofort** nutzbaren diagnostischen Mehrwert (sichtbare, korrekt
  zugeordnete Warnmeldung) mit sehr geringem Testaufwand. Ein Adressierungs-Umbau liefert erst am
  Ende der gesamten Kette (`getJoints()` + `resolveJointReference()` + `objectPartMap`-Schlüsselwechsel
  + Migration) überhaupt ein sichtbares, testbares Ergebnis - es gibt keinen sinnvollen
  Zwischenzustand, den man isoliert gegen echte Baugruppen testen könnte, ohne mindestens Abschnitt 2
  und 3 gemeinsam umzusetzen.

**Sinnvoller Zwischenweg:** genau der in Abschnitt 5 (oben) bereits vorgeschlagene - **zuerst** der
kleine erste Schritt (subJoints=true + Diagnose-Erweiterung um den jeweils anderen Sub-Pfad aus
`getSubValues()`), **weil** dessen zweiter Teilschritt ("Sub-Pfad-Extraktion aus `PropertyXLinkSub`")
exakt die Bausteine liefert, die `resolveJointReference()` (Abschnitt 2, oben) ohnehin braucht -
danach, mit dieser bereits in der Praxis erprobten Extraktion als Fundament, **schrittweise** in
Richtung Adressierung: zuerst `resolveJointReference()` + gemeinsame Walk-Hilfsfunktion (Abschnitt 2)
isoliert am 3-Boxen-Minimal-Repro bauen und verifizieren, **danach erst** den
`objectPartMap`-Schlüsselwechsel (Abschnitt 3) und zuallerletzt das Entfernen der Kopier-Pipeline
samt Migration (Abschnitt 4) - in dieser Reihenfolge, weil jeder Zwischenschritt für sich weiterhin
mit der bestehenden Kopier-Pipeline koexistieren kann (die neue Auflösungsfunktion kann parallel
zur alten `getMovingPartFromRef()` existieren und an einer einzelnen, klar abgegrenzten Stelle wie
`isMbDJointValid()` zuerst nur *zusätzlich* zur Diagnose genutzt werden, bevor sie den bisherigen
Aufruf tatsächlich ersetzt) - und erst der letzte Schritt (Kopier-Pipeline entfernen) den in
Abschnitt 4 beschriebenen "atomar pro `AssemblyLink`"-Charakter hat, der keinen weiteren
Zwischenzustand erlaubt.
