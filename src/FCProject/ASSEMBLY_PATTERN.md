# AssemblyPattern Command - Dokumentation

## Übersicht
Der AssemblyPattern Command ermöglicht die Erstellung von Array-Patterns (Reihungen) von Elementen in einer FreeCAD Assembly über Joints.

## Funktionen

### 1. Lineares Pattern (Standard)
- **Verwendung**: Kopiert ein Element mehrfach in einer Linie
- **Parameter**:
  - `source_element`: Das zu kopierende Element
  - `count`: Anzahl der Kopien (1-100)
  - `distance`: Abstand zwischen Elementen (mm)
  - `direction`: X-Achse, Y-Achse, oder Z-Achse

**Beispiel**:
```python
creator = AssemblyPatternCreator(doc, assembly)
creator.create_pattern(
    source_element=part_object,
    count=5,
    distance=50.0,
    direction="X-Achse"
)
```

### 2. Zirkuläres Pattern (Alternativ)
- **Verwendung**: Kopiert ein Element mehrfach im Kreis
- **Parameter**:
  - `source_element`: Das zu kopierende Element
  - `count`: Anzahl der Kopien
  - `radius`: Radius des Kreises (mm)

**Beispiel**:
```python
creator.create_circular_pattern(
    source_element=part_object,
    count=6,
    radius=100.0
)
```

## Architektur

### Dateien:
- **AssemblyPatternCommand.py**: GUI-Dialog und Command-Registrierung
- **AssemblyPatternCreator.py**: Core-Logik für Pattern-Erstellung
- **InitGui.py**: Integration in die Toolbar

### Workflow:
1. Benutzer klickt den "Assembly Pattern via Joints" Button
2. Dialog öffnet sich mit Konfigurationsoptionen
3. Benutzer wählt Quell-Element, Anzahl, Abstand und Richtung
4. Pattern wird erstellt und in einer DocumentObjectGroup organisiert
5. Joints werden automatisch zwischen Elementen erstellt (wenn verfügbar)

## TODO / Erweiterungen

- [ ] Icons für den Toolbar-Button erstellen (.svg)
- [ ] Joints-Integration mit Assembly Workbench optimieren
- [ ] Symmetrische Patterns unterstützen
- [ ] Pattern-Abstandsberechnung mit Geometrie-Analyse
- [ ] UI für Mirror/Rotation Patterns hinzufügen
- [ ] Undo/Redo Support erweitern
- [ ] CSV-Export für Pattern-Konfiguration

## Abhängigkeiten

- FreeCAD 1.1+ (Assembly Workbench)
- PySide6 (GUI)
- FreeCAD Python API

## Fehlerbehandlung

Der Command behandelt folgende Fehler:
- Keine Assembly vorhanden
- Keine Elemente zur Auswahl
- Ungültige Parameter (count <= 0, distance <= 0)
- Assembly Workbench nicht verfügbar

## Testwerkzeuge

Im Projekt gibt es auch:
- `DEBUG.md`: Für Debugging-Informationen
- `CONSTRAINTS.md`: Assembly-Constraints Dokumentation
- `LEARNINGS.md`: Gelernte Lektionen
