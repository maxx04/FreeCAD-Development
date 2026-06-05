# Macro Version: 1.0.0 - FCProject: Material-Suchwerkzeug via Core UUID
import FreeCAD as App

def get_native_material_by_name(target_name):
    """Sucht im Core-MaterialManager nach dem Namen und gibt das echte C++ Objekt zurück."""
    try:
        import Materials # type: ignore
        manager = Materials.MaterialManager()
        
        # Wir durchsuchen alle registrierten Systemmaterialien nach dem Namen
        for mat_id, mat_obj in manager.Materials.items():
            if mat_obj.Name.lower() == target_name.lower():
                # Gefunden! Wir holen das echte C++ Objekt über seine UUID
                cpp_material = manager.getMaterial(mat_id)
                App.Console.PrintMessage(f"FCProject: UUID '{mat_id}' für Werkstoff '{target_name}' ermittelt.\n")
                return cpp_material
                
        App.Console.PrintWarning(f"FCProject: Werkstoff '{target_name}' nicht im System-Katalog gefunden!\n")
        return None
    except Exception as e:
        App.Console.PrintError(f"FCProject Fehler im MaterialManager-Zugriff: {str(e)}\n")
        return None
