Draft vs. Assembly: Draft-Arrays werden standardmäßig im Root-Verzeichnis des Dokuments erstellt. Befindet sich das Basis-Objekt in einer Unterbaugruppe (App::Part), führt dies zu Koordinaten-Versätzen. Das Array muss zwingend in denselben Part-Container verschoben werden wie sein Basis-Objekt.
## Verknüpfungen in FreeCAD (Abhängigkeiten)

### 1. Die `.Base` Eigenschaft
Viele Werkzeuge (Draft Array, PartDesign Mirrored, PartDesign LinearPattern) erstellen ein neues Objekt, das ein anderes Objekt als Grundlage nutzt. Diese Grundlage wird intern fast immer in der Eigenschaft `.Base` gespeichert.
- **Wichtig:** Das Array-Objekt ist vom Basis-Objekt abhängig. Wenn sich das Basis-Objekt ändert, aktualisiert sich das Array.

### 2. Links vs. Direkte Objekte
In Assemblies arbeiten wir oft mit `App::Link`. Ein Link ist nur ein "Zeiger" auf ein echtes Objekt.
- Wenn ein Array einen Link als Basis nutzt, zeigt `array.Base` auf den Link.
- Um das eigentliche Bauteil zu finden, muss man `array.Base.LinkedObject` abfragen.

### 3. InList vs. OutList
Um im Baum zu navigieren, nutzt man:
- `obj.InList`: "Wer benutzt mich?" (Zeigt nach oben im Baum zu den Eltern/Containern).
- `obj.OutList`: "Wen benutze ich?" (Zeigt nach unten zu den Kindern/Abhängigkeiten).

### 4. Workflow-Umkehr
 Es ist effizienter, vom abhängigen Objekt (Array) auf das Quell-Objekt (Base) zu schließen, um die Ziel-Hierarchie zu bestimmen. obj.Base ist der Schlüssel, um die logische Zusammengehörigkeit in komplexen Assemblies zu wahren.

 Selection-Handling: Gui.Selection.getSelection() gibt ein Listen-Objekt zurück. Auch bei Einzelwahl muss über den Index [0] auf das eigentliche Objekt zugegriffen werden, um Attribute wie .Label, .Name oder .Base nutzen zu können.

 Robustheit bei Dokumentzugriffen: Der Zugriff auf App.ActiveDocument sollte immer validiert werden (if not doc:). In komplexen Baugruppen-Operationen ist es zudem ratsam, openTransaction() und commitTransaction() zu nutzen, um die Datenintegrität während des Verschiebens zu sichern und Recompute-Fehler zu minimieren.
 
 Verschieben in Container (Matrix-Fix): Wenn ein Objekt in ein App::Part verschoben wird, muss seine Platzierung von Welt-Koordinaten in lokale Koordinaten umgerechnet werden (ParentInverse * WorldPlacement). Ohne diese Korrektur bleibt das Objekt im Status "Touched", da die Assembly-Logik und die Objekt-Logik widersprüchliche Positionen berechnen wollen.

 Client-Kritik: Wenn ein logisch korrektes Makro in einer Datei versagt, in einer neuen aber funktioniert, liegt das oft an korrupten internen Abhängigkeits-Graphen (DAG) der alten Datei. In FreeCAD 1.1 hilft es oft, die Struktur in einem frischen Dokument neu aufzubauen, anstatt gegen "Geister-Fehler" zu kämpfen.

 Shape-Explosion: Wenn getPlacements nur ein Element liefert, kann man über obj.Shape.Compounds auf die Platzierungen der tatsächlichen Geometrie-Kopien zugreifen. Dies ist besonders bei Draft-Arrays wichtig, die auf Expand Array = False stehen, da sie ihre Kopien in einem einzigen Compound-Objekt „verstecken“.
 
 ## Label-Degradierung: 
 In FreeCAD 1.1 ist das Label leider nicht mehr nur ein reiner "Anzeigename" (wie in Creo), sondern wird von der GUI als Sekundär-Index missbraucht. Das macht das Label für die Stückliste (BOM) unzuverlässig, da die GUI es eigenmächtig ändert. 

 