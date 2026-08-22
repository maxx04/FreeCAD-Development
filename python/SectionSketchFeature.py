# FCProject: Live aktualisierender Schnitt-Sketch (Ersatz fuer SectionCutSolidsOnly.FCMacro)
#
# Anders als das Makro (siehe resources/SectionCutSolidsOnly.FCMacro, dort mit vollem
# Verlauf/den Fehlschlaegen dokumentiert) werden hier keine Koerper ausgeblendet und
# dupliziert - stattdessen entsteht EIN Sketcher::SketchObject auf der gewaehlten Ebene,
# das die Schnittkonturen aller aktuell sichtbaren Koerper enthaelt und sich bei jeder
# Baugruppen-Aktualisierung neu berechnet (App::FeaturePython, analog zu den bestehenden
# Pattern-Features in PatternFeatures.py).
#
# Auf Nutzerwunsch: IMMER alle sichtbaren Solids live (kein fest hinterlegter Objekt-
# Katalog), aber mit einem "Active"-Schalter, um die (potenziell teure) Neuberechnung bei
# Bedarf abzuschalten. Gefundene Koerper werden zusaetzlich als Dependencies-Property
# hinterlegt, damit FreeCAD ueber den normalen Abhaengigkeitsgraph nur dann neu rechnet,
# wenn sich tatsaechlich einer der zuletzt geschnittenen Koerper aendert - nicht bei
# JEDEM Dokument-Recompute.
import math
import os

import FreeCAD as App
import Part

try:
    import FreeCADGui as Gui
    from PySide6 import QtWidgets
    _GUI_AVAILABLE = True
except ImportError:
    _GUI_AVAILABLE = False

ICON_DIR = os.path.join(os.path.dirname(__file__), 'resources', 'icons')


def _find_assembly(doc):
    for obj in doc.Objects:
        if obj.TypeId == "Assembly::AssemblyObject":
            return obj
    return None


def _find_top_level_link_for(doc, target_obj):
    """FreeCADs 3D-Auswahl liefert bei per App::Link eingebundenen Teilen manchmal das
    ROHE Objekt aus dem verlinkten Quelldokument (z.B. ein PartDesign-Tip-Feature namens
    'BaseFeature') statt das Mirror-Link-Objekt, das tatsaechlich in der Baugruppe sitzt
    und vom Solver bewegt wird. Nur das Mirror-Objekt hat die reale, zusammengebaute
    Placement/Shape - das rohe Quellobjekt bleibt in seinem eigenen Dokument fest.

    Sucht deshalb unter den DIREKTEN Kindern von 'doc' nach einem App::Link, dessen
    aufgeloestes Ziel im selben Dokument wie target_obj liegt, und gibt DIESES zurueck.
    Deckt bewusst nur eine Verschachtelungsebene ab (reicht fuer direkt in der Baugruppe
    eingebundene Teile wie hier getestet) - fuer mehrfach verschachtelte Unterbaugruppen
    (Teil zwei oder mehr Ebenen tief) muesste das rekursiv durch alle AssemblyLinks
    weitersuchen, was hier bewusst noch nicht gemacht wird (kein bestaetigter Bedarfsfall)."""
    target_doc = target_obj.Document
    if target_doc is doc:
        return target_obj  # schon direkt im aktiven Dokument, kein Mirror noetig

    for candidate in doc.Objects:
        if not candidate.isDerivedFrom("App::Link"):
            continue
        try:
            linked = candidate.getLinkedObject(True)
        except Exception:
            continue
        if linked is not None and linked.Document is target_doc:
            return candidate
    return None


