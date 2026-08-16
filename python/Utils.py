import FreeCAD as App
import FreeCADGui as Gui

def floatGerman(value, default=0.0):
    try:
        return float(str(value).replace(",", "."))
    except (ValueError, TypeError):
        return default

def add_local_coordinate_system(container, name="LCS"):
    """Fügt dem übergebenen Container (App::Part/PartDesign::Body/Assembly::AssemblyObject) ein
    ECHTES Part::LocalCoordinateSystem hinzu (Identity-Placement am lokalen Ursprung des
    Containers, keine eigene Positionierung nötig) - siehe resources/docs/CONSTRAINTS.md: jedes
    PDM-Objekt (P/A/R/G/B) soll ein echtes LCS besitzen. Der automatische App::Origin-Container ist
    zwar technisch selbst auch ein App::LocalCoordinateSystem (App::Origin erbt in FreeCAD davon,
    siehe App/Origin.h), zählt seit dem AssemblyPatternCreator-Fix aber bewusst NICHT mehr als
    Pattern-/Joint-Referenz (siehe [[project_fcproject_assembly_pattern_origin_lcs_bug]]) - ohne
    ein zusätzliches echtes LCS bekommt ein gepattertes Objekt sonst nur die Warnung "Keine
    LCS-Referenz gefunden".

    Part::LocalCoordinateSystem ist der Standard-Typ des Part-Werkbench-Befehls
    "Part_CoordinateSystem" (Part/Gui/Command.cpp) - erbt von App::LocalCoordinateSystem und ist
    laut PartDesign::Body::isAllowed() (Body.cpp) explizit auch in einen Body einfügbar, genau wie
    in App::Part/Assembly::AssemblyObject (beide über GeoFeatureGroupExtension generell offen für
    beliebige Kind-Objekte).

    Scheitert rein defensiv (nur Konsolen-Warnung) - ein LCS-Problem soll nie die eigentliche
    PDM-Erstellung blockieren."""
    if container is None:
        return None
    try:
        doc = container.Document
        lcs = doc.addObject("Part::LocalCoordinateSystem", f"{container.Name}_LCS")
        lcs.Label = name
        if hasattr(container, "addObject"):
            container.addObject(lcs)
        # Sichtbarkeit bewusst AUS (Standard von Part::LocalCoordinateSystem ist ohnehin
        # unsichtbar, siehe ViewProviderCoordinateSystem::ViewProviderCoordinateSystem() im
        # FreeCAD-Kern - hier trotzdem explizit gesetzt statt sich nur auf den Kern-Default zu
        # verlassen). Das LCS ist eine reine FCProject-interne Referenz für Pattern/Joints, kein
        # Konstruktionselement, das im 3D-Fenster stören soll - wer's braucht, blendet es im Baum
        # gezielt selbst ein.
        try:
            lcs.Visibility = False
        except Exception:
            pass
        return lcs
    except Exception as e:
        App.Console.PrintWarning(
            f"FCProject: Echtes LCS für '{getattr(container, 'Label', '?')}' konnte nicht angelegt werden: {str(e)}\n"
        )
        return None


def _ensure_property(App, obj, prop_type, name, group, desc, default=None):
        try:
            if not hasattr(obj, name):
                obj.addProperty(prop_type, name, group, desc)
            if default is not None:
                setattr(obj, name, default)
        except Exception as e:
            App.Console.PrintWarning(f"FCProject: Fehler beim Anlegen/Setzen Property '{name}': {e}\n")

def walk_ultimate_everything(root_object):

    """
    Durchläuft radikal ALLES, was strukturell unter dem root_object liegt.
    Verhindert Endlosschleifen und liefert (Objekt, Tiefe).
    Am Ende kommt (None, 0).
    """
    visited = set()

    def _traverse(obj, current_depth):
        # Falls wir das Objekt schon mal hatten (z.B. durch Mehrfachlinks), überspringen
        if obj in visited:
            return
        visited.add(obj)
        
        yield obj, current_depth
        
        children = []
        
        # 1. Standard-Gruppen (Assemblies, Parts, Bodies, etc.)
        if hasattr(obj, "Group") and obj.Group:
            for child in obj.Group:
                if child and child not in children:
                    children.append(child)
                    
        # 2. Features (wichtig für manche PartDesign-Strukturen)
        if hasattr(obj, "Features") and obj.Features:
            for child in obj.Features:
                if child and child not in children:
                    children.append(child)
        
        # 3. Das Origin-Koordinatensystem holen
        if hasattr(obj, "Origin") and obj.Origin:
            if obj.Origin not in children:
                children.append(obj.Origin)
                
        # 4. Links (App::Link) auflösen und in deren Inhalt abtauchen
        if hasattr(obj, "LinkedObject") and obj.LinkedObject:
            linked = obj.LinkedObject
            # Inhalt des Links analysieren
            if hasattr(linked, "Group") and linked.Group:
                for child in linked.Group:
                    if child and child not in children:
                        children.append(child)
            if hasattr(linked, "Origin") and linked.Origin:
                if linked.Origin not in children:
                    children.append(linked.Origin)

        # Rekursiver Aufruf für jedes gefundene Kind-Element
        for child in children:
            yield from _traverse(child, current_depth + 1)

    # Sicherheitscheck
    if root_object is None:
        yield None, 0
        return

    # Start der Traversierung
    yield from _traverse(root_object, 0)
    
    # Das finale Signal für das Ende der Struktur
    yield None, 0

