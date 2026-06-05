# FCProject Icons Dokumentation

## Icon-Struktur

Alle Icons sind im SVG-Format und befinden sich in: `resources/icons/`

## Verfügbare Icons

### 1. assembly_pattern.svg
- **Verwendung**: Assembly Pattern / Array Command
- **Symbol**: 8 Würfel in 2x4 Anordnung (Pattern)
- **Farbe**: Blau (#4A90E2 - #357ABD Gradient)
- **Command**: `FCProject_AssemblyPattern`

### 2. project_manager.svg
- **Verwendung**: Projekt Manager / Initialisierung
- **Symbol**: Ordner mit Dokumenten
- **Farbe**: Orange (#F5A623 - #D68910 Gradient)
- **Command**: `FCProject_ProjectManager`

### 3. bom_export.svg
- **Verwendung**: BOM / Stücklisten Export
- **Symbol**: Tabelle/Grid mit Spalten und Reihen
- **Farbe**: Grün (#7ED321 - #5FA31A Gradient)
- **Command**: `FCProject_ExportBOM`

### 4. part_creator.svg
- **Verwendung**: Part Creator / Bauteil erstellen
- **Symbol**: 3D Würfel (isometrisch) mit Plus-Zeichen
- **Farbe**: Rot (#E84C3D - #C83A2A Gradient)
- **Command**: `FCProject_CreatePart`

### 5. fcproject.svg
- **Verwendung**: FCProject Modul / Haupt-Icon
- **Symbol**: Abstrakter Projektordner mit „FC“ und Zahnrad-Akzent
- **Farbe**: Blauviolett (#5B8BE8 - #3A5DC9 Gradient)
- **Command**: `FCProject` (allgemeines Modul-Icon)

## Design-Prinzipien

- **Format**: SVG (skalierbar, klein, vektorbasiert)
- **Größe**: 64x64 Pixel (optimal für FreeCAD Toolbars)
- **Stil**: Flat Design mit Gradienten
- **Kontrast**: Hohe Lesbarkeit für alle Icon-Größen
- **Konsistenz**: Einheitliche Farbpalette und Design-Sprache

## Farbpalette

```
Blau:    #4A90E2 (Primary) / #357ABD (Dark)
Orange:  #F5A623 (Primary) / #D68910 (Dark)
Grün:    #7ED321 (Primary) / #5FA31A (Dark)
Rot:     #E84C3D (Primary) / #C83A2A (Dark)
Akzent:  #FFFFFF (Light) / #2E5C8A (Shadow)
```

## Icon-Pfade in Commands

```python
import os
icon_path = os.path.join(os.path.dirname(__file__), 'resources', 'icons', 'assembly_pattern.svg')

return {
    'Pixmap': icon_path,
    'MenuText': '...',
    'ToolTip': '...'
}
```

## Bearbeitung / Erweiterung

Die Icons können mit folgenden Tools bearbeitet werden:
- Inkscape (kostenlos, spezialisiert auf SVG)
- Adobe Illustrator
- VS Code mit SVG-Extension
- Online Editoren (z.B. SVG Editor)

## Best Practices

1. **Icon-Größe**: Immer bei 64x64 px entwerfen
2. **Strichstärke**: 0.8-1.5 px für optimale Darstellung
3. **Viewbox**: `viewBox="0 0 64 64"` verwenden
4. **Gradienten**: Für Tiefenwirkung und Professionalität nutzen
5. **Transparenz**: Sparsam einsetzen (opacity < 0.3-0.8)

## Zukünftige Erweiterungen

- [ ] Dark-Mode Icons erstellen (invertierte Farben)
- [ ] Hover-State Icons für Interaktivität
- [ ] Higher-DPI Icons (128x128 / 256x256)
- [ ] Animation möglich (z.B. spinning Pattern Icon)
- [ ] Icon-Set für weitere Commands