def _resolve_plane(ref_obj, subname):
    """Liefert (Basispunkt, Normalenvektor) der Schnittebene, frisch aus der AKTUELLEN
    Position von ref_obj berechnet - das ist der Grund, warum das bei jeder Baugruppen-
    Bewegung mitzieht, statt einmalig eingefroren zu sein."""
    if subname and subname.startswith("Face"):
        if not hasattr(ref_obj, "Shape") or ref_obj.Shape is None or ref_obj.Shape.isNull():
            raise ValueError(f"'{ref_obj.Label}' hat keine gueltige Form mehr.")
        face = ref_obj.Shape.getElement(subname)
        if not isinstance(face.Surface, Part.Plane):
            raise ValueError(f"Flaeche '{subname}' von '{ref_obj.Label}' ist nicht eben.")
        base = face.CenterOfMass
        normal = face.Surface.Axis
        if face.Orientation == "Reversed":
            normal = normal.negative()
        return base, normal.normalize()

    if ref_obj.TypeId in ("PartDesign::Plane", "Part::Plane", "App::Plane"):
        base = ref_obj.Placement.Base
        normal = ref_obj.Placement.Rotation.multVec(App.Vector(0, 0, 1))
        return base, normal.normalize()

    raise ValueError(
        f"'{ref_obj.Label}' ist weder eine ebene Flaeche noch eine Datum-Ebene."
    )


def _make_half_space_box(base, normal, size):
    """Grosser Kasten, dessen eine Seite genau auf der Ebene liegt und der von dort in
    Richtung der Normale wegragt - identische Technik wie in SectionCutSolidsOnly.FCMacro
    (dort live getestet und verifiziert)."""
    box = Part.makeBox(size, size, size, App.Vector(-size / 2, -size / 2, 0))
    box.Placement = App.Placement(base, App.Rotation(App.Vector(0, 0, 1), normal))
    return box


def _section_faces_of_solid(solid, base, normal, size):
    """Schneidet EINEN Solid an der Ebene und gibt die dabei neu entstandene(n)
    Schnittflaeche(n) zurueck (die Flaechen, deren ebene Traegerflaeche exakt mit der
    Schnittebene zusammenfaellt) - das ist robuster als ein direktes Solid/Face-'common()',
    weil 'cut()' schon in SectionCutSolidsOnly.FCMacro live gegen die echte Baugruppe
    verifiziert wurde.

    'size' kommt bewusst von AUSSEN (einmal fuer das ganze Dokument berechnet, siehe
    execute()) statt hier pro Solid aus dessen eigener BoundBox - eine rein lokale
    Groesse reicht bei einer grossen Baugruppe nicht bis zu weit von 'base' entfernten
    Teilen (z.B. Motoren/Schienen am anderen Ende der Baugruppe), die Box trifft solche
    Koerper dann unabhaengig von der Normalenrichtung gar nicht erst - genau das hat
    beim ersten Live-Test ALLE 68 Koerper faelschlich als 'no-intersection' gemeldet."""
    tool = _make_half_space_box(base, normal, size)

    try:
        cut_result = solid.cut(tool)
    except Part.OCCError as exc:
        App.Console.PrintWarning(f"FCProject: SectionSketch: Schnitt fehlgeschlagen: {exc}\n")
        return [], "cut-failed"

    if cut_result.isNull() or not cut_result.Solids:
        return [], "fully-removed"  # Koerper liegt komplett auf der wegzuschneidenden Seite

    if abs(cut_result.Volume - solid.Volume) < 1e-6:
        return [], "no-intersection"  # Ebene trifft den Koerper gar nicht

    faces = []
    for face in cut_result.Faces:
        if not isinstance(face.Surface, Part.Plane):
            continue
        distance = (face.CenterOfMass - base).dot(normal)
        if abs(distance) < 1e-5:
            faces.append(face)

    if not faces:
        return [], "no-matching-face"  # Schnitt fand statt, aber Toleranzcheck griff nicht
    return faces, "ok"


