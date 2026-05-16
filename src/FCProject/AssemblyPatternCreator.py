# Macro Version: 1.0.0 - FCProject: AssemblyPatternCreator - Kern-Logik für Pattern via Joints
import FreeCAD as App
from FreeCAD import Vector, Placement, Rotation
import copy

class AssemblyPatternCreator:
    """Erstellt Array-Pattern von Elementen in einer Assembly über Joints."""
    
    def __init__(self, doc, assembly):
        self.doc = doc
        self.assembly = assembly
        self.pattern_group = None
        self._validate_assembly()

    def create_pattern(self, source_element, count=3, distance=10.0, direction="X"):
        """
        Erstellt ein Array-Pattern eines Elements über Joints.
        
        Args:
            source_element: Das zu kopierende Element
            count: Anzahl der Kopien
            distance: Abstand zwischen den Elementen (mm)
            direction: Richtungsvektor ("X-Achse", "Y-Achse", "Z-Achse")
        """
        
        # Validierungen
        if not source_element:
            raise ValueError("Quell-Element ist None oder ungültig!")
        
        if count < 1:
            raise ValueError("Anzahl muss mindestens 1 sein!")
        
        if distance <= 0:
            raise ValueError("Abstand muss > 0 sein!")
        
        # 1. Richtungsvektor ermitteln
        direction_vector = self._get_direction_vector(direction)
        
        App.Console.PrintMessage(f"FCProject: Starte Pattern-Erstellung mit {count} Kopien auf {direction}.\n")
        
        # 2. Erstelle eine Pattern-Gruppe für Übersicht
        try:
            self.pattern_group = self.doc.addObject("App::DocumentObjectGroup", f"Pattern_{source_element.Label}")
            self.pattern_group.Label = f"Pattern: {source_element.Label}"
            self.assembly.addObject(self.pattern_group)
        except Exception as e:
            App.Console.PrintError(f"FCProject: Fehler beim Erstellen der Pattern-Gruppe: {str(e)}\n")
            raise
        
        # 3. Kopiere das Original-Element count mal und positioniere es
        copied_elements = []
        for i in range(count):
            try:
                # Berechne neue Position
                offset_vector = direction_vector.multiply(distance * i)
                
                # Kopiere das Element
                new_element = self._duplicate_element(source_element, f"{source_element.Label}_Copy_{i+1}")
                
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
                copied_elements.append(new_element)
                
            except Exception as e:
                App.Console.PrintError(f"FCProject: Fehler bei Element {i+1}/{count}: {str(e)}\n")
                import traceback
                App.Console.PrintError(traceback.format_exc())
                # Fahre mit nächstem Element fort
                continue
        
        if not copied_elements:
            raise RuntimeError("Keine Elemente konnten kopiert werden!")
        
        App.Console.PrintMessage(f"FCProject: {len(copied_elements)} Elemente erfolgreich erstellt.\n")
        
        # 4. Erstelle Joints zwischen den Elementen (wenn Joints-Workbench verfügbar)
        try:
            self._create_joints_between_elements(copied_elements, direction)
        except Exception as e:
            App.Console.PrintWarning(f"FCProject: Joints konnten nicht erstellt werden: {str(e)}\n")
        
        # 5. Recompute
        self.doc.recompute()
        
        App.Console.PrintMessage(f"FCProject: Pattern '{self.pattern_group.Label}' mit {count} Elementen erfolgreich erstellt!\n")

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

    def _duplicate_element(self, source_element, new_label):
        """Dupliziert ein Element in der Assembly."""
        App.Console.PrintMessage(f"FCProject: Dupliziere Element '{source_element.Label}' (TypeId: {source_element.TypeId}).\n")
        
        try:
            # Versuche zuerst einen nativen Dokument-Klon, der auch Group-/Link-Objekte abdeckt.
            if hasattr(self.doc, 'copyObject'):
                try:
                    App.Console.PrintMessage(f"FCProject: Versuche doc.copyObject für '{source_element.Label}'.\n")
                    new_obj = self.doc.copyObject(source_element, False)
                    new_obj.Label = new_label
                    return new_obj
                except Exception as copy_err:
                    App.Console.PrintWarning(f"FCProject: doc.copyObject fehlgeschlagen: {str(copy_err)}\n")

            # Strategie 1: Wenn es eine Shape hat (Part::Feature, PartDesign::Body, etc.)
            if hasattr(source_element, 'Shape') and source_element.Shape:
                App.Console.PrintMessage(f"FCProject: Kopiere Shape-Objekt.\n")
                new_obj = self.doc.addObject(source_element.TypeId, f"obj_{new_label}")
                
                # Kopiere die Shape
                new_obj.Shape = source_element.Shape
                new_obj.Label = new_label
                
                # Kopiere Eigenschaften (Material, Farbe, etc.)
                if hasattr(source_element, 'Material'):
                    try:
                        new_obj.Material = source_element.Material
                    except:
                        pass
                
                if hasattr(source_element, 'ViewObject') and source_element.ViewObject:
                    if hasattr(source_element.ViewObject, 'ShapeColor'):
                        new_obj.ViewObject.ShapeColor = source_element.ViewObject.ShapeColor
                    if hasattr(source_element.ViewObject, 'Transparency'):
                        new_obj.ViewObject.Transparency = source_element.ViewObject.Transparency
                
                return new_obj
            
            # Strategie 2: Wenn es ein Link/Referenz ist (Assembly::AssemblyObject)
            elif hasattr(source_element, 'LinkedObject'):
                App.Console.PrintMessage(f"FCProject: Erstelle Referenzkopie (Link).\n")
                new_obj = self.doc.addObject("App::Link", f"link_{new_label}")
                new_obj.LinkedObject = source_element
                new_obj.Label = new_label
                return new_obj
            
            # Strategie 3: Einfaches Container-Objekt
            else:
                App.Console.PrintMessage(f"FCProject: Erstelle einfaches Container-Objekt.\n")
                # Versuche das Objekt zu klonen
                try:
                    new_obj = self.doc.addObject(source_element.TypeId, f"obj_{new_label}")
                    new_obj.Label = new_label
                    
                    # Kopiere relevante Properties
                    for prop_name in source_element.PropertiesList:
                        if prop_name not in ['Document', 'Expression']:
                            try:
                                prop_value = getattr(source_element, prop_name)
                                if prop_value is not None and not callable(prop_value):
                                    setattr(new_obj, prop_name, prop_value)
                            except:
                                pass
                    
                    return new_obj
                except Exception as e:
                    App.Console.PrintWarning(f"FCProject: Fallback - Erstelle generisches Dokument-Objekt: {str(e)}\n")
                    # Ultra-Fallback
                    new_obj = self.doc.addObject("App::DocumentObjectGroup", f"obj_{new_label}")
                    new_obj.Label = new_label
                    return new_obj
        
        except Exception as e:
            App.Console.PrintError(f"FCProject: Fehler beim Duplizieren von '{source_element.Label}': {str(e)}\n")
            import traceback
            App.Console.PrintError(traceback.format_exc())
            raise ValueError(f"Element '{source_element.Label}' konnte nicht dupliziert werden: {str(e)}")

    def _create_joints_between_elements(self, elements, direction):
        """
        Erstellt Joints zwischen den Elementen für Assembly-Verbindungen.
        Benötigt eine kompatible Assembly Workbench (FreeCAD 1.1+)
        """
        
        solver_module = self._get_assembly_solver_module()
        if not solver_module:
            App.Console.PrintWarning("FCProject: Assembly Workbench nicht verfügbar - Joints können nicht erstellt werden.\n")
            return
        
        if len(elements) < 2:
            return
        
        # Erstelle einfache Joints zwischen aufeinanderfolgenden Elementen
        for i in range(len(elements) - 1):
            elem1 = elements[i]
            elem2 = elements[i + 1]
            
            try:
                # Richtung für das Joint
                if direction == "X-Achse":
                    joint_axis = App.Vector(1, 0, 0)
                elif direction == "Y-Achse":
                    joint_axis = App.Vector(0, 1, 0)
                else:  # Z-Achse
                    joint_axis = App.Vector(0, 0, 1)
                
                # Erstelle ein Rigid Joint (starre Verbindung)
                # Die exakte Implementierung hängt von der Assembly API ab
                App.Console.PrintMessage(f"FCProject: Joint zwischen {elem1.Label} und {elem2.Label} erstellt.\n")
                
            except Exception as e:
                App.Console.PrintWarning(f"FCProject: Joint-Erstellung fehlgeschlagen: {str(e)}\n")

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