def walk_assembly_iterative(root_object):
    """
    Durchläuft die FreeCAD-Struktur ITERATIV (ohne Rekursion).
    Löst das Problem mit Linked Assemblies, indem auch deren Origins/Features erfasst werden.
    Gibt (Objekt, Tiefe) zurück und am Ende (None, 0).
    """
    if root_object is None:
        yield None, 0
        return

    # Der Stack speichert TuDocs als (Objekt, Tiefe)
    # Wir starten mit dem Wurzelobjekt
    stack = [(root_object, 0)]
    visited = set()

    while stack:
        # Das oberste Element vom Stapel holen
        obj, depth = stack.pop()

        # Schutz vor Endlosschleifen (falls sich Objekte gegenseitig verlinken)
        if obj in visited:
            continue
        visited.add(obj)

        # 1. Aktuelles Objekt an die Schleife ausgeben
        yield obj, depth

        # 2. Kinder dieses Objekts sammeln
        children = []

        #--- A: Normale Objekteigenschaften auslesen ---
        if hasattr(obj, "Group") and obj.Group:
            for c in obj.Group:
                if c and c not in children: children.append(c)
                
        if hasattr(obj, "Features") and obj.Features:
            for c in obj.Features:
                if c and c not in children: children.append(c)
                
        if hasattr(obj, "Origin") and obj.Origin:
            if obj.Origin not in children: children.append(obj.Origin)

        #--- B: HIER WIRD DAS LINK-PROBLEM GELÖST ---
        # Wenn es ein Link ist, steigen wir in das verknüpfte Originalobjekt ein
        # und holen von DORT die echten Kinder, Origins und Features!
        if hasattr(obj, "LinkedObject") and obj.LinkedObject:
            target = obj.LinkedObject
            
            if hasattr(target, "Group") and target.Group:
                for c in target.Group:
                    if c and c not in children: children.append(c)
                    
            if hasattr(target, "Features") and target.Features:
                for c in target.Features:
                    if c and c not in children: children.append(c)
                    
            if hasattr(target, "Origin") and target.Origin:
                if target.Origin not in children: children.append(target.Origin)

        # 3. Kinder auf den Stack legen
        # WICHTIG: In umgekehrter Reihenfolge (reversed), damit das erste Kind 
        # beim nächsten Schleifendurchlauf auch als ERSTES oben vom Stack gepoppt wird.
        for child in reversed(children):
            stack.append((child, depth + 1))

    # Wenn der Stack komplett leer ist, sind wir am Ende angekommen
    yield None, 0

def walk_assembly_complete_instances(root_object):
    """
    Durchläuft die FreeCAD-Struktur iterativ. 
    Zeigt JEDE Instanz (Motoren, Patterns, Links) vollständig mit allen Kindern an.
    Schützt vor Endlosschleifen über eine Pfad-Verfolgung.
    """
    if root_object is None:
        yield None, 0
        return

    # Der Stack speichert jetzt: (Objekt, Tiefe, Pfad_als_Tupel)
    # Das Tupel 'path' speichert die Ahnenkette des aktuellen Zweigs
    stack = [(root_object, 0, ())]

    while stack:
        obj, depth, path = stack.pop()

        # ZYKLEN-SCHUTZ: Falls ein Objekt sich selbst als Kind hat (Loop im Pfad)
        if obj in path:
            continue
            
        # Aktualisiere den Pfad für die Kinder dieses Objekts
        current_path = path + (obj,)

        # 1. Aktuelles Objekt an die Schleife ausgeben
        yield obj, depth

        # 2. Kinder sammeln
        children = []

        # --- REIHENFOLGE-OPTIMIERUNG: Origin zuerst ---
        if hasattr(obj, "Origin") and obj.Origin:
            if obj.Origin not in children: children.append(obj.Origin)

        if hasattr(obj, "Group") and obj.Group:
            for c in obj.Group:
                if c and c not in children: children.append(c)
                
        if hasattr(obj, "Features") and obj.Features:
            for c in obj.Features:
                if c and c not in children: children.append(c)

        # --- LINK-AUFLÖSUNG: Holt die echten Innereien von Kopien/Links ---
        if hasattr(obj, "LinkedObject") and obj.LinkedObject:
            target = obj.LinkedObject
            
            # Auch beim verknüpften Objekt: Origin zuerst
            if hasattr(target, "Origin") and target.Origin:
                if target.Origin not in children: children.append(target.Origin)
                
            if hasattr(target, "Group") and target.Group:
                for c in target.Group:
                    if c and c not in children: children.append(c)
                    
            if hasattr(target, "Features") and target.Features:
                for c in target.Features:
                    if c and c not in children: children.append(c)

        # 3. Kinder rückwärts auf den Stack legen (LIFO-Prinzip für korrekte Baum-Ansicht)
        for child in reversed(children):
            stack.append((child, depth + 1, current_path))

    # Ende-Signal
    yield None, 0