def _edge_to_sketch_geometry(edge):
    """Wandelt eine (bereits ins lokale Ebenen-Koordinatensystem transformierte) Kante in
    Sketcher-Geometrie um. Deckt die in mechanischen Schnitten weit ueberwiegenden Faelle ab
    (Linie, Kreis/Bogen); alles andere wird als B-Spline-Naeherung uebernommen, statt
    stillschweigend zu verschwinden."""
    curve = edge.Curve
    p1 = edge.Vertexes[0].Point
    p2 = edge.Vertexes[-1].Point

    if isinstance(curve, (Part.Line, Part.LineSegment)):
        return [Part.LineSegment(App.Vector(p1.x, p1.y, 0), App.Vector(p2.x, p2.y, 0))]

    if isinstance(curve, Part.Circle):
        center = App.Vector(curve.Center.x, curve.Center.y, 0)
        if edge.Closed:
            return [Part.Circle(center, App.Vector(0, 0, 1), curve.Radius)]
        circle = Part.Circle(center, App.Vector(0, 0, 1), curve.Radius)
        return [Part.ArcOfCircle(circle, curve.parameter(p1), curve.parameter(p2))]

    try:
        bspline = curve.toBSpline(edge.FirstParameter, edge.LastParameter)
        return [bspline]
    except Exception:
        App.Console.PrintWarning(
            "FCProject: SectionSketch: unbekannter Kantentyp uebersprungen "
            f"({type(curve).__name__}).\n"
        )
        return []


def _rebuild_sketch_geometry(sketch, local_edges):
    sketch.deleteAllGeometry()
    geoms = []
    for edge in local_edges:
        geoms.extend(_edge_to_sketch_geometry(edge))
    if geoms:
        sketch.addGeometry(geoms, False)


