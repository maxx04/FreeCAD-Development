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
import Sketcher

try:
    import FreeCADGui as Gui
    from PySide6 import QtWidgets, QtCore
    _GUI_AVAILABLE = True
except ImportError:
    _GUI_AVAILABLE = False

import IconUtils

ICON_DIR = os.path.join(os.path.dirname(__file__), 'resources', 'icons')

# FCPROJECT-FEATURE (2026-11-08, Nutzerwunsch "in Baugruppe verschiedene Teile zuerst durch
# Farben zu unterscheiden"): FreeCADs Sketcher kennt KEINE Farbe pro einzelnem Geometrie-
# Element innerhalb eines Sketches (geprueft: weder SketchObject.h noch ViewProviderSketch.cpp
# bieten eine per-Element-Farb-API) - Farbe ist nur eine Eigenschaft des GANZEN Sketch-Objekts
# (ViewObject.LineColor, geerbt von Gui::ViewProviderGeometryObject). Deshalb erzeugt execute()
# jetzt einen EIGENEN Sketch PRO geschnittenem Quell-Teil statt einen gemeinsamen fuer alle -
# jeder bekommt automatisch eine eigene Farbe aus dieser festen Palette. Farbwahl ueber einen
# Hash des (nie veraendernden) internen .Name des Quell-Teils statt Listen-Reihenfolge, damit
# dieselbe Farbe bei jedem Recompute beim selben Teil bleibt, auch wenn sich z.B. durch
# Sichtbarkeits-Toggles die Reihenfolge der gefundenen Koerper aendert.
_PART_COLOR_PALETTE = [
    (0.85, 0.20, 0.20),  # Rot
    (0.20, 0.45, 0.85),  # Blau
    (0.20, 0.75, 0.30),  # Gruen
    (0.95, 0.60, 0.10),  # Orange
    (0.60, 0.25, 0.80),  # Violett
    (0.10, 0.70, 0.70),  # Tuerkis
    (0.90, 0.85, 0.15),  # Gelb
    (0.85, 0.35, 0.60),  # Pink
    (0.45, 0.45, 0.45),  # Grau
    (0.55, 0.35, 0.15),  # Braun
]


def _color_for_part(part_name):
    """Deterministische, stabile Farbzuordnung per Hash des internen .Name (NIE .Label, siehe
    [[feedback_fcproject_never_use_label_for_addressing]]) - dieselbe Farbe fuer dasselbe Teil
    bei jedem Recompute, unabhaengig von der Fundreihenfolge."""
    index = hash(part_name) % len(_PART_COLOR_PALETTE)
    return _PART_COLOR_PALETTE[index]


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


def _ancestor_placement(obj):
    """Liefert NUR den Beitrag der umschliessenden GeoFeatureGroups (z.B. Assembly::
    AssemblyObject) zur globalen Platzierung von obj - OHNE obj's eigene Placement (die steckt
    schon in obj.Shape/obj.Placement selbst drin).

    FCPROJECT-FIX (2026-11-08, Nutzer-Report "einzelne Schnitte liegen in anderer Ebene" +
    isoliert reproduziert mit absichtlich nicht-trivialer Baugruppen-Placement): obj.Shape UND
    obj.Placement sind NUR lokal zur direkt umschliessenden GeoFeatureGroup - die Placement
    der Baugruppe SELBST (z.B. weil sie Teil einer groesseren Baugruppe ist) wird darin NICHT
    automatisch mitgerechnet. obj.getGlobalPlacement() liefert dagegen die volle, durch ALLE
    Eltern-Gruppen hindurch zusammengesetzte Placement (global = ancestor * obj.Placement) -
    durch Abziehen von obj.Placement bleibt genau der Eltern-Anteil uebrig, den man auf einen
    bereits obj-lokalen Punkt/Vektor (wie er aus obj.Shape.getElement() kommt) noch zusaetzlich
    anwenden muss, um die ECHTE globale/zusammengebaute Position zu bekommen.

    FCPROJECT-FIX (2026-11-08, Live-Fehler "App.DocumentObject object has no attribute
    'getGlobalPlacement'"): getGlobalPlacement() existiert nur auf App::GeoFeature (siehe
    src/App/GeoFeaturePyImp.cpp) - App::Link (das in diesem Projekt staendig als "Mirror-Link"
    fuer Teile aus eigenen Unter-Dokumenten verwendet wird, siehe _find_top_level_link_for())
    erbt NICHT davon und hat die Methode schlicht nicht. Fuer Links ist das aber kein Problem:
    ihre .Shape/.Placement sind (anders als bei einer reinen GeoFeatureGroup-Verschachtelung
    OHNE Link) bereits vollstaendig ueber den Link hinweg zusammengesetzt - hier also KEINE
    zusaetzliche Korrektur noetig (Identity zurueckgeben)."""
    if not hasattr(obj, "getGlobalPlacement"):
        return App.Placement()
    try:
        return obj.getGlobalPlacement() * obj.Placement.inverse()
    except Exception:
        # Defensiv: lieber keine Korrektur (altes, bisher funktionierendes Verhalten) als
        # execute() wegen eines einzelnen unerwarteten Objekttyps komplett abzubrechen.
        return App.Placement()


def _resolve_plane(ref_obj, subname):
    """Liefert (Basispunkt, Normalenvektor) der Schnittebene, frisch aus der AKTUELLEN
    Position von ref_obj berechnet - das ist der Grund, warum das bei jeder Baugruppen-
    Bewegung mitzieht, statt einmalig eingefroren zu sein."""
    ancestor = _ancestor_placement(ref_obj)
    if subname and subname.startswith("Face"):
        if not hasattr(ref_obj, "Shape") or ref_obj.Shape is None or ref_obj.Shape.isNull():
            raise ValueError(f"'{ref_obj.Label}' hat keine gueltige Form mehr.")
        face = ref_obj.Shape.getElement(subname)
        if not isinstance(face.Surface, Part.Plane):
            raise ValueError(f"Flaeche '{subname}' von '{ref_obj.Label}' ist nicht eben.")
        base = ancestor.multVec(face.CenterOfMass)
        normal = ancestor.Rotation.multVec(face.Surface.Axis)
        if face.Orientation == "Reversed":
            normal = normal.negative()
        return base, normal.normalize()

    # FCPROJECT-FIX (2026-11-08, bekannter offener Bug seit 2026-08-22, siehe
    # [[project_fcproject_sectionsketch_open_issues]]): "selbsterstellte Bezugsebenen
    # funktionieren nicht als ReferencePlane" - Root Cause gefunden per freecad-source-
    # Recherche: der generische "Bezugsebene erstellen"-Befehl AUSSERHALB von PartDesign
    # (Part_DatumPlane, src/Mod/Part/Gui/Command.cpp) legt ein Part::DatumPlane an - genau
    # der TypeId, den eine Baugruppe (kein PartDesign-Body-Kontext) normalerweise nutzt.
    # Der bisherige exakte TypeId-String-Vergleich kannte nur "PartDesign::Plane"/
    # "Part::Plane"/"App::Plane", NICHT "Part::DatumPlane" - fiel also bisher immer durch,
    # obwohl Part::DatumPlane (Datums.h) direkt von App::Plane erbt. Jetzt per
    # isDerivedFrom() statt exaktem String - robust auch gegen diese (und kuenftige)
    # Unterklassen. "Part::Plane" (reine Flaechen-Primitive, andere Vererbung) bleibt
    # separat per exaktem TypeId, PartDesign::Plane analog per isDerivedFrom (erbt von
    # Part::Datum, NICHT von App::Plane - eigener Zweig).
    if (
        ref_obj.TypeId == "Part::Plane"
        or ref_obj.isDerivedFrom("App::Plane")
        or ref_obj.isDerivedFrom("PartDesign::Plane")
    ):
        base = ancestor.multVec(ref_obj.Placement.Base)
        normal = ancestor.Rotation.multVec(ref_obj.Placement.Rotation.multVec(App.Vector(0, 0, 1)))
        return base, normal.normalize()

    raise ValueError(
        f"'{ref_obj.Label}' ist weder eine ebene Flaeche noch eine Datum-Ebene."
    )


