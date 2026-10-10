Hauptsächlich bearbeitet mit [Claude Code](https://claude.com/claude-code) (Anthropic).


# FCProject

FreeCAD-Workbench für Projektmanagement, Stücklisten (BOM) und Assembly-Werkzeuge rund um
strukturierte PDM-Projekte.

Installation über den FreeCAD Addon Manager: **Bearbeiten → Einstellungen → Addon-Manager →
Eigene Repositories** → `https://github.com/maxx04/FreeCAD-Development` (Branch `main`)
eintragen. Der eigentliche Workbench-Code liegt im Unterordner [`python/`](python/) (siehe
`package.xml`), der Rest dieses Repos enthält daneben persönliche FreeCAD-Patches/-Notizen, die
mit der Workbench selbst nichts zu tun haben.

## Werkzeuge (Symbolleiste "FCProject Tools")

| Werkzeug | Zweck |
|---|---|
| Projekt initialisieren | Erstellt eine strukturierte PDM-Umgebung und setzt das Arbeitsverzeichnis |
| PDM-Teil erstellen | Erstellt eine neue, strukturierte Bauteil-Datei |
| Stückliste (BOM) exportieren | Generiert eine Excel-konforme CSV-Stückliste aus dem aktiven Dokument |
| Part/Assembly ersetzen | Ersetzt ein ausgewähltes Teil/Assembly durch ein Ersatzteil, ordnet Joints/Referenzen neu zu |
| Auswählbarkeit reparieren | Macht Bauteile wieder auswählbar, die durch den Joint-Isolate-Bug hängen geblieben sind |
| Schnitt-Sketch erstellen | Erstellt einen Sketch mit den Schnittkonturen aller sichtbaren Körper |
| Import-Komponente | Bindet eine fertige Unterbaugruppe als normales `App::Link` ein |
| Interface anlegen/bearbeiten | Erstellt/bearbeitet ein InterfacePlacement-Feature |
| Part Player | Baut einen PartDesign-Body Feature für Feature in einem neuen Dokument nach |

(Das frühere eigene Pattern-Werkzeug wurde 2026-10-10 entfernt - FreeCADs Assembly-Werkbench
unterstützt seit Upstream-Commit `67103b19c9` natives `Part::LinkArray` direkt in
Baugruppen, siehe [docs/ASSEMBLY_PATTERN.md](docs/ASSEMBLY_PATTERN.md).)

## Weiterführende Dokumentation

Siehe [`docs/`](docs/), u.a. [Assembly Solver Guide](docs/ASSEMBLY_SOLVER_GUIDE.md)
und [Assembly Pattern](docs/ASSEMBLY_PATTERN.md).

## Hinweis zu `src/`/`include/`

Die dort liegende C++-Portierung (`FCProjectCore`) ist historisch/optional - seit 2026-09
läuft die komplette Workbench (inkl. BOM-Export) rein in Python, damit sie ohne separaten
Build über den Addon Manager installierbar bleibt. `src/`/`include/`/`CMakeLists.txt` bleiben
als Referenz stehen, werden aber von keinem Python-Modul mehr importiert.
