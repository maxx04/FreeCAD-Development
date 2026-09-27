#!/bin/bash
# Startet die selbst gebaute FreeCAD 26.3 mit den Qt-Bibliotheken/Plugins aus dem PySide6-venv,
# damit keine Qt-Plattform-Plugin-Fehler durch eine inkompatible System-Qt-Version auftreten.

# Gleiches venv-Setup wie in ~/.bashrc, damit FreeCAD
# exakt dieselbe Umgebung sieht wie ein Terminal mit aktiviertem venv.
# Pfad relativ zum Skript-Ort ermittelt (FCProject/resources/../../.venv),
# damit ein Verschieben von FreeCAD-Development/ (wie z.B. Dokuments -> Dokumente)
# dieses Skript nicht erneut bricht. Funktioniert so nur, wenn das Skript aus
# dem Repo heraus läuft - die per CMake nach ~/freecad/ installierte Kopie
# (Ziel des Desktop-Starters) liegt in einem eigenen, unabhängigen Verzeichnis-
# baum, daher der absolute Fallback als zweite Instanz. VIRTUAL_ENV wird nach
# dem source in jedem Fall überschrieben, weil im venv selbst (bin/activate)
# noch der absolute Erstellungspfad einprogrammiert ist, der sich beim
# Verschieben nicht automatisch mitändert.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FALLBACK_VENV_DIR="/home/maxx/Dokumente/FreeCAD-Development/.venv"
if VENV_DIR="$(cd "${SCRIPT_DIR}/../../.venv" 2>/dev/null && pwd)"; then
    :
else
    VENV_DIR="${FALLBACK_VENV_DIR}"
fi
source "${VENV_DIR}/bin/activate"
export VIRTUAL_ENV="${VENV_DIR}"

SITE_PACKAGES="${VIRTUAL_ENV}/lib/python3.12/site-packages"

# FCPROJECT-FIX (2026-09-25, Nutzer-Report nach Arbeitsumgebungswechsel - FreeCAD stuerzte
# beim Start ab, Log zeigte kaskadierende "ImportError: libshiboken6.abi3.so.6.11: cannot
# open shared object file" bzw. "libpyside6.abi3.so.6.11: ... nicht gefunden" quer durch
# alle Mod/*-Python-Module, endend in "No viable version of PySide was found"):
# SITE_PACKAGES/PySide6/Qt/lib (die bisherige Quelle) ist inzwischen LEER - die venv-
# PySide6-Installation wurde offenbar auf Version 6.11 aktualisiert, OHNE eigene Qt-/
# PySide-/shiboken-.so-Dateien zu buendeln (frueher: 6.6, mitgebuendelt). Die echten
# .so-Dateien fuer 6.11 liegen jetzt in einem separaten, dafuer vorbereiteten Qt6.11-
# Sysroot (vermutlich aus KDE-Neon-apt-Paketen extrahiert, siehe
# neon-qt6-pyside6/apt-sandbox/) - NUR von dort kommen sowohl passende Qt6-Bibliotheken
# ALS AUCH libpyside6/libshiboken6 in Version 6.11 (zur venv-Python-Seite passend). Live
# verifiziert: "import shiboken6/PySide6/PySide6.QtCore" im venv-Python klappt erst damit.
# Python-PAKETE (.py/.pyi) kommen weiterhin aus der venv (SITE_PACKAGES via PYTHONPATH
# unten) - nur die .so-Bibliotheken/Plugins kommen aus diesem Sysroot.
#
# WICHTIG (2026-09-27, Nutzer-Report "error while loading shared libraries:
# libpyside6.abi3.so.6.11: cannot open shared object file"): dieser Fix wurde zuerst NUR in
# der per CMake DEPLOYTEN Kopie (~/freecad/run-freecad-26.3.sh) gemacht, nie hier in der
# Repo-Quelle - ein ganz normaler `cmake --build --target install`-Lauf (fuer FCProjectCore,
# nichts mit Qt zu tun) hat die deployte Kopie beim naechsten Mal wieder mit DIESER
# (damals noch alten) Datei ueberschrieben und den Fix damit stillschweigend rueckgaengig
# gemacht. Immer HIER (Repo-Quelle) aendern, nie nur an der deployten Kopie direkt.
NEON_QT_LIB="/home/maxx/Dokumente/FreeCAD-Development/neon-qt6-pyside6/root/usr/lib/x86_64-linux-gnu"
export QT_PLUGIN_PATH="${NEON_QT_LIB}/qt6/plugins"
export LD_LIBRARY_PATH="${NEON_QT_LIB}:/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export PYTHONNOUSERSITE=1
export PYTHONPATH="${VIRTUAL_ENV}/lib/python3.12/site-packages"
# XWayland erzwingen: Coin3D (FreeCAD 3D-Engine) nutzt GLX, nicht EGL –
# nach Mutter-Update 46.2-16 werden Apps sonst nativ-Wayland gestartet, was crasht.
export QT_QPA_PLATFORM=xcb