def _make_half_space_box(base, normal, size):
    """Grosser Kasten, dessen eine Seite genau auf der Ebene liegt und der von dort in
    Richtung der Normale wegragt - identische Technik wie in SectionCutSolidsOnly.FCMacro
    (dort live getestet und verifiziert). Wird fuer JEDE einzelne Wand verwendet - beim
    flachen Fall genau einmal, beim gestuften Schnitt einmal PRO Stufen-Segment (siehe
    _wall_segments_from_step_sketch())."""
    box = Part.makeBox(size, size, size, App.Vector(-size / 2, -size / 2, 0))
    box.Placement = App.Placement(base, App.Rotation(App.Vector(0, 0, 1), normal))
    return box


def _wall_segments_from_step_sketch(local_wire):
    """Liest aus einem offenen, bereits ins lokale Ebenen-Koordinatensystem transformierten
    Linienzug (nur Geradensegmente - siehe Pruefung unten) die einzelnen Wand-SEGMENTE aus -
    jedes Segment wird spaeter wie ein GANZ NORMALER flacher Schnitt behandelt (eigene,
    lokale (Basispunkt, Normale), exakt die gleiche Technik wie beim einfachen Fall, siehe
    _make_half_space_box()/_section_faces_of_solid()), nur mehrfach hintereinander statt
    einmal - ein gestufter Schnitt ist technisch nichts anderes als mehrere unabhaengige
    flache Schnitte, einer pro Stufen-Segment.

    FCPROJECT-FIX (2026-11-08, live gefunden): ein erster Versuch baute stattdessen EINEN
    gemeinsamen, gestuften Werkzeug-Solid (Linienzug an den offenen Enden verlaengert, zu
    einem 2D-Profil geschlossen, senkrecht zur Ebene extrudiert) und versuchte, die daraus
    entstehenden Schnittflaechen anschliessend wieder in die EINE gemeinsame 2D-Ebenen-
    Projektion der Referenzebene zu packen. Das war konzeptionell falsch: die Schnittflaeche
    einer gestuften Wand liegt NICHT in der Referenzebene selbst, sondern in IHRER EIGENEN,
    seitlich versetzten Wandebene - die (lokaleX, lokaleY)-Projektion der Referenzebene
    kollabierte deren eigentliche Ausdehnung (die in Wahrheit entlang der Wandrichtung UND
    der Tiefe/lokalen Z verlaeuft) auf quasi einen Punkt ("Both points are equal" bzw. nur
    2 statt 4 Kanten pro Rechteck). Jedes Wand-Segment braucht deshalb seine EIGENE lokale
    Projektion (siehe execute()), nicht die der Referenzebene.

    Gibt eine Liste aus (lokaler Basispunkt, lokale Normale) zurueck, EIN Eintrag pro
    Segment, in Linienzug-Reihenfolge."""
    for edge in local_wire.Edges:
        if not isinstance(edge.Curve, (Part.Line, Part.LineSegment)):
            raise ValueError(
                "Gestufter Schnitt: der Linienzug im StepSketch enthaelt ein Element, das "
                "keine gerade Linie ist (z.B. Bogen/Spline) - aktuell nur Geradensegmente "
                "unterstuetzt."
            )

    ordered_points = [v.Point for v in local_wire.OrderedVertexes]
    if len(ordered_points) < 2:
        raise ValueError("Gestufter Schnitt: der Linienzug im StepSketch braucht mindestens 2 Punkte.")

    segments = []
    for i in range(len(ordered_points) - 1):
        p1, p2 = ordered_points[i], ordered_points[i + 1]
        seg_dir = p2 - p1
        if seg_dir.Length < 1e-9:
            continue
        seg_dir.normalize()
        # Senkrecht zum Segment, innerhalb der lokalen XY-Ebene (90 Grad gedreht) - das
        # Vorzeichen spielt fuer den Halbraum-Schnitt keine Rolle (Invert deckt beide
        # Richtungen gleichermassen ab, genau wie beim flachen Fall).
        wall_normal = App.Vector(-seg_dir.y, seg_dir.x, 0)
        segments.append((p1, wall_normal))

    if not segments:
        raise ValueError("Gestufter Schnitt: der Linienzug im StepSketch ergibt keine gueltigen Segmente.")
    return segments


def _section_faces_of_solid(solid, base, normal, size):
    """Schneidet EINEN Solid an der Ebene (base, normal) und gibt die dabei neu entstandene(n)
    Schnittflaeche(n) zurueck (die Flaechen, deren ebene Traegerflaeche exakt mit der
    Schnittebene zusammenfaellt) - das ist robuster als ein direktes Solid/Face-'common()',
    weil 'cut()' schon in SectionCutSolidsOnly.FCMacro live gegen die echte Baugruppe
    verifiziert wurde.

    'size' kommt bewusst von AUSSEN (einmal fuer das ganze Dokument berechnet, siehe
    execute()) statt hier pro Solid aus dessen eigener BoundBox - eine rein lokale
    Groesse reicht bei einer grossen Baugruppe nicht bis zu weit von 'base' entfernten
    Teilen (z.B. Motoren/Schienen am anderen Ende der Baugruppe), die Box trifft solche
    Koerper dann unabhaengig von der Normalenrichtung gar nicht erst - genau das hat
    beim ersten Live-Test ALLE 68 Koerper faelschlich als 'no-intersection' gemeldet.

    Wird jetzt sowohl fuer den flachen ALS AUCH (einmal PRO WAND-SEGMENT) fuer den
    gestuften Schnitt verwendet - siehe _wall_segments_from_step_sketch()."""
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

    # FCPROJECT-FIX (2026-11-08, live beim ersten Test des gestuften Schnitts aufgetreten):
    # an einer Stufen-Kante (Uebergang zwischen zwei Wandebenen) kann ein winziges, praktisch
    # entartetes Kantenstueck entstehen - Part.LineSegment() lehnt das mit "Both points are
    # equal" hart ab. Betrifft NUR den gestuften Fall (beim flachen Schnitt nie beobachtet,
    # da dort alle Kanten auf einer einzigen Ebene liegen). WICHTIG: der Vergleich muss auf
    # den 2D-PROJIZIERTEN Punkten laufen (genau die, die unten tatsaechlich in die
    # LineSegment-Konstruktion eingehen) - der volle 3D-Abstand allein reichte nicht: bei
    # Restrauschen in Z (aus der Mehrfach-Ebenen-Transformation des gestuften Schnitts)
    # konnten X/Y bereits identisch sein, obwohl der 3D-Abstand wegen der Z-Differenz noch
    # > Toleranz war - der erste Fix-Versuch mit (p1-p2).Length griff deshalb live NICHT.
    if math.hypot(p1.x - p2.x, p1.y - p2.y) < 1e-7:
        return []

    if isinstance(curve, (Part.Line, Part.LineSegment)):
        return [Part.LineSegment(App.Vector(p1.x, p1.y, 0), App.Vector(p2.x, p2.y, 0))]

    if isinstance(curve, Part.Circle):
        center = App.Vector(curve.Center.x, curve.Center.y, 0)
        if edge.Closed:
            return [Part.Circle(center, App.Vector(0, 0, 1), curve.Radius)]
        # FCPROJECT-FIX (2026-11-08, Nutzer-Report "offene Kontur/Artefakte im Sketch beim
        # Deckel" - live reproduziert: eine Kontur mit Boegen wurde durch diese Funktion
        # kaputt gemacht, obwohl die Rohkontur aus dem booleschen Schnitt nachweislich bereits
        # perfekt geschlossen war). Ein erster Versuch (Winkel per atan2 aus den lokalen
        # 2D-Punkten gegen einen neu aufgebauten Kreis) behob die Richtung des urspruenglichen
        # Fehlers (falsches Winkel-Bezugssystem zwischen 3D-Original und neuem 2D-Kreis),
        # erzeugte aber teils den FALSCHEN (grossen statt kleinen) Bogen - sichtbar als kleine
        # Schlaufe/Kringel an der Ecke im Screenshot des Nutzers. Grund: Part.ArcOfCircle(
        # circle, a1, a2) zeichnet IMMER im Gegenuhrzeigersinn von a1 nach a2 - ob das der
        # kurze oder der lange Weg ist, haengt von der (unbekannten) tatsaechlichen
        # Umlaufrichtung der Original-Kante ab, die atan2 allein nicht kennt.
        #
        # Robuste Loesung: 3-Punkt-Bogenkonstruktion (Part.Arc(start, mittlerer_Punkt, ende))
        # statt Winkel+Kreis-Konstruktion - dabei gibt es GAR KEINE Richtungs-Mehrdeutigkeit,
        # der Bogen ist durch 3 Punkte eindeutig bestimmt. Der mittlere Punkt kommt direkt von
        # der ORIGINAL-Kante (deren Parameterbereich ist nach dem Transform ins lokale
        # Koordinatensystem bereits korrekt), nicht ueber Winkel-Umrechnung.
        mid_param = (edge.FirstParameter + edge.LastParameter) / 2.0
        mid_3d = curve.value(mid_param)
        mid_point = App.Vector(mid_3d.x, mid_3d.y, 0)
        return [Part.Arc(App.Vector(p1.x, p1.y, 0), mid_point, App.Vector(p2.x, p2.y, 0))]

    try:
        bspline = curve.toBSpline(edge.FirstParameter, edge.LastParameter)
        return [bspline]
    except Exception:
        App.Console.PrintWarning(
            "FCProject: SectionSketch: unbekannter Kantentyp uebersprungen "
            f"({type(curve).__name__}).\n"
        )
        return []


