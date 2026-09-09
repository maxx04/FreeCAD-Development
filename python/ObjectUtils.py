# FCProject: gemeinsame Objekt-/Link-Hilfsfunktionen fuer mehrere Werkzeuge.
#
# Hintergrund (siehe [[feedback_fcproject_need_unified_search_utils]], Nutzer-Feedback
# 2026-09-07 "wir haben in FCProject schon 100 mal gleiches Problem gehabt. Endlich muss
# man in Utils einheitliche Suche machen."): Link-Ketten-Aufloesung und "gleich benannte
# Kopien eines Objekts finden" wurden bisher unabhaengig und leicht unterschiedlich in
# PatternFeatures.py, AssemblyPatternCreator.py, PartExchangeWindow.py und
# SectionSketchFeature.py nachgebaut - mit denselben Bugs in mehreren Varianten (siehe
# [[project_fcproject_freecadcmd_zero_joints_cold_load]]). Hier jetzt an EINER Stelle,
# bewusst ohne Abhaengigkeiten zu anderen FCProject-Modulen (nur FreeCAD-Kern-API), damit
# jedes Werkzeug es gefahrlos importieren kann.

import re

# FreeCADs eigenes Kollisions-Suffix beim Anlegen (doc.addObject() bei Namenskonflikt,
# z.B. "GWH_002_P_Latte" -> "GWH_002_P_Latte001") UND das Suffix von "Einfache Kopie
# erstellen" folgen demselben Muster: eine Ziffernfolge direkt am Namensende, ohne
# Trennzeichen. Bewusst NUR .Name (nie .Label, siehe
# [[feedback_fcproject_never_use_label_for_addressing]]).
_TRAILING_DIGITS_RE = re.compile(r"\d+$")


def base_name(name):
    """Liefert `name` ohne angehaengte Ziffern am Ende - z.B. "GWH_002_P_Latte001" ->
    "GWH_002_P_Latte". Objekte mit demselben Basis-Namen gelten als "Kopien-Familie"
    desselben urspruenglichen Objekts (per Nutzer-Bestaetigung 2026-09-09)."""
    return _TRAILING_DIGITS_RE.sub("", name)


def find_name_pattern_siblings(obj, objects):
    """Liefert alle Objekte aus `objects` (z.B. doc.Objects), deren interner Name denselben
    Basis-Namen wie `obj` hat (siehe base_name()) - `obj` selbst ist immer mit enthalten.
    Reihenfolge wie in `objects`, keine Duplikate.

    ACHTUNG (2026-09-09, per Live-Diagnose widerlegt): erfasst NUR das Ziffern-Suffix-Muster
    (FreeCADs eigenes Kollisions-Suffix / "Einfache Kopie erstellen"). Andere
    Kopier-Konventionen wie "_Copy_N" (siehe PatternFeatures.py/AssemblyPatternCreator.py)
    werden NICHT erfasst - live bestaetigt an "GWH_008_P_Latte" vs. "GWH_008_P_Latte_Copy_1/2/3"
    (zeigen auf dieselbe Quelldatei, aber komplett andere Namen). Fuer "ist das eine Kopie
    desselben Teils" IMMER find_same_source_siblings() benutzen (robuster, namensunabhaengig) -
    diese Funktion nur, wenn wirklich ausschliesslich auf den NAMEN selbst geprueft werden soll."""
    target_base = base_name(obj.Name)
    return [o for o in objects if base_name(o.Name) == target_base]


def resolve_linked_object(obj):
    """Loest `obj` rekursiv bis zum ECHTEN, finalen Ziel auf, falls es selbst (eine Kette
    von) App::Link(s) ist - duenner, dokumentierender Wrapper um FreeCADs eigene
    DocumentObject::getLinkedObject(recurse=True). Gibt `obj` unveraendert zurueck, falls
    es selbst kein Link ist. Immer DIESE Funktion (bzw. direkt getLinkedObject(True))
    benutzen statt eine eigene Link-Aufloesungs-Schleife nachzubauen - siehe
    [[feedback_fcproject_need_unified_search_utils]]."""
    return obj.getLinkedObject(True)


def _source_key(obj):
    """Identifiziert die AUFGELOESTE Quelle von `obj` eindeutig (Dokumentname + Name), fuer
    den Vergleich in find_same_source_siblings()."""
    source = resolve_linked_object(obj)
    doc = getattr(source, "Document", None)
    return (doc.Name, source.Name) if doc is not None else id(source)


def find_same_source_siblings(obj, objects):
    """Liefert alle Objekte aus `objects` (z.B. doc.Objects), die - nach Aufloesung etwaiger
    App::Link-Ketten (siehe resolve_linked_object()) - auf DIESELBE Quelle zeigen wie `obj`.
    `obj` selbst ist immer mit enthalten. Reihenfolge wie in `objects`.

    Robuster als find_name_pattern_siblings(): unabhaengig davon, WIE die Kopien benannt
    sind (Ziffern-Suffix, "_Copy_N", komplett frei gewaehltes Label) - live bestaetigt an
    "GWH_008_P_Latte" (Ziffern-Suffix-Kopien UND "_Copy_N"-Kopien zeigen beide auf dieselbe
    Quelldatei "GWH_008_P_Latte.FCStd", werden hier beide korrekt erfasst). Das ist die
    empfohlene Standardfunktion fuer "finde alle Vorkommen/Instanzen desselben Teils" -
    siehe [[feedback_fcproject_need_unified_search_utils]]."""
    target_key = _source_key(obj)
    return [o for o in objects if _source_key(o) == target_key]