class SectionSketchProxy:
    """Proxy fuer das Schnitt-Sketch-Feature (App::FeaturePython)."""

    def __init__(self, obj):
        self._add_properties(obj)
        obj.Proxy = self

    def _add_properties(self, obj):
        if not hasattr(obj, 'ReferencePlane'):
            # PropertyXLinkSub statt PropertyLinkSub: die gewaehlte Flaeche/Ebene liegt im
            # PDM-Standardfall auf einem Teil, das per App::Link aus einem eigenen
            # Teildokument eingebunden ist (siehe SourceElement in PatternFeatures.py -
            # gleicher Grund).
            obj.addProperty(
                "App::PropertyXLinkSub", "ReferencePlane", "Section",
                "Ebene Flaeche oder Datum-Ebene, die Position/Ausrichtung des Schnitts vorgibt"
            )
        if not hasattr(obj, 'Invert'):
            obj.addProperty(
                "App::PropertyBool", "Invert", "Section",
                "Schneidet die jeweils andere Haelfte, falls die Flaechennormale in die falsche Richtung zeigt"
            )
            obj.Invert = False
        if not hasattr(obj, 'Active'):
            obj.addProperty(
                "App::PropertyBool", "Active", "Section",
                "Bei Bedarf abschalten, um die Neuberechnung bei jeder Baugruppen-Aktualisierung zu sparen"
            )
            obj.Active = True
        if not hasattr(obj, 'Sketch'):
            # PropertyLinkHidden statt PropertyLink: dieser Link ist rein informativ
            # ("welcher Sketch gehoert zu mir") und darf NICHT in FreeCADs
            # Abhaengigkeitsgraph auftauchen - sonst wuerde er bedeuten "obj haengt vom
            # Sketch ab", also Sketch VOR obj berechnen. Tatsaechlich ist es umgekehrt:
            # obj.execute() SCHREIBT in den Sketch, der Sketch muss also NACH obj
            # berechnet werden. Die richtige Abhaengigkeitsrichtung stellt stattdessen
            # sketch.Driver her (siehe make_section_sketch()) - ein normaler PropertyLink
            # auf dem Sketch selbst, der obj referenziert. Beide Links gleichzeitig als
            # normale PropertyLink waeren ein Ring (obj->Sketch->obj) und wuerden von
            # FreeCAD als zirkulaere Abhaengigkeit abgelehnt.
            obj.addProperty(
                "App::PropertyLinkHidden", "Sketch", "Section",
                "Sketch-Objekt mit den berechneten Schnittkonturen", locked=True
            )
        if not hasattr(obj, 'Dependencies'):
            # Hidden, rein fuer den Abhaengigkeitsgraph: registriert die beim letzten
            # Durchlauf gefundenen Koerper, damit FreeCAD kuenftig NUR dann neu rechnet,
            # wenn sich einer von ihnen aendert - nicht bei jedem beliebigen Recompute.
            obj.addProperty(
                "App::PropertyLinkListHidden", "Dependencies", "Section",
                "Zuletzt geschnittene Koerper (rein informativ/fuer den Abhaengigkeitsgraph)",
                locked=True
            )

    def onChanged(self, obj, prop):
        pass

    def execute(self, obj):
        if not obj.Active:
            return

        ref = obj.ReferencePlane
        if not ref or ref[0] is None:
            App.Console.PrintWarning(f"FCProject: SectionSketch '{obj.Label}' hat keine ReferencePlane.\n")
            return
        ref_obj, subnames = ref
        subname = subnames[0] if subnames else None

        try:
            base, normal = _resolve_plane(ref_obj, subname)
        except Exception as exc:
            App.Console.PrintWarning(f"FCProject: SectionSketch '{obj.Label}': {exc}\n")
            return

        if obj.Invert:
            normal = normal.negative()

        plane_placement = App.Placement(base, App.Rotation(App.Vector(0, 0, 1), normal))
        inv_matrix = plane_placement.inverse().toMatrix()

        sketch = obj.Sketch
        if sketch is None:
            App.Console.PrintWarning(f"FCProject: SectionSketch '{obj.Label}' hat kein Sketch-Kindobjekt.\n")
            return

        doc = obj.Document

        # 1. Durchlauf: sichtbare Koerper einsammeln UND eine gemeinsame Box-Groesse
        # bestimmen, die von 'base' aus in jede Richtung weit genug reicht, um auch weit
        # entfernte Teile der Baugruppe noch zu erfassen (siehe Docstring von
        # _section_faces_of_solid - eine rein lokale Groesse pro Solid reicht dafuer nicht).
        candidates = []
        combined_bbox = App.BoundBox(base, base)
        for candidate in doc.Objects:
            if candidate is obj or candidate is sketch:
                continue
            # Assembly-Container ueberspringen: ihre .Shape ist ohnehin nur die
            # Vereinigung ihrer eigenen (hier separat als eigene Objekte gezaehlten)
            # Kinder - ohne diesen Filter wuerde JEDER Koerper doppelt geschnitten
            # (einmal als Teil des Container-Compounds, einmal einzeln), was sowohl
            # die Rechenzeit vervielfacht als auch zu ueberlagerter/verdoppelter
            # Sketch-Geometrie fuehrt (sah im Live-Test wie wirres Gekritzel aus).
            if candidate.TypeId in ("Assembly::AssemblyObject", "Assembly::AssemblyLink"):
                continue
            vis = getattr(candidate, "ViewObject", None)
            if vis is None or not vis.Visibility:
                continue
            if not hasattr(candidate, "Shape") or candidate.Shape is None or candidate.Shape.isNull():
                continue
            if not candidate.Shape.Solids:
                continue
            candidates.append(candidate)
            combined_bbox.add(candidate.Shape.BoundBox)

        diagonal = combined_bbox.DiagonalLength
        if not math.isfinite(diagonal) or diagonal <= 0.0:
            diagonal = 0.0
        size = max(diagonal * 2, 100.0)

        # 2. Durchlauf: mit der so bestimmten, garantiert ausreichenden Groesse schneiden.
        solids_found = []
        local_edges = []
        status_labels = {}  # status -> [Label, ...], nur fuer status != "ok"

        for candidate in candidates:
            solids_found.append(candidate)
            for solid in candidate.Shape.Solids:
                faces, status = _section_faces_of_solid(solid, base, normal, size)
                if status != "ok":
                    status_labels.setdefault(status, []).append(candidate.Label)
                    continue
                for face in faces:
                    for wire in face.Wires:
                        for edge in wire.Edges:
                            local_edge = edge.copy()
                            local_edge.transformShape(inv_matrix, True)
                            local_edges.append(local_edge)

        obj.Dependencies = solids_found
        sketch.Placement = plane_placement
        _rebuild_sketch_geometry(sketch, local_edges)

        if not solids_found:
            App.Console.PrintWarning(
                f"FCProject: SectionSketch '{obj.Label}': keine sichtbaren Koerper gefunden.\n"
            )
        _STATUS_MESSAGES = {
            "no-intersection": (
                "Ebene trifft den Koerper gar nicht (Volumen unveraendert) - haeufigste Ursache: "
                "Flaechennormale zeigt vom Material weg, 'Invert'-Property umschalten"
            ),
            "fully-removed": "Koerper liegt komplett auf der wegzuschneidenden Seite (leeres Ergebnis)",
            "no-matching-face": "Schnitt fand statt, aber keine Flaeche lag exakt auf der Ebene (Toleranzproblem)",
            "cut-failed": "Boolescher Schnitt ist fehlgeschlagen (OCC-Fehler)",
            "invalid-boundbox": "Koerper hat eine ungueltige/unplausible BoundBox",
        }
        for status, labels in status_labels.items():
            App.Console.PrintWarning(
                f"FCProject: SectionSketch '{obj.Label}': {_STATUS_MESSAGES.get(status, status)} - "
                f"betrifft {len(labels)} Koerper: {', '.join(labels)}.\n"
            )
        if not local_edges and solids_found and not status_labels:
            App.Console.PrintWarning(
                f"FCProject: SectionSketch '{obj.Label}': {len(solids_found)} Koerper gefunden, "
                "aber keine Schnittkanten erzeugt - unklare Ursache, bitte melden.\n"
            )

    def onDocumentRestored(self, obj):
        self._add_properties(obj)
        obj.Proxy = self

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