def _get_or_create_part_sketch(doc, obj, existing_part_sketches, key, part_label):
    """Findet unter den zuletzt erzeugten Teil-Sketches (per SourcePartName, NICHT Label -
    siehe [[feedback_fcproject_never_use_label_for_addressing]]) den zu 'key' gehoerenden
    wieder, oder legt bei Bedarf einen neuen an. Reuse haelt Name/Farbe stabil ueber mehrere
    Recomputes, statt bei jedem Durchlauf alles neu zu erzeugen.

    'key' ist beim flachen Schnitt einfach der interne .Name des Quell-Teils; ueberspannt ein
    Teil beim gestuften Schnitt MEHRERE Wand-Segmente, enthaelt key zusaetzlich einen Wand-
    Index-Suffix (siehe execute()), damit jedes Segment seinen eigenen Sketch bekommt."""
    for sketch in existing_part_sketches:
        if getattr(sketch, "SourcePartName", None) == key:
            return sketch

    # "#" (im key bei mehreren Waenden) ist kein gueltiges Zeichen in FreeCADs internem
    # Objekt-.Name - durch "_w" ersetzen statt auf FreeCADs automatische Sanitisierung zu
    # vertrauen.
    safe_name = key.replace("#w", "_w")
    sketch = doc.addObject("Sketcher::SketchObject", f"{obj.Name}_{safe_name}")
    sketch.Label = f"Schnitt: {part_label}"
    sketch.addProperty(
        "App::PropertyString", "SourcePartName", "Section",
        "Reuse-Schluessel (Quell-Teil, ggf. + Wand-Segment) - fuer Wiederverwendung bei Recompute",
        locked=True
    )
    sketch.SourcePartName = key
    # Gleiches Driver-Muster wie zuvor bei der einen gemeinsamen Sketch-Property: normaler
    # PropertyLink AUF obj, nicht umgekehrt - sorgt dafuer, dass obj IMMER vor diesem Sketch
    # berechnet wird (obj.execute() schreibt erst hinein), ohne eine zirkulaere Abhaengigkeit
    # zu erzeugen (siehe Erklaerung bei PartSketches-Property weiter oben).
    sketch.addProperty(
        "App::PropertyLink", "Driver", "Section",
        "Erzeugendes SectionSketch-Feature (nur fuer die Berechnungsreihenfolge)"
    )
    sketch.Driver = obj

    # FCPROJECT-FIX (2026-11-08, zurueckgerollt): ein frueherer Versuch, diesen Sketch per
    # Absicht NICHT in assembly.Group aufzunehmen (um Assemblys Klick-/Leertaste-Abfangen fuer
    # die Sichtbarkeit zu umgehen), erzeugte live einen SCHLIMMEREN Folgefehler ("Sketcher::
    # SketchObject: ... links are out of scope", FreeCADs GeoFeatureGroupExtension::
    # areLinksValid() ueber das 'Driver'-PropertyLink zurueck auf obj, DAS weiterhin Mitglied
    # der Baugruppen-Gruppe ist) UND vermutlich den gemeldeten Platzierungs-Versatz ("liegen in
    # anderer Ebene") - GeoFeatureGroups wie Assembly::AssemblyObject wenden ihre eigene
    # Placement kumulativ auf ALLE Gruppen-Mitglieder an; ein Sketch ausserhalb der Gruppe
    # verliert diesen Beitrag und landet dadurch an der FALSCHEN Stelle, sobald die Baugruppe
    # selbst eine Placement != Identity hat. Deshalb bewusst wieder MIT assembly.addObject() -
    # fuer das Sichtbarkeits-Problem gibt es einen einfacheren Umweg: die "Sichtbarkeit"-Zeile
    # im Eigenschaften-Fenster (Daten/Ansicht-Tab) umgehen Assemblys Baum-Klick-Abfangen, weil
    # sie ueber einen anderen UI-Pfad dieselbe ViewObject.Visibility-Eigenschaft setzt.
    assembly = _find_assembly(doc)
    if assembly is not None and hasattr(assembly, "addObject"):
        assembly.addObject(sketch)

    return sketch


def _place_sketch_via_attachment(sketch, ref_obj, subname, desired_placement):
    """Setzt sketch.Placement auf desired_placement, aber NICHT direkt - stattdessen ueber
    FreeCADs eingebaute Attachment-Mechanik (AttachmentSupport/MapMode/AttachmentOffset), mit
    dem Offset so berechnet, dass am Ende exakt dieselbe Placement herauskommt.

    FCPROJECT-FIX (2026-11-08, Nutzer-Report "Attachment Support ist leer" - live bestaetigt
    als Ursache des pinken 'nicht angeheftet'-Symbols im Baum, siehe AttachEngine3D::
    _calculateAttachedPlacement() in freecad-source: wirft bei MapMode=Deactivated IMMER eine
    Exception, wodurch AttachExtension::isAttacherActive() dauerhaft False bleibt - genau die
    Bedingung fuer PartGui::ViewProviderAttachExtension::extensionMergeColorfullOverlayIcons(),
    das dann das Part_Detached-Icon zeigt. Einfach "irgendeine" Attachment-Referenz setzen
    wuerde aber sketch.Placement SOFORT ueberschreiben (live getestet) - deshalb wird hier
    zuerst mit AttachmentOffset=Identity angeheftet, die DADURCH entstehende Placement
    ausgelesen, und der noetige Offset bis zur gewuenschten Zielposition nachtraeglich
    draufgerechnet. Faellt auf direktes Placement-Setzen zurueck, falls die Referenz aus
    irgendeinem Grund nicht anheftbar ist (z.B. unbekannter Objekttyp) - dann bleibt zwar das
    kosmetische Symbol, aber die Platzierung ist trotzdem korrekt."""
    try:
        if subname and subname.startswith("Face"):
            sketch.AttachmentSupport = [(ref_obj, [subname])]
            sketch.MapMode = "FlatFace"
        else:
            sketch.AttachmentSupport = [(ref_obj, [""])]
            sketch.MapMode = "ObjectXY"
        sketch.AttachmentOffset = App.Placement()
        sketch.positionBySupport()
        base_placement = App.Placement(sketch.Placement)
        offset = base_placement.inverse().multiply(desired_placement)
        sketch.AttachmentOffset = offset
        sketch.positionBySupport()
        # FCPROJECT-FIX (2026-11-08, Folgefund beim GroundedJoint-Ausblenden): eine echte
        # Attachment-Anheftung (MapMode != Deactivated/Translate) setzt die Placement-Property
        # automatisch ReadOnly (Part::AttachExtension::updateAttacherVals(), freecad-source
        # AttachExtension.cpp: "getPlacement().setReadOnly(bAttached && mmode != mmTranslate)").
        # AssemblyObject::syncGroundedJoints() haelt GENAU dieses ReadOnly-Flag fuer das Zeichen
        # "dies ist ein unbewegliches Baugruppen-Teil, das einen Erdungs-Anker braucht" - legt
        # dadurch pro Schnitt-Sketch einen EIGENEN, voellig unnoetigen GroundedJoint an (live
        # bestaetigt: GroundedJoint001..006 erdeten nicht Bauteile, sondern unsere eigenen
        # SectionSketch-Objekte). Das Flag zurueckzusetzen aendert nichts an der Anheftung selbst
        # (AttachmentSupport/MapMode bleiben, isAttacherActive() bleibt True, Pink-Icon bleibt
        # weg) - es nimmt dem Solver nur den (falschen) Anlass, hierfuer einen Anker anzulegen.
        try:
            sketch.setPropertyStatus("Placement", "-ReadOnly")
        except Exception:
            pass
    except Exception as exc:
        App.Console.PrintWarning(
            f"FCProject: SectionSketch: Sketch '{sketch.Label}' konnte nicht per Attachment "
            f"platziert werden ({exc}) - verwende direkte Placement-Zuweisung.\n"
        )
        sketch.MapMode = "Deactivated"
        sketch.AttachmentSupport = []
        sketch.Placement = desired_placement


