#FCProject: AssemblyPatternCreator - Kern-Logik für Pattern via Joints
import FreeCAD as App
from FreeCAD import Vector, Placement, Rotation
import copy

class AssemblyPatternCreator:
    """Erstellt Array-Pattern von Elementen in einer Assembly über Joints."""
    
    def __init__(self, doc, assembly):
        self.doc: App.Document = doc
        self.assembly: App.DocumentObject = assembly
        self.pattern_group: App.DocumentObjectGroup = None
        self._validate_assembly()

    def create_pattern(self, source_element, count=3, distance=600.0, direction="X-Achse"):
        """
        Erstellt ein Array-Pattern eines Elements über Joints.
        
        Args:
            source_element: Das zu kopierende Element
            count: Anzahl der Kopien
            distance: Abstand zwischen den Elementen (mm)
            direction: Richtungsvektor ("X-Achse", "Y-Achse", "Z-Achse" des LCS kopierten Objektes)
        """
        
        # 1. Validierungen für kopierbares Element
        self._validate_source_element(source_element)
        
        # 2. Erstelle eine Pattern-Gruppe für Übersicht
        self._create_patterngroup(source_element)
        
        # 3. Kopiere das Original-Element count mal und positioniere es
        copied_elements = self._copy_and_place_element(source_element, count, distance, direction)
        
        # 4. Erstelle Joints zwischen den Elementen (wenn Joints-Workbench verfügbar)
        # Erste Joint wird zwischen original und erstem Kopie erstellt, dann zwischen den Kopien
        try:
            self._create_joints_between_elements(source_element, copied_elements, direction)
        except Exception as e:
            App.Console.PrintWarning(f"FCProject: Joints konnten nicht erstellt werden: {str(e)}\n")

        # 5. Recompute
        self.doc.recompute()
        
        App.Console.PrintMessage(f"FCProject: Pattern '{self.pattern_group.Label}' mit {count} Elementen erfolgreich erstellt!\n")

    def _copy_and_place_element(self, source_element, count, distance, direction):
        copied_elements = []
        for i in range(1, count+1):
            try:
                # Berechne neue Position
                #TODO Da kann man verschiedene Varianten von Berechnung einbauen, z.B. auch mit Rotation oder entlang von LCS-Achsen
                offset_vector = self._calculate_offset_vector(distance, direction, i)
                
                # Kopiere das Element
                new_element = self._duplicate_element(source_element, f"{source_element.Label}_Copy_{i}")
                
                if not new_element:
                    App.Console.PrintWarning(f"FCProject: Element {i+1} konnte nicht erstellt werden (None returned).\n")
                    continue
                
                # Positioniere das neue Element (falls möglich)
                try:
                    if hasattr(new_element, 'Placement'):
                        current_placement = new_element.Placement
                        new_placement = Placement(
                            Vector(
                                current_placement.Base.x + offset_vector.x,
                                current_placement.Base.y + offset_vector.y,
                                current_placement.Base.z + offset_vector.z
                            ),
                            current_placement.Rotation
                        )
                        new_element.Placement = new_placement
                        App.Console.PrintMessage(f"FCProject: Element {i+1}/{count} positioniert.\n")
                    else:
                        App.Console.PrintWarning(f"FCProject: Element {i+1} hat keine Placement-Property.\n")
                except Exception as pos_err:
                    App.Console.PrintWarning(f"FCProject: Fehler beim Positionieren von Element {i+1}: {str(pos_err)}\n")
                
                # Füge zur Pattern-Gruppe hinzu
                self.pattern_group.addObject(new_element)
                # Versuche, das neue Element auch in der Assembly einzuhängen (falls möglich)
                try:
                    if hasattr(self.assembly, 'addObject'):
                        self.assembly.addObject(new_element)
                except Exception:
                    # Nicht kritisch, nur loggen
                    App.Console.PrintWarning(f"FCProject: Konnte {new_element.Label} nicht zur Assembly hinzufügen (nicht kritisch).\n")

                copied_elements.append(new_element)
                
            except Exception as e:
                App.Console.PrintError(f"FCProject: Fehler bei Element {i}/{count}: {str(e)}\n")
                import traceback
                App.Console.PrintError(traceback.format_exc())
                # Fahre mit nächstem Element fort
                continue
            
        
        if not copied_elements:
            raise RuntimeError("Keine Elemente konnten kopiert werden!")
        
        App.Console.PrintMessage(f"FCProject: {len(copied_elements)} Elemente erfolgreich erstellt.\n")
        return copied_elements

    def _calculate_offset_vector(self, distance, direction, i):
        direction_vector = self._get_direction_vector(direction)
        offset_vector = direction_vector * (distance * i)
        return offset_vector

    def _create_patterngroup(self, source_element):
        try:
            self.pattern_group = self.doc.addObject("App::DocumentObjectGroup", f"Pattern_{source_element.Label}")
            self.pattern_group.Label = f"Pattern: {source_element.Label}"
            self.assembly.addObject(self.pattern_group)
        except Exception as e:
            App.Console.PrintError(f"FCProject: Fehler beim Erstellen der Pattern-Gruppe: {str(e)}\n")
            raise

    def _validate_source_element(self, element):
        """Validiert das Quell-Element für die Pattern-Erstellung."""

        if element is None:
            raise ValueError("Quell-Element ist None!")
        
        # Überprüfe, ob das Element ein gültiger Typ ist (Part, Body, Assembly, Link, oder hat Shape)
        is_valid = False
        if hasattr(element, 'Shape') and element.Shape is not None:
            is_valid = True  # Hat Shape
        elif element.isDerivedFrom('Assembly::AssemblyObject'):
            is_valid = True  # Assembly
        elif element.isDerivedFrom('App::Part'):
            is_valid = True  # Part
        elif element.isDerivedFrom('PartDesign::Body'):
            is_valid = True  # Body
        elif element.isDerivedFrom('App::Link'):
            is_valid = True  # Link
        
        if not is_valid:
            raise ValueError(f"Quell-Element '{element.Label}' (Typ: {element.TypeId}) ist nicht gültig! \
                             Unterstützt: Part, Body, Assembly, Link, oder Elemente mit Shape.")
        
        App.Console.PrintMessage(f"FCProject: Quell-Element '{element.Label}' validiert.\n")

    def _validate_assembly(self):
        """Validiert dass die Assembly FreeCAD 1.1 kompatibel ist."""

        if not self.assembly:
            raise ValueError("Assembly-Objekt ist None!")
        
        if self.assembly.TypeId != "Assembly::AssemblyObject":
            raise ValueError(f"Objekt ist keine Assembly, sondern: {self.assembly.TypeId}")
        
        App.Console.PrintMessage(f"FCProject: Assembly '{self.assembly.Label}' validiert.\n")

    def _get_direction_vector(self, direction):
        """Konvertiert Richtungsstring in Vector."""
        direction_map = {
            "X-Achse": Vector(1, 0, 0),
            "Y-Achse": Vector(0, 1, 0),
            "Z-Achse": Vector(0, 0, 1),
        }
        return direction_map.get(direction, Vector(1, 0, 0))

    def _normalize_direction(self, direction):
        """Normalisiert kurze Formen ('X','Y','Z') auf die erwarteten Strings.

        Akzeptiert bereits gültige Strings unverändert.
        """
        if direction is None:
            return 'X-Achse'
        if isinstance(direction, str):
            s = direction.strip()
            mapping = {
                'X': 'X-Achse', 'Y': 'Y-Achse', 'Z': 'Z-Achse',
                'X-Achse': 'X-Achse', 'Y-Achse': 'Y-Achse', 'Z-Achse': 'Z-Achse',
                'x': 'X-Achse', 'y': 'Y-Achse', 'z': 'Z-Achse'
            }
            return mapping.get(s, s)
        return 'X-Achse'

    def _safe_getattr(self, obj, name, default=None):
        try:
            return getattr(obj, name, default)
        except Exception:
            return default

    def _has_shape(self, obj):
        shape = self._safe_getattr(obj, 'Shape', None)
        return shape is not None

    def _duplicate_element(self, source_element, new_label):
        """Dupliziert ein Element in der Assembly."""
        App.Console.PrintMessage(f"FCProject: Dupliziere Element '{source_element.Label}' (TypeId: {source_element.TypeId}).\n")
        
        try:
            new_obj = None
            
            # 1. Versuche doc.copyObject (funktioniert für die meisten Typen)
            if hasattr(self.doc, 'copyObject'):
                try:
                    App.Console.PrintMessage(f"FCProject: Versuche doc.copyObject für '{source_element.Label}'.\n")
                    new_obj = self.doc.copyObject(source_element, False)
                    if new_obj is not None:
                        new_obj.Label = new_label
                        App.Console.PrintMessage(f"FCProject: copyObject erfolgreich.\n")
                        # Versuche zusätzliche Eigenschaften zu kopieren
                        try:
                            if hasattr(source_element, 'Placement') and hasattr(new_obj, 'Placement'):
                                new_obj.Placement = source_element.Placement
                        except Exception:
                            pass
                        return new_obj
                    
                except Exception as copy_err:
                    App.Console.PrintWarning(f"FCProject: doc.copyObject fehlgeschlagen: {str(copy_err)}\n")

            # 2. Fallback: Shape-Kopie (für Part/Body)
            shape = self._safe_getattr(source_element, 'Shape', None)

            if shape is not None:
                App.Console.PrintMessage(f"FCProject: Kopiere Shape-Objekt.\n")
                new_obj = self.doc.addObject(source_element.TypeId, f"obj_{new_label}")
                new_obj.Shape = shape
                new_obj.Label = new_label

                # Versuche, Placement-Eigenschaft zu übernehmen
                try:
                    if hasattr(source_element, 'Placement') and hasattr(new_obj, 'Placement'):
                        new_obj.Placement = source_element.Placement
                except Exception:
                    pass

                if hasattr(source_element, 'Material'):
                    try:
                        new_obj.Material = source_element.Material
                    except Exception:
                        pass

                if hasattr(source_element, 'ViewObject') and source_element.ViewObject:
                    if hasattr(source_element.ViewObject, 'ShapeColor'):
                        new_obj.ViewObject.ShapeColor = source_element.ViewObject.ShapeColor
                    if hasattr(source_element.ViewObject, 'Transparency'):
                        new_obj.ViewObject.Transparency = source_element.ViewObject.Transparency

                return new_obj

            # 3. Link-Fallback
            linked = self._safe_getattr(source_element, 'LinkedObject', None)
            if linked is not None:
                App.Console.PrintMessage(f"FCProject: Erstelle Link-Kopie eines referenzierten Objekts.\n")
                try:
                    new_obj = self.doc.addObject("App::Link", f"link_{new_label}")
                    new_obj.LinkedObject = source_element
                    new_obj.Label = new_label
                    return new_obj
                except Exception as link_err:
                    App.Console.PrintWarning(f"FCProject: Link-Erstellung fehlgeschlagen: {str(link_err)}\n")

            App.Console.PrintMessage(f"FCProject: Erstelle Link-Fallback für '{source_element.Label}'.\n")
            try:
                new_obj = self.doc.addObject("App::Link", f"link_{new_label}")
                new_obj.LinkedObject = source_element
                new_obj.Label = new_label
                return new_obj
            except Exception as fallback_err:
                App.Console.PrintWarning(f"FCProject: Link-Fallback fehlgeschlagen: {str(fallback_err)}\n")

            try:
                new_obj = self.doc.addObject("App::DocumentObjectGroup", f"obj_{new_label}")
                new_obj.Label = new_label
                return new_obj
            except Exception as group_err:
                App.Console.PrintError(f"FCProject: Ultimativer Fallback fehlgeschlagen: {str(group_err)}\n")
                raise

        except Exception as e:
            App.Console.PrintError(f"FCProject: Fehler beim Duplizieren von '{source_element.Label}': {str(e)}\n")
            import traceback
            App.Console.PrintError(traceback.format_exc())
            raise ValueError(f"Element '{source_element.Label}' konnte nicht dupliziert werden: {str(e)}")

    def _create_joints_between_elements(self, source_element, elements, direction):
        """
        Erstellt Joints zwischen den Elementen für Assembly-Verbindungen.
        Erste Joint wird zwischen original und erstem Kopie erstellt, dann zwischen den Kopien
        Benötigt eine kompatible Assembly Workbench (FreeCAD 1.1+).
        """
        JointObject, UtilsAssembly = self._import_assembly_api()
        if not JointObject or not UtilsAssembly:
            App.Console.PrintWarning("FCProject: Assembly Workbench API nicht verfügbar - Joints können nicht erstellt werden.\n")
            return

        if len(elements) < 1:
            return

        joint_group = UtilsAssembly.getJointGroup(self.assembly)
        if joint_group is None:
            App.Console.PrintWarning("FCProject: Konnte keine Joint-Gruppe in der Assembly finden.\n")
            return

        preferred_sub_name = self._get_basis_reference_name(source_element, UtilsAssembly, direction)

        # einfüge source_element am Anfang der Liste, damit zuerst ein Joint zwischen Original und erstem Element erstellt wird
        elements.insert(0, source_element)

        for i in range(len(elements) - 1):
            elem1 = elements[i]
            elem2 = elements[i + 1]

            try:
                ref1 = self._build_joint_reference(elem1, UtilsAssembly, preferred_sub_name)
                ref2 = self._build_joint_reference(elem2, UtilsAssembly, preferred_sub_name)

                if not ref1 or not ref2:
                    App.Console.PrintWarning(
                        f"FCProject: Keine geeigneten Referenzgeometrien für Joint zwischen {elem1.Label} und {elem2.Label} gefunden.\n"
                    )
                    continue

                joint = joint_group.newObject("App::FeaturePython", f"PatternJoint_{i+1}")
                joint.Label = f"PatternJoint_{i+1}"
                JointObject.Joint(joint, 0)
                if hasattr(JointObject, "ViewProviderJoint"):
                    JointObject.ViewProviderJoint(joint.ViewObject)

                offset2 = self._compute_fixed_joint_offset(elem1, elem2, ref1, ref2, UtilsAssembly, direction)
                if offset2 is not None:
                    joint.Offset2 = offset2

                joint.Proxy.setJointConnectors(joint, [ref1, ref2])
                App.Console.PrintMessage(f"FCProject: Joint zwischen {elem1.Label} und {elem2.Label} erstellt.\n")
            except Exception as e:
                App.Console.PrintWarning(f"FCProject: Joint-Erstellung fehlgeschlagen: {str(e)}\n")

    def _try_create_joint(self, solver_module, elem1, elem2, axis):
        """Versucht mehrere bekannte Assembly-API-Aufrufe für die Joint-Erstellung."""
        candidates = [
            'addJoint',
            'createJoint',
            'addConstraint',
            'createConstraint',
            'addRigid',
            'createRigid',
            'addLink',
        ]
        for name in candidates:
            if hasattr(solver_module, name):
                try:
                    func = getattr(solver_module, name)
                    result = func(elem1, elem2, axis)
                    return result is not None
                except Exception as e:
                    App.Console.PrintWarning(f"FCProject: Assembly-Funktion {name} fehlgeschlagen: {str(e)}\n")

        # Fallback: prüfe, ob solver_module selbst ein Joint-Objekt erzeugen kann
        if hasattr(solver_module, 'Joint'):
            try:
                joint = solver_module.Joint(elem1, elem2, axis)
                return joint is not None
            except Exception as e:
                App.Console.PrintWarning(f"FCProject: Assembly-Joint Konstruktor fehlgeschlagen: {str(e)}\n")

        return False

    def _import_assembly_api(self):
        import importlib
        import os
        import sys

        candidates = [
            "Assembly",
            "assembly",
            "A2",
            "A2.assembly",
            "FreeCADAssembly",
            "FreeCADAssembly.assembly",
            "freecad.assembly",
        ]

        for package_name in candidates:
            try:
                module = importlib.import_module(package_name)
                JointObject = getattr(module, 'JointObject', None)
                UtilsAssembly = getattr(module, 'UtilsAssembly', None)
                if JointObject and UtilsAssembly:
                    return JointObject, UtilsAssembly
            except Exception:
                continue

        try:
            JointObject = importlib.import_module('JointObject')
            UtilsAssembly = importlib.import_module('UtilsAssembly')
            if JointObject and UtilsAssembly:
                return JointObject, UtilsAssembly
        except Exception:
            pass

        potential_dirs = []
        for path in sys.path:
            if not path:
                continue
            if os.path.isfile(os.path.join(path, 'JointObject.py')) and os.path.isfile(os.path.join(path, 'UtilsAssembly.py')):
                potential_dirs.append(path)

        if hasattr(App, 'getResourcePath'):
            resource_dir = os.path.join(App.getResourcePath(), 'Mod', 'Assembly')
            if os.path.isdir(resource_dir) and resource_dir not in potential_dirs:
                potential_dirs.append(resource_dir)

        for path in potential_dirs:
            if path not in sys.path:
                sys.path.insert(0, path)
            try:
                JointObject = importlib.import_module('JointObject')
                UtilsAssembly = importlib.import_module('UtilsAssembly')
                if JointObject and UtilsAssembly:
                    return JointObject, UtilsAssembly
            except Exception:
                continue

        return None, None

    def _get_basis_reference_name(self, source_element, UtilsAssembly=None, direction=None):
        """Bestimmt die bevorzugte Basisreferenz (nur LCS) vom ausgewählten Quellteil."""
        if source_element is None:
            return None

        linked = self._safe_getattr(source_element, 'LinkedObject', None)
        root = linked if linked is not None else source_element

        names = self._get_coordinate_system_names(root)
        if not names:
            return None

        chosen = self._select_lcs_name(names, direction)
        App.Console.PrintMessage(f"FCProject: Gewählte LCS-Referenz für Richtung {direction}: {chosen}\n")
        return chosen

    def _get_sub_name_for_child(self, child, root):
        """Ermittelt den Subnamen eines verschachtelten Objekts relativ zur Wurzel."""
        if child is None or root is None:
            return None

        if child == root:
            return None

        if hasattr(child, 'Parents'):
            for sel in child.Parents:
                if not sel or len(sel) < 2:
                    continue
                parent_obj, path = sel[0], sel[1]
                if parent_obj == root or parent_obj.Name == root.Name:
                    if path.endswith('.'):
                        return f"{path}{child.Name}"
                    return f"{path}.{child.Name}"

        return child.Name

    def _get_coordinate_system_names(self, element):
        """Gibt alle LCS-/Datum-Referenznamen im Element zurück."""
        if element is None:
            return []

        candidates = []
        if hasattr(element, 'OutListRecursive'):
            candidates = list(element.OutListRecursive)
        elif hasattr(element, 'OutList'):
            candidates = list(element.OutList)

        names = []
        for child in candidates:
            if child is None:
                continue
            if getattr(child, 'TypeId', '') == 'App::LocalCoordinateSystem' or child.isDerivedFrom('App::LocalCoordinateSystem'):
                sub_name = self._get_sub_name_for_child(child, element)
                if sub_name:
                    names.append(sub_name)
            elif child.isDerivedFrom('App::DatumElement'):
                sub_name = self._get_sub_name_for_child(child, element)
                if sub_name:
                    names.append(sub_name)

        return names

    def _select_lcs_name(self, names, direction=None):
        """Wählt eine LCS-Referenz entsprechend der Pattern-Richtung aus."""
        if not names:
            return None

        direction_map = {
            'X-Achse': ['.Origin', '.YZ_Plane'],
            'Y-Achse': ['.Origin', '.XZ_Plane'],
            'Z-Achse': ['.Origin', '.XY_Plane'],
        }
        priorities = direction_map.get(direction, ['.Origin', '.X_Axis.', '.Y_Axis.', '.Z_Axis.'])

        for token in priorities:
            for name in names:
                if token in name or name.endswith(token.strip('.')):
                    return name

        return names[0]

    def _find_coordinate_system_name(self, element):
        """Sucht eine lokale Koordinatensystem-Referenz im Objekt."""
        if element is None:
            return None

        candidates = []
        if hasattr(element, 'OutListRecursive'):
            candidates = list(element.OutListRecursive)
        elif hasattr(element, 'OutList'):
            candidates = list(element.OutList)

        for child in candidates:
            if child is None:
                continue

            if getattr(child, 'TypeId', '') == 'App::LocalCoordinateSystem' or child.isDerivedFrom('App::LocalCoordinateSystem'):
                return self._get_sub_name_for_child(child, element)

            if child.isDerivedFrom('App::DatumElement'):
                parent = None
                try:
                    parent = child.getParent()
                except Exception:
                    parent = None
                if parent is not None and parent.isDerivedFrom('App::LocalCoordinateSystem'):
                    return self._get_sub_name_for_child(child, element)
                return self._get_sub_name_for_child(child, element)

        return None

    def _build_joint_reference(self, element, UtilsAssembly=None, preferred_sub_name=None):
        """Erstellt eine gültige Assembly-Referenz für das gegebene Element."""
        if element is None:
            return None

        linked = self._safe_getattr(element, 'LinkedObject', None)
        root = linked if linked is not None else element

            #HACK Verstehe nicht wie es funktioniert
        if preferred_sub_name:
            ref = [element, [preferred_sub_name, ""]]
            if UtilsAssembly and hasattr(UtilsAssembly, 'addTipNameToSub'):
                tip_sub = UtilsAssembly.addTipNameToSub(ref)
                if tip_sub:
                    ref = [element, [tip_sub, ""]]
            try:
                plc = UtilsAssembly.findPlacement(ref, False) if UtilsAssembly else None
                if plc is not None:
                    App.Console.PrintMessage(f"FCProject: LCS-Referenz für {element.Label}: {ref}\n")
                    return ref
            except Exception as e:
                App.Console.PrintWarning(
                    f"FCProject: Bevorzugte LCS-Referenz '{preferred_sub_name}' für {element.Label} ist ungültig: {str(e)}\n"
                )

            # Fallback: versuche dieselbe Sub-Referenz aber am Root-Objekt
            try:
                root_ref = [root, [preferred_sub_name, ""]]
                if UtilsAssembly and hasattr(UtilsAssembly, 'addTipNameToSub'):
                    tip_sub = UtilsAssembly.addTipNameToSub(root_ref)
                    if tip_sub:
                        root_ref = [root, [tip_sub, ""]]
                plc = UtilsAssembly.findPlacement(root_ref, False) if UtilsAssembly else None
                if plc is not None:
                    App.Console.PrintMessage(f"FCProject: LCS-Referenz (root) für {element.Label}: {root_ref}\n")
                    return root_ref
            except Exception:
                App.Console.PrintWarning(f"FCProject: Bevorzugte LCS-Referenz am Root für {element.Label} ungültig.\n")

        lcs_name = self._find_coordinate_system_name(root)
        if lcs_name:
            ref = [element, [lcs_name, ""]]
            if UtilsAssembly and hasattr(UtilsAssembly, 'addTipNameToSub'):
                tip_sub = UtilsAssembly.addTipNameToSub(ref)
                if tip_sub:
                    ref = [element, [tip_sub, ""]]
            try:
                plc = UtilsAssembly.findPlacement(ref, False) if UtilsAssembly else None
                if plc is not None:
                    App.Console.PrintMessage(f"FCProject: LCS-Referenz für {element.Label}: {ref}\n")
                    return ref
            except Exception as e:
                App.Console.PrintWarning(
                    f"FCProject: LCS-Referenz '{lcs_name}' für {element.Label} ist ungültig: {str(e)}\n"
                )

            # Fallback: versuche LCS-Referenz am Root-Objekt
            try:
                root_ref = [root, [lcs_name, ""]]
                if UtilsAssembly and hasattr(UtilsAssembly, 'addTipNameToSub'):
                    tip_sub = UtilsAssembly.addTipNameToSub(root_ref)
                    if tip_sub:
                        root_ref = [root, [tip_sub, ""]]
                plc = UtilsAssembly.findPlacement(root_ref, False) if UtilsAssembly else None
                if plc is not None:
                    App.Console.PrintMessage(f"FCProject: LCS-Referenz (root) für {element.Label}: {root_ref}\n")
                    return root_ref
            except Exception:
                App.Console.PrintWarning(f"FCProject: LCS-Referenz am Root für {element.Label} ungültig.\n")

        App.Console.PrintWarning(
            f"FCProject: Keine LCS-Referenz für Element '{element.Label}' gefunden. Joint wird ohne Referenz übersprungen.\n"
        )
        return None

    #FIXME: was ist mit direction, die wird nicht benutzt?
    def _compute_fixed_joint_offset(self, elem1, elem2, ref1, ref2, UtilsAssembly, direction):
        """Berechnet den Offset für ein fixiertes Joint, damit die aktuelle Position erhalten bleibt."""
        try:
            plc1 = UtilsAssembly.findPlacement(ref1, False)
            plc2 = UtilsAssembly.findPlacement(ref2, False)
            if plc1 is None or plc2 is None:
                return None

            global1 = UtilsAssembly.getJcsGlobalPlc(plc1, ref1)
            global2 = UtilsAssembly.getJcsGlobalPlc(plc2, ref2)
            if global1 is None or global2 is None:
                return None

            # Offset2 muss so gesetzt werden, dass der globale JCS von Reference2
            # mit dem globalen JCS von Reference1 übereinstimmt.
            try:
                offset2 = global2.inverse().multiply(global1)
            except Exception as e:
                App.Console.PrintWarning(f"FCProject: Fehler beim Multiplizieren von globalen JCS: {str(e)}\n")
                return None

            # Debug-Logging der Werte (kann komplexe Objekte sein)
            try:
                App.Console.PrintMessage(f"FCProject: plc1={str(plc1)}, plc2={str(plc2)}\n")
                App.Console.PrintMessage(f"FCProject: global1={str(global1)}, global2={str(global2)}\n")
                App.Console.PrintMessage(f"FCProject: berechnetes offset2={str(offset2)}\n")
            except Exception:
                pass

            return offset2
        except Exception as e:
            App.Console.PrintWarning(f"FCProject: Berechnung des Joint-Offsets fehlgeschlagen: {str(e)}\n")
            return None

    def _get_assembly_solver_module(self):
        """Versucht mehrere bekannte Assembly-Workbench-Importpfade."""
        import importlib

        candidates = [
            "freecad.assembly",
            "assembly",
            "Assembly",
            "A2",
            "A2.assembly",
            "FreeCADAssembly",
            "FreeCADAssembly.assembly",
        ]

        for package_name in candidates:
            try:
                module = importlib.import_module(package_name)
                if hasattr(module, 'solver'):
                    return module.solver
                if package_name.lower().endswith('solver'):
                    return module
            except Exception:
                continue
        return None

    def create_circular_pattern(self, source_element, count=3, radius=50.0):
        """
        Alternative: Erstellt ein Zirkular-Pattern (um eine Achse).
        
        Args:
            source_element: Das zu kopierende Element
            count: Anzahl der Kopien
            radius: Radius des Kreises (mm)
        """
        
        if count < 1:
            raise ValueError("Anzahl muss mindestens 1 sein!")
        
        if radius <= 0:
            raise ValueError("Radius muss > 0 sein!")
        
        # Erstelle Pattern-Gruppe
        self.pattern_group = self.doc.addObject("App::DocumentObjectGroup", f"CircularPattern_{source_element.Label}")
        self.pattern_group.Label = f"Circular Pattern: {source_element.Label}"
        self.assembly.addObject(self.pattern_group)
        
        import math
        angle_step = 360.0 / count
        
        for i in range(count):
            angle_rad = math.radians(angle_step * i)
            
            # Berechne Position auf dem Kreis
            x = radius * math.cos(angle_rad)
            y = radius * math.sin(angle_rad)
            
            # Kopiere Element
            new_element = self._duplicate_element(source_element, f"{source_element.Label}_Circular_{i+1}")
            
            # Positioniere auf dem Kreis
            current_placement = new_element.Placement
            new_placement = Placement(
                Vector(x, y, current_placement.Base.z),
                Rotation(App.Vector(0, 0, 1), angle_rad)
            )
            new_element.Placement = new_placement
            
            # Füge zur Gruppe hinzu
            self.pattern_group.addObject(new_element)
            
            App.Console.PrintMessage(f"FCProject: Circular-Element {i+1}/{count} erstellt.\n")
        
        self.doc.recompute()
        App.Console.PrintMessage(f"FCProject: Circular Pattern '{self.pattern_group.Label}' erfolgreich erstellt!\n")