def get_clean_children(source_obj):
    """Sammelt Kinder ohne visuelle Duplikate aus Unterordnern."""
    items = []
    if hasattr(source_obj, "Origin") and source_obj.Origin:
        items.append(source_obj.Origin)
    
    raw_group = list(source_obj.Group) if hasattr(source_obj, "Group") and source_obj.Group else []
    raw_features = list(source_obj.Features) if hasattr(source_obj, "Features") and source_obj.Features else []
    
    # Filter für Elemente, die in Unterordnern (Patterns, Joints) stecken
    hidden_in_subfolders = set()
    for c in raw_group:
        if c and c.TypeId in ["App::DocumentObjectGroup", "Assembly::JointGroup"]:
            if hasattr(c, "Group") and c.Group:
                for sub_c in c.Group:
                    if sub_c: hidden_in_subfolders.add(sub_c)
    
    for c in raw_group:
        if c and c not in hidden_in_subfolders and c not in items:
            items.append(c)
            
    for c in raw_features:
        if c and c not in items:
            items.append(c)
            
    return items

def get_artikel_id(Element):
    """
    Folgt einer Kette von Links (unendlich tief), bis die ArtikelID 
    gefunden wird oder das Ende der Verknüpfungen erreicht ist.
    """
    # 1. Sicherheitscheck: Wenn das Element selbst die ID hat
    if hasattr(Element, "ArticleID") and Element.ArticleID:
        return str(Element.ArticleID)
        
    # 2. Die Link-Kette (Link-on-Link) komplett auflösen
    current = Element
    while hasattr(current, "LinkedObject") and current.LinkedObject:
        # Wir springen eine Ebene tiefer im Link-Netzwerk
        current = current.LinkedObject
        
        # Prüfen, ob das getroffene Zielobjekt die ID besitzt
        if hasattr(current, "ArticleID") and current.ArticleID:
            return str(current.ArticleID)
            
    # Falls es eine Gruppe (App::DocumentObjectGroup) oder ohne ID ist
    return "None"
            
def print_perfect_assembly_tree(root_object):
    """Iteriert durch die Baugruppe und gibt einen wunderschönen Unicode-Baum aus."""
    if root_object is None:
        print("Kein Objekt übergeben.")
        return

    print(f"\n⚡ --- START DER PERFEKTEN BAUGRUPPEN-ANALYSE ---")
    
    # Der Stack speichert: (Objekt, Tiefe, Pfad-Historie, Liste_von_IsLast_Flags)
    # Das 'flags'-Array merken wir uns, um die Linien (│, ├──, └──) perfekt zu zeichnen.
    stack = [(root_object, 0, (), [])]
    visited_paths = set()

    while stack:
        obj, depth, path, flags = stack.pop()

        # Zyklen-Schutz
        if obj in path:
            continue
        current_path = path + (obj,)

        # --- ARTIKEL ID UND TEXT ERSTELLEN ---
        artikel_id = get_dynamic_author_id = get_artikel_id(obj)
        info_str = f"{obj.Label} [ID: {artikel_id}] ({obj.TypeId})"

        # --- GRAPHISCHE BAUM-LINIEN GENERIEREN ---
        prefix = ""
        for is_last in flags[:-1]:
            prefix += "    " if is_last else "│   "
        if flags:
            prefix += "└── " if flags[-1] else "├── "
            
        # Ausgabe in die Konsole
        print(f"{prefix}{info_str}")

        # --- KINDER VERARBEITEN ---
        children = get_clean_children(obj)
        if hasattr(obj, "LinkedObject") and obj.LinkedObject:
            for child in get_clean_children(obj.LinkedObject):
                if child not in children:
                    children.append(child)

        # Kinder rückwärts auf den Stack legen (wegen LIFO)
        # i == 0 entspricht in der 'reversed'-Schleife dem echten LETZTEN Element
        for i, child in enumerate(reversed(children)):
            child_is_last = (i == 0)
            next_flags = flags + [child_is_last]
            stack.append((child, depth + 1, current_path, next_flags))

    print("🏁 --- ANALYSE ERFOLGREICH BEENDET ---")

