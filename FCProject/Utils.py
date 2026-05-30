def _ensure_property(App, obj, prop_type, name, group, desc, default=None):
        try:
            if not hasattr(obj, name):
                obj.addProperty(prop_type, name, group, desc)
            if default is not None:
                setattr(obj, name, default)
        except Exception as e:
            App.Console.PrintWarning(f"FCProject: Fehler beim Anlegen/Setzen Property '{name}': {e}\n")