def _stitch_wire_geometry(wire_geoms, tol=1e-4):
    """Schweisst die Enden aufeinanderfolgender Sketcher-Geometrie-Elemente EINER Kontur
    zusammen, die eigentlich denselben Punkt teilen sollten, aber durch Rundungsfehler aus
    dem booleschen Schnitt nur FAST identisch sind (typischerweise < 1e-6mm daneben).

    FCPROJECT-FIX (2026-11-08, Nutzer-Report "Artefakte/offene Enden im Sketch, an Ecken
    erscheint ein kleines Kreissymbol"): jede Kante wurde bisher UNABHAENGIG von ihren
    Nachbarn in Sketcher-Geometrie umgewandelt (_edge_to_sketch_geometry() liest fuer jede
    Kante ihre EIGENEN Vertexes - bei einer geteilten Ecke zwischen zwei Kanten liefert OCC
    dafuer nicht immer bit-identische Punkte). Sketcher markiert daraufhin diese winzigen
    Luecken als offene Konturenden - genau das kleine Kreissymbol im Bild des Nutzers. Fix:
    NACHDEM alle Elemente EINER Kontur (Wire) erzeugt sind, das Ende jedes Elements an den
    Anfang des naechsten (inkl. Rueckschluss vom letzten zum ersten, da jede Kontur ein
    geschlossener Kreislauf ist) anpassen, WENN sie nah genug beieinander liegen, um
    eindeutig derselbe Punkt zu sein."""
    def get_endpoints(geom):
        try:
            return geom.StartPoint, geom.EndPoint
        except (AttributeError, Exception):
            return None, None

    count = len(wire_geoms)
    for i in range(count):
        current = wire_geoms[i]
        nxt = wire_geoms[(i + 1) % count]
        _, end_point = get_endpoints(current)
        start_point, _ = get_endpoints(nxt)
        if end_point is None or start_point is None:
            continue
        gap = (end_point - start_point).Length
        if 0 < gap < tol:
            # FCPROJECT-FIX (2026-11-08, Live-Absturz "Attribute 'StartPoint' of object
            # 'GeomBoundedCurve' is read-only"): nur Part.LineSegment erlaubt das direkte
            # Setzen von StartPoint - bei Part.ArcOfCircle/BSpline ist es nur lesbar (der
            # Punkt ergibt sich dort aus Kreis+Winkel bzw. Kontrollpunkten). Fuer diese Typen
            # bleibt die (durch den atan2-Fix oben ohnehin schon sehr kleine) Restluecke
            # unangetastet, statt abzustuerzen.
            try:
                nxt.StartPoint = end_point
            except Exception:
                pass