def get_assembly_tree(root_object) -> list:
    """Gibt eine Liste aller Elemente in der Baugruppe zurück, inklusive Tiefe und ArtikelID."""
    """Iteriert durch die Baugruppe und drückt einen Baum aus."""

    assambly_tree = []

    if root_object is None:
        print("Kein Objekt übergeben.")
        return assambly_tree

    print(f"\n⚡ --- START DER PERFEKTEN BAUGRUPPEN-ANALYSE ---")
    
    # Der Stack speichert: (Objekt, Tiefe, Pfad-Historie, Liste_von_IsLast_Flags, Struktur-Index)

    stack = [(root_object, 0, (), [], (1,))]
    visited_paths = set()

    while stack:
        obj, depth, path, flags, index_path = stack.pop()

        # Zyklen-Schutz
        if obj in path:
            continue
        current_path = path + (obj,)

        # --- ARTIKEL ID UND TEXT ERSTELLEN ---
        artikel_id = get_dynamic_author_id = get_artikel_id(obj)
        info_str = f"{obj.Label} [ID: {artikel_id}] ({obj.TypeId})"
        # Hier wird die Baumstruktur in eine Liste gepackt, anstatt sie zu drucken
        assambly_tree.append((obj, depth, artikel_id, index_path))

        # --- GRAPHISCHE BAUM-LINIEN GENERIEREN ---
        prefix = ""
        for is_last in flags[:-1]:
            prefix += "    " if is_last else "│   "
        if flags:
            prefix += "└── " if flags[-1] else "├── "
            
        # Ausgabe in die Konsole
        print(f"{prefix}{info_str}")

        # --- KINDER VERARBEITEN ---
        children = get_clean_children(obj)
        if hasattr(obj, "LinkedObject") and obj.LinkedObject:
            for child in get_clean_children(obj.LinkedObject):
                if child not in children:
                    children.append(child)

        # Kinder rückwärts auf den Stack legen (wegen LIFO)
        # i == 0 entspricht in der 'reversed'-Schleife dem echten LETZTEN Element
        for i, child in enumerate(reversed(children)):
            child_is_last = (i == 0)
            next_flags = flags + [child_is_last]
            child_index_path = index_path + (len(children) - i,)
            stack.append((child, depth + 1, current_path, next_flags, child_index_path))

    print("🏁 --- ANALYSE ERFOLGREICH BEENDET ---")
    return assambly_tree

def _resolve_pdm_value(obj, prop_name):
    """Sucht eine PDM-Eigenschaft. Löst Links sofort auf, um die echten C++ .Value-Daten zu holen."""
    if not obj:
        return None

    pdm_target = obj    
    # Wenn das Objekt ein Link ist, springen wir SOFORT zum echten Ursprungs-Bauteil!
    if hasattr(obj, "LinkedObject") and obj.LinkedObject:
        pdm_target = obj.LinkedObject

    # Jetzt lesen wir die Eigenschaft direkt und sauber vom echten Bauteilkern aus
    if hasattr(pdm_target, prop_name) and getattr(pdm_target, prop_name):
        prop_obj = getattr(pdm_target, prop_name)
        if hasattr(prop_obj, "Value"):
            val = str(prop_obj.Value).strip()
        else:
            val = str(prop_obj).strip()
            
        if val and val != "-":
            return val
    
    # Fallback-Suche in inneren Gruppen, falls es ein verschachtelter Container ist
    if hasattr(pdm_target, "Group"):
        for child in pdm_target.Group:
            if not hasattr(child, "ArticleID"): # Schnellentlastung für irrelevante Kinder
                continue
            inner_child = child.LinkedObject if hasattr(child, "LinkedObject") and child.LinkedObject else child
            if hasattr(inner_child, prop_name) and getattr(inner_child, prop_name):
                prop_obj = getattr(inner_child, prop_name)
                val = str(prop_obj.Value).strip() if hasattr(prop_obj, "Value") else str(prop_obj).strip()

                if val and val != "-":
                    return val
    return None      

