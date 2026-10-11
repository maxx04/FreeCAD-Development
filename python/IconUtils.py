# FCProject: liefert den passenden Icon-Pfad abhaengig vom aktiven Theme (hell/dunkel).
#
# Theme-Erkennung ueber die tatsaechlich gerenderte Fenster-Hintergrundfarbe (QPalette.Window)
# statt ueber einen Stylesheet-/Theme-Namen zu raten - funktioniert dadurch unabhaengig davon,
# welches konkrete Theme aktiv ist (FreeCADs eigenes Dark-Theme, OpenDark, ein individuelles
# Stylesheet, ...), weil sie direkt misst statt zu raten.
import os


def icon_path(icon_dir, filename):
    """Pfad zu filename in icon_dir - bei dunklem Theme stattdessen '<name>_dark.svg',
    falls diese Datei existiert, sonst der normale (helle) Pfad als Fallback."""
    light_path = os.path.join(icon_dir, filename)
    if _is_dark_theme():
        base, ext = os.path.splitext(filename)
        dark_path = os.path.join(icon_dir, base + "_dark" + ext)
        if os.path.exists(dark_path):
            return dark_path
    return light_path


def _is_dark_theme():
    try:
        from PySide6 import QtWidgets
        app = QtWidgets.QApplication.instance()
        if app is None:
            return False
        window_color = app.palette().window().color()
        # Wahrgenommene Helligkeit (ITU-R BT.709) - < 128 von 255 gilt als dunkles Theme.
        luminance = (
            0.2126 * window_color.red()
            + 0.7152 * window_color.green()
            + 0.0722 * window_color.blue()
        )
        return luminance < 128
    except Exception:
        return False
