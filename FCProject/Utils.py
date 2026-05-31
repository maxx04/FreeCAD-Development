import FreeCAD as App
import FreeCADGui as Gui

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


def get_artikel_id(element):
    """
    Folgt einer Kette von Links (unendlich tief), bis die ArtikelID 
    gefunden wird oder das Ende der Verknüpfungen erreicht ist.
    """
    # 1. Sicherheitscheck: Wenn das Element selbst die ID hat
    if hasattr(element, "ArticleID") and element.ArticleID:
        return str(element.ArticleID)
        
    # 2. Die Link-Kette (Link-on-Link) komplett auflösen
    current = element
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

# --- STARTER ---
auswahl = Gui.Selection.getSelection()
if not auswahl:
    print("!! Bitte markiere zuerst die Hauptbaugruppe im Modellbaum !!")
else:
    print_perfect_assembly_tree(auswahl[0])    