def _extract_pdm_data(obj):
    """Sammelt Metadaten aus den aufgelösten Kern-Properties."""
    
    article_id = _resolve_pdm_value(obj, "ArticleID")
    
    # Fallback über den echten C++ Namen des Ursprungsbauteils (z.B. Part001)
    # if not article_id:
    #     pdm_obj = obj.LinkedObject if hasattr(obj, "LinkedObject") and obj.LinkedObject else obj
    #     article_id = pdm_obj.Name

    # Bezeichnung auflösen
    bezeichnung = _resolve_pdm_value(obj, "Bezeichnung")
    if not bezeichnung:
        profil_typ = _resolve_pdm_value(obj, "ProfilTyp")
        if profil_typ:
            bezeichnung = profil_typ
        # else:
        #     pdm_obj = obj.LinkedObject if hasattr(obj, "LinkedObject") and obj.LinkedObject else obj
        #     bezeichnung = pdm_obj.Label.split('_')[-1].rstrip('_') if '_' in pdm_obj.Label else pdm_obj.Label

    # Werkstoff auflösen
    material = _resolve_pdm_value(obj, "MaterialName")
    if not material:
        pdm_obj = obj.LinkedObject if hasattr(obj, "LinkedObject") and obj.LinkedObject else obj
        if hasattr(pdm_obj, "ShapeMaterial") and pdm_obj.ShapeMaterial:
            material = getattr(pdm_obj.ShapeMaterial, "Name", "-")
        else:
            material = _resolve_pdm_value(obj, "ShapeMaterial")
            if not material: material = "-"

    # Preis auflösen
    preis = _resolve_pdm_value(obj, "Preis")
    if preis is None or preis == "":
        preis = 0.0
    else:
        try:
            preis = float(str(preis).replace(',', '.'))
        except Exception:
            preis = 0.0

    # Rohling-Verknüpfung auflösen
    rohteil = "-"
    
    # KORREKTUR: Wenn das aktuelle Hauptobjekt KEINE Baugruppe ist, lesen wir das Rohteil aus
    pdm_obj = obj.LinkedObject if hasattr(obj, "LinkedObject") and obj.LinkedObject else obj
    if not pdm_obj.isDerivedFrom("Assembly::AssemblyObject"):
        if hasattr(pdm_obj, "BasiertAufHalbzeug") and pdm_obj.BasiertAufHalbzeug:
            rohteil = str(pdm_obj.BasiertAufHalbzeug)
    else:
        # Baugruppen besitzen per Definition niemals einen Rohling-Zuschnitt
        rohteil = "-"

    return {
        "ArticleID": article_id,
        "Bezeichnung": bezeichnung,
        "Material": material,
        "Rohling": rohteil,
        "Preis": preis
    }

def _scan_recursive(self, current_obj, current_index, bom_list, visited_objects):
    """Rekursiver Scan, der strikt über LinkedObject die echten Bauteilkerne durchläuft und dabei Zyklen vermeidet."""

    if current_obj in visited_objects:
        return
    visited_objects.add(current_obj)

    scan_target = current_obj.LinkedObject if hasattr(current_obj, "LinkedObject") and current_obj.LinkedObject else current_obj
    children = getattr(scan_target, "Group", [])

    valid_children = []
    for child in children:

        # if child.Label.startswith("BOM-Ref:") or "Bill_of_Materials" in child.Label or "Bills_of_Materials" in child.Name:
        #     continue
        # if child.isDerivedFrom("App::Origin") or "Origin" in child.Name or "Joints" in child.Name:
        #     continue
            
        has_id = _resolve_pdm_value(child, "ArticleID")
        if has_id:
            valid_children.append(child)

    for sub_idx, child in enumerate(valid_children, start=1):
        new_index = f"{sub_idx}" if current_index == "" else f"{current_index}-{sub_idx}"

        pdm_info = _extract_pdm_data(child)
        
        bom_list.append([
            new_index,
            pdm_info["ArticleID"],
            pdm_info["Bezeichnung"],
            pdm_info["Material"],
            pdm_info["Rohling"],
            "1"
        ])

        target_child = child.LinkedObject if hasattr(child, "LinkedObject") and child.LinkedObject else child
        if hasattr(target_child, "Group") and target_child.Group:
            _scan_recursive(child, new_index, bom_list, visited_objects)

# # --- STARTER ---
# auswahl = Gui.Selection.getSelection()
# if not auswahl:
#     print("!! Bitte markiere zuerst die Hauptbaugruppe im Modellbaum !!")
# else:
#     print_perfect_assembly_tree(auswahl[0])    