if _GUI_AVAILABLE:
    class ViewProviderSectionSketch:
        def __init__(self, vobj):
            vobj.Proxy = self

        def attach(self, vobj):
            self.Object = vobj.Object

        def claimChildren(self):
            return [self.Object.Sketch] if self.Object.Sketch else []

        def getIcon(self):
            return os.path.join(ICON_DIR, 'section_sketch.svg')

        def doubleClicked(self, vobj):
            # Kein eigenes TaskPanel bisher - Doppelklick markiert zumindest die aktuell
            # verwendete Referenzebene, damit man sie im Modellbaum wiederfindet.
            ref = vobj.Object.ReferencePlane
            if ref and ref[0] is not None:
                Gui.Selection.clearSelection()
                Gui.Selection.addSelection(ref[0])
            return True

        def __getstate__(self):
            return None

        def __setstate__(self, state):
            return None


def make_section_sketch(doc, assembly, ref_obj, subname):
    """Erstellt das SectionSketch-Feature plus sein Sketch-Kindobjekt und haengt beides
    in die Baugruppe ein (analog zu make_linear_pattern/make_circular_pattern)."""
    doc.openTransaction("FCProject Section Sketch")
    try:
        sketch = doc.addObject("Sketcher::SketchObject", "SectionProfile")

        obj = doc.addObject("App::FeaturePython", "SectionSketch")
        obj.Label = f"Schnitt-Sketch: {ref_obj.Label}"
        SectionSketchProxy(obj)
        obj.ReferencePlane = (ref_obj, [subname] if subname else [])
        obj.Sketch = sketch

        # Normaler (nicht versteckter) Link auf dem SKETCH, der auf obj zeigt - das ist
        # die einzige echte Abhaengigkeitskante im Graph: "Sketch haengt von obj ab",
        # sorgt also dafuer, dass obj.execute() IMMER vor der Sketch-Neuberechnung laeuft.
        # Ohne das kann FreeCADs Recompute-Reihenfolge den Sketch vor obj einsortieren -
        # das Ergebnis bleibt dann "still touched after recompute" haengen, weil obj erst
        # danach in den Sketch hineinschreibt.
        if not hasattr(sketch, "Driver"):
            sketch.addProperty(
                "App::PropertyLink", "Driver", "Section",
                "Erzeugendes SectionSketch-Feature (nur fuer die Berechnungsreihenfolge)"
            )
        sketch.Driver = obj

        if assembly is not None and hasattr(assembly, 'addObject'):
            assembly.addObject(obj)
            assembly.addObject(sketch)

        if _GUI_AVAILABLE and obj.ViewObject:
            ViewProviderSectionSketch(obj.ViewObject)

        doc.recompute()
        doc.commitTransaction()
        return obj
    except Exception:
        doc.abortTransaction()
        raise