LOG_DIR="$HOME/freecad/logs"
mkdir -p "$LOG_DIR"
TS="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="${LOG_DIR}/freecad-compiled-${TS}.log"

# Erzwingt "eingebauten statt nativen Datei-Dialog" (BaseApp/Preferences/Dialog/DontUseNativeDialog)
# in der aktiven FreeCAD-Profil-user.cfg, falls noch nicht gesetzt. Grund: der native Speichern-
# unter-Dialog haengt auf dieser Maschine lautlos fest (Hide/Show main window in den Logs, dann
# nichts mehr - kein Crash) - vermutlich derselbe XWayland/Mutter-Portal-Konflikt, der schon
# QT_QPA_PLATFORM=xcb oben noetig macht. Bewusst bei JEDEM Start geprueft statt nur einmalig
# manuell gesetzt: FreeCAD legt bei einem Versionssprung (z.B. v26-3 -> v27-x) keinen neuen
# Profil-Ordner an, sondern nimmt den zuletzt genutzten weiter - der Trick ueberlebt das nicht
# automatisch, ein frischer/anderer Profil-Ordner haette die Einstellung sonst wieder verloren.
python3 - <<'PYEOF'
import glob
import os
import xml.etree.ElementTree as ET

candidates = sorted(
    glob.glob(os.path.expanduser("~/.config/FreeCAD/v*/user.cfg")),
    key=os.path.getmtime,
    reverse=True,
)
if not candidates:
    print("Kein FreeCAD-Profil (user.cfg) gefunden - ueberspringe DontUseNativeDialog-Check "
          "(wird beim naechsten Start erneut versucht, sobald FreeCAD eins angelegt hat).")
else:
    cfg_path = candidates[0]
    tree = ET.parse(cfg_path)
    root = tree.getroot()

    def get_or_create_group(parent, name):
        for child in parent.findall("FCParamGroup"):
            if child.get("Name") == name:
                return child
        return ET.SubElement(parent, "FCParamGroup", {"Name": name})

    base_app = get_or_create_group(root.find("FCParamGroup"), "BaseApp")  # Root -> BaseApp
    prefs = get_or_create_group(base_app, "Preferences")
    dialog = get_or_create_group(prefs, "Dialog")

    entry = next((e for e in dialog.findall("FCBool") if e.get("Name") == "DontUseNativeDialog"), None)
    if entry is not None and entry.get("Value") == "1":
        pass  # schon gesetzt, nichts zu tun
    else:
        if entry is None:
            entry = ET.SubElement(dialog, "FCBool", {"Name": "DontUseNativeDialog"})
        entry.set("Value", "1")
        tree.write(cfg_path, encoding="UTF-8", xml_declaration=True)
        print(f"FCProject: DontUseNativeDialog=1 in {cfg_path} gesetzt (native Speichern-Dialoge umgangen).")
PYEOF

echo "Starte FreeCAD 26.3 mit Qt aus venv, Logfile: $LOG_FILE"

exec /home/maxx/freecad/install/bin/FreeCAD -l --log-file "$LOG_FILE" "$@"