def _rebuild_sketch_geometry(sketch, local_wires):
    # FCPROJECT-FIX (2026-11-10, Nutzer-Report "Icon schaltet um, Geometrie bleibt sichtbar":
    # live per echter Maus/Kontextmenue reproduziert, siehe
    # [[project_fcproject_sectionsketch_next_checks]]): dieser komplette Geometrie-Rebuild
    # laeuft UNCONDITIONAL bei JEDEM execute() von obj - und obj.Active=True heisst, execute()
    # laeuft bei JEDEM Dokument-Recompute neu, nicht nur bei tatsaechlichen Geometrie-
    # Aenderungen. sketch.recompute() + signalChangeIcon() weiter unten (noetig fuer den
    # pinkes-Icon-Fix vom 2026-11-08) erzwingen dabei einen kompletten Coin3D-Redraw des
    # Sketches - der scheint den sichtbaren Zustand dabei IMMER auf sichtbar zurueckzusetzen,
    # unabhaengig vom tatsaechlichen Wert der Visibility-Eigenschaft (die selbst korrekt
    # bestehen bleibt - nur der tatsaechliche Redraw ignoriert sie). Sichtbarkeit davor merken
    # und danach per echter Property-Zuweisung erzwungen neu anwenden, damit der Redraw sie
    # wieder respektiert (siehe ViewProviderDocumentObject::onChanged() in freecad-source,
    # ruft bei Visibility-Aenderung zuverlaessig show()/hide() auf).
    was_visible = sketch.ViewObject.Visibility if _GUI_AVAILABLE and sketch.ViewObject else None
    sketch.deleteAllGeometry()
    geoms = []
    for wire_edges in local_wires:
        wire_geoms = []
        for edge in wire_edges:
            wire_geoms.extend(_edge_to_sketch_geometry(edge))
        if len(wire_geoms) > 1:
            _stitch_wire_geometry(wire_geoms)
        geoms.extend(wire_geoms)
    if geoms:
        sketch.addGeometry(geoms, False)
        # FCPROJECT-FIX (2026-11-08, Nutzer-Report "pinkes Warn-Symbol stoert"): ohne jede
        # Constraint zeigt FreeCAD auf dem Sketch-Icon im Baum automatisch das Standard-
        # Warnsymbol "Sketcher_NotFullyConstrained" (ViewProviderSketch::
        # mergeColorfulOverlayIcons() in src/Mod/Sketcher/Gui/ViewProviderSketch.cpp) - obwohl
        # das hier gar kein Problem ist, diese Sketches werden nie von Hand editiert, sondern
        # bei jedem Recompute komplett neu aus der Schnittgeometrie erzeugt. Jedes Element per
        # Block-Constraint fixieren ist die FreeCAD-ueblicherweise empfohlene Vorgehensweise
        # fuer reine Referenz-/Anzeige-Geometrie und macht den Sketch "richtig" voll
        # bestimmt, statt das Warnsymbol nur optisch zu unterdruecken.
        sketch.addConstraint([
            Sketcher.Constraint('Block', i) for i in range(len(geoms))
        ])
        # FCPROJECT-FIX (2026-11-08, Nutzer-Report "pinkes Symbol trotz FullyConstrained=True,
        # Teil-Sketches unsichtbar bis ein UNABHAENGIGER Recompute (HideBodies-Toggle)
        # stattfindet"): sketch wird hier WAEHREND obj.execute() veraendert (Geometrie, dann
        # separat Constraints) - die GUI (Baum-Icon-Overlay UND 3D-Darstellung) aktualisiert
        # sich dabei offenbar anhand eines Zwischenzustands (Geometrie gesetzt, Constraints
        # noch nicht), noch BEVOR addConstraint() oben durchgelaufen ist, und wird danach
        # nicht mehr von selbst neu gezeichnet (bis irgendein VOELLIG ANDERER Recompute das
        # erzwingt). sketch.recompute() erzwingt Sketchers eigenen internen Durchlauf (inkl.
        # Loesen + UI-Benachrichtigung) JETZT, mit dem fertigen Endzustand, statt auf den
        # naechsten ohnehin stattfindenden Dokument-Recompute zu warten.
        sketch.recompute()
        # FCPROJECT-FIX (2026-11-08, Nutzer-Report "pinkes Symbol trotzdem noch da, Sichtbarkeit
        # erst nach Berechnung"): sketch.recompute() allein reicht nicht - der Baum-Icon-Cache
        # (das zusammengesetzte Icon inkl. Warnsymbol-Overlay) wird offenbar nur bei bestimmten
        # Signalen neu gezeichnet, nicht automatisch bei jeder Shape-/Constraint-Aenderung.
        # signalChangeIcon() ist genau der von FreeCADs ViewProvider dafuer vorgesehene,
        # explizite Trigger (Gui::ViewProviderPy::signalChangeIcon(), src/Gui/
        # ViewProviderPyImp.cpp) - zwingt den Baum, das Icon (und damit auch den fuer die
        # 3D-Darstellung erforderlichen Redraw) jetzt neu abzufragen, statt erst beim naechsten,
        # VOELLIG unabhaengigen Recompute.
        if _GUI_AVAILABLE and sketch.ViewObject:
            sketch.ViewObject.signalChangeIcon()
            if was_visible is not None:
                sketch.ViewObject.Visibility = was_visible


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
        # FCPROJECT-FEATURE (2026-11-08, Nutzerwunsch "gestufter Schnitt, der in einem Sketch
        # definiert ist"): optional - ein vom Nutzer auf der ReferencePlane angelegter Sketch
        # mit einem OFFENEN Linienzug (nur Geradensegmente, siehe _wall_segments_from_step_sketch()), der
        # statt der flachen Ebene einen gestuften/gejogten Schnitt vorgibt. Leer/None ->
        # normaler flacher Schnitt wie bisher (volle Abwaertskompatibilitaet).
        if not hasattr(obj, 'StepSketch'):
            # Bewusst normaler (nicht versteckter) PropertyLink, anders als die Ausgabe-Links
            # (PartSketches/CombinedShape, siehe unten): StepSketch ist eine EINGABE des
            # Nutzers, nicht eine von execute() erzeugte Ausgabe - die Abhaengigkeitsrichtung
            # soll hier normal sein ("obj haengt vom StepSketch ab"), damit FreeCAD obj
            # automatisch neu rechnet, wenn der Nutzer den Linienzug aendert.
            obj.addProperty(
                "App::PropertyLink", "StepSketch", "Section",
                "Optional: Sketch mit gestuftem Linienzug auf der ReferencePlane, ersetzt den flachen Schnitt"
            )
        # FCPROJECT-FEATURE (2026-11-08, Nutzerwunsch "Teile durch Farben unterscheiden"):
        # ersetzt die fruehere EINZELNE 'Sketch'-Property. FreeCADs Sketcher kennt keine
        # Farbe pro Geometrie-Element (nur pro ganzem Sketch-Objekt, ViewObject.LineColor) -
        # deshalb jetzt EIN Sketch PRO geschnittenem Quell-Teil (eigene Farbe je Teil,
        # siehe _color_for_part()), PLUS ein zusammengesetztes, nicht editierbares
        # Part::Feature (CombinedShape) mit allen Kanten in einem Stueck - fuer TechDraw/
        # Weiterverwendung, wie vorher der eine gemeinsame Sketch (auf Nutzerwunsch
        # bewusst zusaetzlich erhalten, nicht ersetzt).
        if not hasattr(obj, 'PartSketches'):
            # PropertyLinkListHidden aus demselben Grund wie zuvor 'Sketch' (siehe Git-
            # Historie dieser Zeile): rein informativ, NICHT Teil des Abhaengigkeitsgraphen -
            # execute() SCHREIBT in diese Sketches, die Abhaengigkeitsrichtung kommt
            # stattdessen von jedem Sketch' eigenem 'Driver'-Link auf obj (siehe
            # _get_or_create_part_sketch()).
            obj.addProperty(
                "App::PropertyLinkListHidden", "PartSketches", "Section",
                "Ein Sketch pro geschnittenem Quell-Teil, je in eigener Farbe", locked=True
            )
        if not hasattr(obj, 'CombinedShape'):
            obj.addProperty(
                "App::PropertyLinkHidden", "CombinedShape", "Section",
                "Alle Schnittkonturen zusammen als EIN nicht editierbares Objekt (fuer TechDraw/Weiterverwendung)",
                locked=True
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
        # FCPROJECT-FEATURE (2026-11-08, Nutzerwunsch "bei 50 Teilen alle Koerper einzeln
        # auszublenden ist aufwendig"): wenn aktiv, blendet execute() die gerade
        # geschnittenen Koerper automatisch aus (und beim Abschalten/Entfernen wieder ein),
        # statt das dem Nutzer von Hand zu ueberlassen.
        if not hasattr(obj, 'HideBodies'):
            obj.addProperty(
                "App::PropertyBool", "HideBodies", "Section",
                "Blendet die geschnittenen Koerper automatisch aus, damit nur noch der Schnitt sichtbar ist"
            )
            obj.HideBodies = False
        if not hasattr(obj, 'AutoHiddenBodies'):
            # Hidden Buchhaltung: NUR die Koerper, die WIR wegen HideBodies ausgeblendet
            # haben - damit beim Abschalten/Loeschen genau die richtigen wieder sichtbar
            # werden (nicht Koerper, die der Nutzer selbst schon vorher ausgeblendet hatte).
            obj.addProperty(
                "App::PropertyLinkListHidden", "AutoHiddenBodies", "Section",
                "Von HideBodies aktuell ausgeblendete Koerper (rein interne Buchhaltung)",
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

        doc = obj.Document
        existing_part_sketches = list(obj.PartSketches)
        existing_combined = obj.CombinedShape

        # 1. Durchlauf: sichtbare Koerper einsammeln UND eine gemeinsame Box-Groesse
        # bestimmen, die von 'base' aus in jede Richtung weit genug reicht, um auch weit
        # entfernte Teile der Baugruppe noch zu erfassen (siehe Docstring von
        # _section_faces_of_solid - eine rein lokale Groesse pro Solid reicht dafuer nicht).
        # Koerper, die WIR (HideBodies) beim letzten Durchlauf ausgeblendet haben, muessen
        # trotz Visibility=False weiterhin als Kandidat gelten - sonst wuerden sie durch
        # das eigene Ausblenden beim naechsten Recompute aus dem Schnitt herausfallen.
        auto_hidden_before = set(obj.AutoHiddenBodies)

        candidates = []
        candidate_global_shapes = {}
        combined_bbox = App.BoundBox(base, base)
        skip_objs = set(existing_part_sketches)
        if existing_combined is not None:
            skip_objs.add(existing_combined)
        if obj.StepSketch is not None:
            skip_objs.add(obj.StepSketch)
        for candidate in doc.Objects:
            if candidate is obj or candidate in skip_objs:
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
            if vis is None:
                continue
            if not vis.Visibility and candidate not in auto_hidden_before:
                continue
            if not hasattr(candidate, "Shape") or candidate.Shape is None or candidate.Shape.isNull():
                continue
            if not candidate.Shape.Solids:
                continue
            # FCPROJECT-FIX (2026-11-08, siehe _ancestor_placement()): candidate.Shape ist nur
            # lokal zur umschliessenden Baugruppe - einmal pro Kandidat in ECHTE globale
            # Koordinaten umrechnen und das Ergebnis fuer den Rest von execute() (BoundBox UND
            # der eigentliche Schnitt weiter unten) wiederverwenden, statt mehrfach neu zu
            # transformieren.
            global_shape = candidate.Shape.copy()
            global_shape.transformShape(_ancestor_placement(candidate).toMatrix(), True)
            candidate_global_shapes[candidate] = global_shape
            candidates.append(candidate)
            combined_bbox.add(global_shape.BoundBox)

        diagonal = combined_bbox.DiagonalLength
        if not math.isfinite(diagonal) or diagonal <= 0.0:
            diagonal = 0.0
        size = max(diagonal * 2, 100.0)

        # Wand-Liste bestimmen: im flachen Standardfall genau EINE Wand (die ReferencePlane
        # selbst, mit dem bereits berechneten plane_placement/inv_matrix) - bei gesetztem
        # StepSketch eine WAND PRO STUFEN-SEGMENT, jede mit ihrer EIGENEN, lokal berechneten
        # Placement/inv_matrix (siehe _wall_segments_from_step_sketch() fuer die Begruendung,
        # warum das NICHT alles in EINER gemeinsamen Projektion gehen kann). Jede Wand wird
        # danach komplett unabhaengig wie ein ganz normaler flacher Schnitt behandelt - ein
        # gestufter Schnitt ist technisch nichts anderes als mehrere unabhaengige flache
        # Schnitte hintereinander.
        step_sketch = obj.StepSketch
        walls = None
        if step_sketch is not None and hasattr(step_sketch, "Shape") and step_sketch.Shape and step_sketch.Shape.Wires:
            try:
                local_wire = step_sketch.Shape.Wires[0].copy()
                local_wire.transformShape(inv_matrix, True)
                local_segments = _wall_segments_from_step_sketch(local_wire)
                walls = []
                for seg_base_local, seg_normal_local in local_segments:
                    wall_base = plane_placement.multVec(seg_base_local)
                    wall_normal = plane_placement.Rotation.multVec(seg_normal_local)
                    wall_placement = App.Placement(wall_base, App.Rotation(App.Vector(0, 0, 1), wall_normal))
                    walls.append((wall_base, wall_normal, wall_placement, wall_placement.inverse().toMatrix()))
            except Exception as exc:
                App.Console.PrintWarning(
                    f"FCProject: SectionSketch '{obj.Label}': gestufter Schnitt fehlgeschlagen "
                    f"({exc}) - falle auf flachen Schnitt zurueck.\n"
                )
                walls = None
        if walls is None:
            walls = [(base, normal, plane_placement, inv_matrix)]
        multi_wall = len(walls) > 1

        # 2. Durchlauf: pro Wand UND pro Teil schneiden - Kanten PRO (TEIL, WAND) gesammelt
        # (nicht mehr in einer flachen Liste), damit jedes Teil seinen eigenen, eingefaerbten
        # Sketch bekommt (siehe Modul-Kopf). Beim flachen Standardfall (EINE Wand) verhaelt
        # sich das exakt wie vorher: ein Sketch pro Teil.
        solids_found = []
        edges_by_key = {}  # (candidate.Name, wall_idx) -> (candidate, wall_placement, [[local_edge, ...], ...])
        # (die dritte Komponente ist eine Liste von KONTUREN, jede ihrerseits eine Liste von
        # Kanten - die Kontur-Gruppierung braucht _stitch_wire_geometry() in
        # _rebuild_sketch_geometry(), um Kanten-Enden nur INNERHALB derselben Kontur
        # zusammenzuschweissen, nicht ueber mehrere unabhaengige Konturen hinweg.)
        status_labels = {}  # status -> [Label, ...], nur fuer status != "ok"

        # CombinedShape (siehe Schritt 4 unten) braucht alle Kanten in EINEM gemeinsamen
        # Koordinatensystem - genommen wird dafuer WELTKOORDINATEN (combined_obj.Placement
        # bleibt Identity), weil die einzelnen Wand-Placements bei einem gestuften Schnitt
        # NICHT alle gleich sind (anders als im flachen Fall) und es deshalb keine einzelne
        # gemeinsame lokale Ebene gibt, in die man stattdessen transformieren koennte.
        world_edges = []

        for wall_idx, (wall_base, wall_normal, wall_placement, wall_inv_matrix) in enumerate(walls):
            for candidate in candidates:
                if candidate not in solids_found:
                    solids_found.append(candidate)
                part_wires = []  # Liste von Kanten-Listen, EINE pro Kontur (siehe _rebuild_sketch_geometry)
                for solid in candidate_global_shapes[candidate].Solids:
                    faces, status = _section_faces_of_solid(solid, wall_base, wall_normal, size)
                    if status != "ok":
                        status_labels.setdefault(status, []).append(candidate.Label)
                        continue
                    for face in faces:
                        for wire in face.Wires:
                            local_wire_edges = []
                            # FCPROJECT-FIX (2026-11-08, Nutzer-Report "offene Kontur trotz
                            # _stitch_wire_geometry()"): wire.Edges liefert KEINE garantiert
                            # fortlaufende Reihenfolge (OCC-Topologie-Rohdaten) - fuer manche
                            # Konturen kamen Kanten in einer Reihenfolge zurueck, in der
                            # aufeinanderfolgende Listenelemente gar nicht die echten Nachbarn
                            # in der Kontur waren, wodurch _stitch_wire_geometry() die falschen
                            # (Nicht-)Punktepaare verglich. wire.OrderedEdges liefert dagegen
                            # garantiert die tatsaechliche Lauf-Reihenfolge entlang der Kontur.
                            for edge in wire.OrderedEdges:
                                world_edges.append(edge.copy())
                                local_edge = edge.copy()
                                local_edge.transformShape(wall_inv_matrix, True)
                                local_wire_edges.append(local_edge)
                            if local_wire_edges:
                                part_wires.append(local_wire_edges)
                if part_wires:
                    key = candidate.Name if not multi_wall else f"{candidate.Name}#w{wall_idx}"
                    edges_by_key[key] = (candidate, wall_placement, part_wires)

        all_local_edges = world_edges
        obj.Dependencies = solids_found

        # HideBodies-Abgleich: nur die Koerper ein-/ausblenden, die WIR selbst verwalten
        # (auto_hidden_before) - Koerper, die der Nutzer unabhaengig davon schon selbst
        # ausgeblendet hatte, bleiben unberuehrt (die erscheinen hier gar nicht erst in
        # solids_found/candidates, siehe Visibility-Filter oben).
        #
        # FCPROJECT-FEATURE (2026-11-08, Nutzerwunsch "GroundedJoint Symbole ausblenden" -
        # "die sollen ab Anfang an nach der Schnitterstellung ausgeblendet sein"): die
        # Anker-/Erdungs-Symbole der GroundedJoint-Objekte werden ausgeblendet. GroundedJoint
        # ist in FreeCADs Assembly-Werkbench kein eigener TypeId, sondern ein normales
        # Joint-Objekt mit dem festen internen Namen "GroundedJoint" (ggf. "GroundedJoint001"
        # usw. bei mehreren geerdeten Teilen) - deshalb per Namenspraefix gesucht, nicht per
        # Typ. Live-Fund: bei einer Baugruppe mit Unterbaugruppen (jede als eigenes, per
        # App::Link eingebundenes PDM-Dokument - siehe Projekt-Konvention) liegt JEDE
        # Unterbaugruppe mit ihrem EIGENEN GroundedJoint-Objekt in einem EIGENEN Dokument,
        # nicht in 'doc' selbst - eine Suche nur in doc.Objects fand deshalb nur 1 von 7
        # GroundedJoint-Objekten. Alle aktuell offenen Dokumente durchsuchen statt nur 'doc'.
        #
        # FCPROJECT-FIX (2026-11-10, Nutzer-Report "das ist nicht korrekt ich sollen bodies
        # gezeigt werden und nicht joints"): bis hierhin war GroundedJoint an dieselbe
        # AutoHiddenBodies-Buchhaltung wie die Koerper gekoppelt - beim Ausschalten von
        # HideBodies (Koerper absichtlich wieder einblenden, um sie zu inspizieren) wurde
        # dadurch FAELSCHLICH auch das GroundedJoint-Symbol wieder sichtbar. Die urspruengliche
        # Nutzeranforderung war aber "von Anfang an ausgeblendet", UNABHAENGIG vom
        # HideBodies-Umschalter - deshalb jetzt komplett entkoppelt: GroundedJoints werden bei
        # jedem execute() unconditional ausgeblendet und NIE durch die
        # HideBodies=False-Wiederherstellung erfasst.
        grounded_joints = [
            o
            for d in App.listDocuments().values()
            for o in d.Objects
            if o.Name.startswith("GroundedJoint")
        ]
        if _GUI_AVAILABLE:
            for g in grounded_joints:
                vis = getattr(g, "ViewObject", None)
                if vis is not None:
                    vis.Visibility = False

            if obj.HideBodies:
                new_auto_hidden = []
                for body in solids_found:
                    vis = getattr(body, "ViewObject", None)
                    if vis is None:
                        continue
                    vis.Visibility = False
                    new_auto_hidden.append(body)
                still_hidden = set(solids_found)
                for old_body in auto_hidden_before:
                    if old_body not in still_hidden:
                        vis = getattr(old_body, "ViewObject", None)
                        if vis is not None:
                            vis.Visibility = True
                obj.AutoHiddenBodies = new_auto_hidden
            elif auto_hidden_before:
                for old_body in auto_hidden_before:
                    vis = getattr(old_body, "ViewObject", None)
                    if vis is not None:
                        vis.Visibility = True
                obj.AutoHiddenBodies = []

        # 3. Pro (Teil, Wand) einen Sketch finden/anlegen (reuse per SourcePartName statt
        # jedes Mal neu zu erzeugen - haelt Namen stabil ueber mehrere Recomputes) und die
        # alten, jetzt nicht mehr gebrauchten Sketches entfernen (Teil ausgeblendet/geloescht,
        # oder Wand-Anzahl hat sich geaendert). Farbe kommt bewusst vom ECHTEN Teil-Namen
        # (candidate.Name), nicht vom (ggf. Wand-Suffix enthaltenden) Reuse-Key - mehrere
        # Sketches desselben Teils (weil es mehrere Stufen-Waende ueberspannt) bekommen so
        # trotzdem dieselbe Farbe.
        reused_keys = set(edges_by_key.keys())
        new_part_sketches = []
        for key, (candidate, wall_placement, part_wires) in edges_by_key.items():
            sketch = _get_or_create_part_sketch(doc, obj, existing_part_sketches, key, candidate.Label)
            _place_sketch_via_attachment(sketch, ref_obj, subname, wall_placement)
            _rebuild_sketch_geometry(sketch, part_wires)
            if _GUI_AVAILABLE and sketch.ViewObject:
                color = _color_for_part(candidate.Name)
                sketch.ViewObject.LineColor = color
                sketch.ViewObject.PointColor = color
            new_part_sketches.append(sketch)

        for old_sketch in existing_part_sketches:
            if getattr(old_sketch, "SourcePartName", None) not in reused_keys:
                try:
                    doc.removeObject(old_sketch.Name)
                except Exception as exc:
                    App.Console.PrintWarning(
                        f"FCProject: SectionSketch '{obj.Label}': verwaister Teil-Sketch "
                        f"'{old_sketch.Name}' konnte nicht entfernt werden: {exc}\n"
                    )
        obj.PartSketches = new_part_sketches

        # 4. Zusaetzlich ALLE Kanten zusammen als EIN nicht editierbares Objekt (fuer
        # TechDraw/Weiterverwendung "der ganze Schnitt als ein Stueck", wie vorher der eine
        # gemeinsame Sketch - auf Nutzerwunsch bewusst zusaetzlich erhalten).
        combined_obj = existing_combined
        if combined_obj is None:
            combined_obj = doc.addObject("Part::Feature", f"{obj.Name}_Combined")
            combined_obj.Label = f"Gesamtschnitt: {ref_obj.Label}"
            if _GUI_AVAILABLE and combined_obj.ViewObject:
                combined_obj.ViewObject.Visibility = False
            if not hasattr(combined_obj, "Driver"):
                combined_obj.addProperty(
                    "App::PropertyLink", "Driver", "Section",
                    "Erzeugendes SectionSketch-Feature (nur fuer die Berechnungsreihenfolge)"
                )
            combined_obj.Driver = obj
            # FCPROJECT-FIX (2026-11-08, zurueckgerollt - siehe ausfuehrlicher Kommentar in
            # _get_or_create_part_sketch()): ein Versuch, combined_obj NICHT in assembly.Group
            # aufzunehmen (wegen Assemblys Klick-/Leertaste-Abfangen fuer die Sichtbarkeit),
            # erzeugte live einen schlimmeren Folgefehler (GeoFeatureGroup-Scope-Warnung ueber
            # das 'Driver'-PropertyLink zurueck auf obj) und vermutlich den gemeldeten
            # Platzierungs-Versatz - deshalb wieder MIT assembly.addObject(). Sichtbarkeit laesst
            # sich stattdessen zuverlaessig ueber die "Sichtbarkeit"-Zeile im Eigenschaften-
            # Fenster (Daten/Ansicht-Tab) umschalten, nicht nur per Baum-Klick/Leertaste.
            assembly = _find_assembly(doc)
            if assembly is not None and hasattr(assembly, "addObject"):
                assembly.addObject(combined_obj)
        elif combined_obj.Label.startswith("Schnitt-Sketch: ") and combined_obj.Label.endswith(" (Gesamt)"):
            # FCPROJECT-FIX (2026-11-10, Nutzerwunsch "Label vom Gesamtschnitt aendern,
            # alt Schnitt-Sketch: auf Gesamtschnitt:"): die alte Label-Konvention wiederholte
            # praktisch den Ordner-Namen ("Schnitt-Sketch: X" Ordner + "Schnitt-Sketch: X
            # (Gesamt)" Kind) - sah im Baum wie ein verdoppelter Eintrag aus. Migriert nur das
            # Label bestehender, noch nicht manuell umbenannter Objekte (Driver/assembly-
            # Zugehoerigkeit bestehen bei diesen schon seit ihrer urspruenglichen Erstellung) -
            # echte Nutzer-Umbenennungen matchen dieses Muster nicht und bleiben unangetastet.
            combined_obj.Label = f"Gesamtschnitt: {ref_obj.Label}"
        # Placement bewusst Identity (NICHT plane_placement): all_local_edges enthaelt
        # bereits WELTKOORDINATEN (siehe oben) - bei mehreren Waenden (gestufter Schnitt)
        # gibt es keine einzelne gemeinsame lokale Ebene mehr, in die man stattdessen
        # transformieren koennte.
        # FCPROJECT-FIX (2026-11-10, gleicher Grund wie in _rebuild_sketch_geometry() -
        # Shape-Zuweisung laeuft unconditional bei jedem execute() und scheint die
        # tatsaechliche 3D-Sichtbarkeit zurueckzusetzen, unabhaengig vom Visibility-Wert):
        # Sichtbarkeit merken, danach per echter Property-Zuweisung erneut anwenden.
        combined_was_visible = (
            combined_obj.ViewObject.Visibility if _GUI_AVAILABLE and combined_obj.ViewObject else None
        )
        combined_obj.Placement = App.Placement()
        combined_obj.Shape = Part.makeCompound([e.copy() for e in all_local_edges]) if all_local_edges else Part.Shape()
        obj.CombinedShape = combined_obj
        if combined_was_visible is not None and combined_obj.ViewObject.Visibility != combined_was_visible:
            combined_obj.ViewObject.Visibility = combined_was_visible
        if _GUI_AVAILABLE and combined_obj.ViewObject:
            # FCPROJECT-FIX (2026-11-10, Nutzerbeobachtung "Linienfarbe aendert sich vom
            # Gelb, sonst kommt schwarze Linie dazu"): anders als die Teil-Sketches (siehe
            # oben, LineColor explizit pro Teil gesetzt) bekam der Gesamtschnitt bisher NIE
            # eine eigene LineColor/PointColor - er fiel auf den undefinierten Default
            # zurueck, der je nach zuletzt beteiligten Kanten/Teilen wechselte (mal "gelb"
            # wirkend, mal schwarz). Fixe, einheitliche Farbe statt pro-Teil-Hash, weil der
            # Gesamtschnitt bewusst ALLE Teile zusammengefasst zeigt.
            combined_obj.ViewObject.LineColor = (0.0, 0.0, 0.0)
            combined_obj.ViewObject.PointColor = (0.0, 0.0, 0.0)

        # FCPROJECT-FIX (2026-11-11, Nutzer-Report "Gesamtschnitt scheint 2 mal zu sein"): obj ist
        # "Part::FeaturePython", damit ein Darstellungsmodus existiert und Sichtbarkeit-Umschalten
        # funktioniert (siehe make_section_sketch()) - dafuer reicht aber der TYP, die Shape darf
        # leer bleiben (per Sonde verifiziert: Umschalten geht auch mit Null-Shape). Eine Kopie
        # der Gesamtschnitt-Geometrie hier liess den Ordner den kompletten Schnitt selbst
        # mitzeichnen - ein zweiter Gesamtschnitt ohne eigene Baum-Zeile, der sich nicht getrennt
        # ausblenden liess und exakt ueber Gesamtschnitt und Teilschnitten lag. Bedingt, damit
        # Schnitte aus der Zwischenversion ihre Kopie beim naechsten Recompute verlieren, ohne
        # bei jedem Durchlauf eine Property anzufassen.
        if not obj.Shape.isNull():
            obj.Shape = Part.Shape()

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
        # "Koerper verfehlt die Schnittebene" ist beim gestuften Schnitt (mehrere Waende,
        # typischerweise trifft jede Wand nur einen Teil der Baugruppe) der NORMALFALL, kein
        # Fehler - deshalb bewusst nur ins Report-View/Log (PrintMessage), NICHT als Warnung
        # (PrintWarning liefe sonst bei jedem Recompute als Popup/Toast in der Notification-
        # Area auf, Nutzerwunsch war genau das zu vermeiden). "cut-failed"/"invalid-boundbox"
        # sind echte Probleme und bleiben deshalb Warnungen.
        _ROUTINE_STATUSES = {"no-intersection", "fully-removed", "no-matching-face"}
        for status, labels in status_labels.items():
            printer = App.Console.PrintMessage if status in _ROUTINE_STATUSES else App.Console.PrintWarning
            printer(
                f"FCProject: SectionSketch '{obj.Label}': {_STATUS_MESSAGES.get(status, status)} - "
                f"betrifft {len(labels)} Koerper: {', '.join(labels)}.\n"
            )
        if not all_local_edges and solids_found and not status_labels:
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
            self._last_visible = vobj.Visibility

        def claimChildren(self):
            children = list(self.Object.PartSketches)
            if self.Object.CombinedShape is not None:
                children.append(self.Object.CombinedShape)
            return children

        def getIcon(self):
            return os.path.join(ICON_DIR, 'section_sketch.svg')

        def onChanged(self, vobj, prop):
            # FCPROJECT-FEATURE (2026-11-10, Nutzerwunsch): der Container selbst hat keine
            # eigene Shape (reine Verwaltung von PartSketches/CombinedShape, siehe
            # SectionSketchProxy._add_properties) - Sichtbarkeit umschalten (Baum-Leertaste/
            # Kontextmenue/Augen-Icon) hatte deshalb bisher KEINE sichtbare Wirkung in der
            # 3D-Ansicht. Kaskadiert die Container-Sichtbarkeit jetzt auf alle Kinder, damit
            # Ein-/Ausblenden des Ordners tatsaechlich den angezeigten Inhalt umschaltet.
            if prop != "Visibility":
                return
            obj = getattr(vobj, "Object", None)
            if obj is None or getattr(obj.Document, "Restoring", False):
                return
            visible = vobj.Visibility
            if visible == getattr(self, "_last_visible", None):
                return  # jede explizite Zuweisung feuert onChanged - nur echte Aenderungen zaehlen
            self._last_visible = visible
            for sketch in getattr(obj, "PartSketches", []):
                sketch_vis = getattr(sketch, "ViewObject", None)
                if sketch_vis is not None:
                    sketch_vis.Visibility = visible
            # Ausblenden blendet auch den Gesamtschnitt aus; Einblenden laesst ihn unveraendert
            # (Initialzustand: ausgeblendet, der Nutzer schaltet ihn bei Bedarf einzeln zu).
            combined = getattr(obj, "CombinedShape", None)
            if combined is not None and not visible:
                combined_vis = getattr(combined, "ViewObject", None)
                if combined_vis is not None:
                    combined_vis.Visibility = False

            # Nutzerwunsch 2026-11-11: Schnitt sichtbar <-> Koerper unsichtbar, und umgekehrt.
            # HideBodies mitfuehren, damit der naechste Recompute (execute()) denselben Zustand
            # herstellt statt ihn zurueckzudrehen; Koerper sofort direkt schalten, damit der
            # Effekt ohne Recompute sichtbar ist.
            bodies = list(obj.Dependencies) if visible else list(obj.AutoHiddenBodies)
            for body in bodies:
                body_vis = getattr(body, "ViewObject", None)
                if body_vis is not None:
                    body_vis.Visibility = not visible
            if obj.HideBodies != visible:
                obj.HideBodies = visible
            obj.AutoHiddenBodies = bodies if visible else []

        def doubleClicked(self, vobj):
            # Kein eigenes TaskPanel bisher - Doppelklick markiert zumindest die aktuell
            # verwendete Referenzebene, damit man sie im Modellbaum wiederfindet.
            ref = vobj.Object.ReferencePlane
            if ref and ref[0] is not None:
                Gui.Selection.clearSelection()
                Gui.Selection.addSelection(ref[0])
            return True

        def onDelete(self, vobj, subelements):
            # Von HideBodies ausgeblendete Koerper sollen nicht fuer immer unsichtbar
            # bleiben, nur weil dieses SectionSketch-Objekt geloescht wird. Wichtig: dieser
            # Hook sitzt bewusst auf dem VIEW PROVIDER (nicht dem DocumentObject-Proxy) -
            # Gui::CommandDoc.cpp ruft beim Loeschen "vp->onDelete(...)" auf, nicht die
            # Proxy-Methode des eigentlichen Objekts.
            for body in getattr(vobj.Object, "AutoHiddenBodies", []):
                vis = getattr(body, "ViewObject", None)
                if vis is not None:
                    vis.Visibility = True

            # FCPROJECT-FIX (2026-11-10, Nutzerwunsch): Loeschen des Ordners (Containers)
            # liess bisher PartSketches und CombinedShape als Karteileichen im Dokument
            # zurueck - claimChildren() zeigte sie zwar NICHT mehr im Baum (ihr einziger
            # Elternknoten war weg), aber sie blieben als echte, ungenutzte Objekte im
            # Dokument bestehen. Kopie der Liste, bevor geloescht wird (Live-Mutation der
            # PropertyLinkListHidden waehrend der Schleife waere sonst fehleranfaellig).
            doc = vobj.Object.Document
            children = list(getattr(vobj.Object, "PartSketches", []))
            combined = getattr(vobj.Object, "CombinedShape", None)
            if combined is not None:
                children.append(combined)
            for child in children:
                if child is not None and doc.getObject(child.Name) is not None:
                    doc.removeObject(child.Name)
            return True

        def __getstate__(self):
            return None

        def __setstate__(self, state):
            return None


def make_section_sketch(doc, assembly, ref_obj, subname):
    """Erstellt das SectionSketch-Feature (analog zu make_linear_pattern/
    make_circular_pattern) und haengt es in die Baugruppe ein. Die Teil-Sketches + das
    zusammengesetzte CombinedShape-Objekt werden NICHT hier vorab angelegt - deren Anzahl
    steht erst beim ersten execute()-Lauf fest (ein Sketch pro tatsaechlich geschnittenem
    Teil, siehe _get_or_create_part_sketch())."""
    doc.openTransaction("FCProject Section Sketch")
    try:
        # FCPROJECT-FIX (2026-11-10, Nutzer-Frage "warum legst du Schnitte in nicht
        # Geometrie-Objekte": traf den eigentlichen Kern des Umschalt-Bugs): "App::FeaturePython"
        # hat KEINE Shape-Eigenschaft - FreeCADs ViewProvider::isShow() (prueft den Coin3D-
        # Darstellungsmodus-Switch) bleibt dadurch PERMANENT False, egal was die Visibility-
        # Eigenschaft sagt. ViewProvider::toggleVisibility() (Leertaste/Kontextmenue/
        # Std_ToggleVisibility-Befehl) prueft GENAU isShow() und landet dadurch IMMER im
        # else-Zweig (show()) - Sichtbarkeit laesst sich darueber nie auf "versteckt" schalten,
        # bleibt nach jedem Umschalt-Versuch wieder bei True haengen (live reproduziert,
        # 2026-11-10). "Part::FeaturePython" bringt einen echten Darstellungsmodus mit,
        # damit isShow()/toggleVisibility() korrekt arbeiten - die Shape selbst bleibt leer
        # (siehe execute()), der Ordner zeichnet nichts Eigenes.
        obj = doc.addObject("Part::FeaturePython", "SectionSketch")
        obj.Label = f"Schnitt-Sketch: {ref_obj.Label}"
        SectionSketchProxy(obj)
        obj.ReferencePlane = (ref_obj, [subname] if subname else [])
        # Initialzustand (Nutzerwunsch 2026-11-11): Koerper bleiben eingeblendet, Gesamtschnitt
        # ist ausgeblendet (siehe execute()). Ab dem ersten Umschalten des Ordners wechseln sich
        # Schnitt und Koerper ab (siehe ViewProviderSectionSketch.onChanged()).
        obj.HideBodies = False

        # FCPROJECT-FIX (2026-11-08, zurueckgerollt - siehe ausfuehrlicher Kommentar in
        # _get_or_create_part_sketch()): obj (und seine Kinder) bleiben MIT assembly.addObject()
        # - ein Versuch ohne fuehrte live zu einer GeoFeatureGroup-Scope-Warnung und vermutlich
        # zum gemeldeten Platzierungs-Versatz. Sichtbarkeit laesst sich stattdessen ueber die
        # "Sichtbarkeit"-Zeile im Eigenschaften-Fenster umschalten.
        if assembly is not None and hasattr(assembly, 'addObject'):
            assembly.addObject(obj)

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
                'Pixmap': IconUtils.icon_path(ICON_DIR, 'section_sketch.svg'),
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