if _GUI_AVAILABLE:
    class CommandCreateSectionSketch:
        """Befehl: legt an der ausgewaehlten Flaeche/Datum-Ebene ein live aktualisierendes
        SectionSketch-Feature an (Ersatz fuer SectionCutSolidsOnly.FCMacro)."""

        def GetResources(self):
            return {
                'Pixmap': os.path.join(ICON_DIR, 'section_sketch.svg'),
                'MenuText': 'FCProject: Schnitt-Sketch erstellen',
                'ToolTip': (
                    'Erstellt einen Sketch mit den Schnittkonturen aller sichtbaren Koerper an '
                    'der ausgewaehlten Ebene/Flaeche - aktualisiert sich bei Baugruppen-Aenderungen '
                    'automatisch mit (ueber "Active" abschaltbar).'
                )
            }

        def Activated(self):
            main_win = Gui.getMainWindow()
            sel = Gui.Selection.getSelectionEx()
            if not sel:
                QtWidgets.QMessageBox.warning(
                    main_win, "FCProject",
                    "Bitte zuerst eine ebene Flaeche oder eine Datum-Ebene auswaehlen."
                )
                return

            first = sel[0]
            ref_obj = first.Object
            subname = first.SubElementNames[0] if first.SubElementNames else None

            doc = App.ActiveDocument
            top_level = _find_top_level_link_for(doc, ref_obj)
            if top_level is not None and top_level is not ref_obj:
                App.Console.PrintMessage(
                    f"FCProject: SectionSketch: Auswahl '{ref_obj.Label}' gehoert zum "
                    f"Quelldokument von Mirror-Objekt '{top_level.Label}' in der Baugruppe - "
                    "verwende dieses fuer die Referenzebene (hat die tatsaechliche, "
                    "zusammengebaute Platzierung).\n"
                )
                ref_obj = top_level

            try:
                base, normal = _resolve_plane(ref_obj, subname)  # nur zur Validierung der Auswahl
            except Exception as exc:
                QtWidgets.QMessageBox.warning(main_win, "FCProject", str(exc))
                return

            # Diagnose: vergleicht unseren (ueber ref_obj.Shape.getElement() berechneten)
            # Basispunkt mit dem, was FreeCADs Selection-API selbst als global korrekt
            # platzierte Position dieser Unterflaeche kennt (SubObjects[0]) - bei tief
            # verschachtelten Baugruppen/PartDesign-Feature-Objekten (z.B. Label
            # "BaseFeature") koennen diese auseinanderlaufen, wenn ref_obj.Shape nur die
            # LOKALE, nicht die durch die Baugruppe hindurch komponierte globale Form ist.
            try:
                selection_sub_shape = first.SubObjects[0] if first.SubObjects else None
                if selection_sub_shape is not None and hasattr(selection_sub_shape, "CenterOfMass"):
                    selection_center = selection_sub_shape.CenterOfMass
                    App.Console.PrintMessage(
                        f"FCProject: SectionSketch-Diagnose: ref_obj='{ref_obj.Name}' "
                        f"(Label='{ref_obj.Label}', TypeId={ref_obj.TypeId}), subname='{subname}'\n"
                        f"  base (aus ref_obj.Shape.getElement)      = {base}\n"
                        f"  Selection.SubObjects[0].CenterOfMass     = {selection_center}\n"
                        f"  Abstand zwischen beiden                  = {(base - selection_center).Length:.3f} mm\n"
                    )
            except Exception as exc:
                App.Console.PrintWarning(f"FCProject: SectionSketch-Diagnose fehlgeschlagen: {exc}\n")

            assembly = _find_assembly(doc)
            make_section_sketch(doc, assembly, ref_obj, subname)

        def IsActive(self):
            return App.ActiveDocument is not None

    Gui.addCommand('FCProject_CreateSectionSketch', CommandCreateSectionSketch())
