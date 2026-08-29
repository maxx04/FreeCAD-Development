#!/bin/bash
# Startet die ISOLIERTE Sandbox-Installation des Hintergrund-Agenten
# (/home/maxx/freecad/install-claude-sandbox) statt der normalen FreeCAD-Installation - dorthin
# deployt der Agent seine C++-Diagnose-/Fix-Builds (siehe project_fcproject_solver_data_fix_and_
# import_component-Memory, "Betriebs-Lektion" zum ABI-Vorfall vom 2026-08-28). Immer dieses
# Skript benutzen, wenn ein Live-Test speziell FUER den Agenten gebraucht wird - niemals die
# normale run-freecad-26.3.sh dafuer zweckentfremden, das war Ursache des ABI-Vorfalls.
#
# WICHTIG (2026-08-29, Nachtrag): dieses Skript (bzw. das gepinnte Desktop-Icon "FreeCAD Sandbox")
# hatte urspruenglich KEIN eigenes Nutzerprofil und teilte sich dadurch versehentlich
# ~/.config/FreeCAD/v26-3/user.cfg mit der echten, taeglich genutzten Installation - ein
# Testlauf darueber hat dabei einmal die komplette Fensteranordnung des Nutzers ueberschrieben.
# Deshalb jetzt per FREECAD_USER_HOME (App::Application::getCustomPaths(),
# src/App/Application.cpp) ein eigenes, dauerhaftes Profil-Verzeichnis erzwungen - Falle dabei:
# das Zielverzeichnis MUSS schon existieren, sonst wird der Wert stillschweigend verworfen und
# FreeCAD faellt auf den echten, geteilten Pfad zurueck (deshalb IMMER zuerst mkdir -p).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ISOLATED_PROFILE="${SCRIPT_DIR}/freecad-sandbox-profile"
mkdir -p "$ISOLATED_PROFILE"
export FREECAD_USER_HOME="$ISOLATED_PROFILE"

FALLBACK_VENV_DIR="/home/maxx/Dokumente/FreeCAD-Development/.venv"
if VENV_DIR="$(cd "${SCRIPT_DIR}/../../.venv" 2>/dev/null && pwd)"; then
    :
else
    VENV_DIR="${FALLBACK_VENV_DIR}"
fi
source "${VENV_DIR}/bin/activate"
export VIRTUAL_ENV="${VENV_DIR}"

PYSIDE_QT="${VIRTUAL_ENV}/lib/python3.12/site-packages/PySide6/Qt"

export QT_PLUGIN_PATH="${PYSIDE_QT}/plugins"
export LD_LIBRARY_PATH="${PYSIDE_QT}/lib:/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export PYTHONNOUSERSITE=1
export PYTHONPATH="${VIRTUAL_ENV}/lib/python3.12/site-packages"
export QT_QPA_PLATFORM=xcb

LOG_DIR="$HOME/freecad/logs"
mkdir -p "$LOG_DIR"
TS="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="${LOG_DIR}/freecad-sandbox-${TS}.log"

echo "Starte FreeCAD-SANDBOX (Agent-Diagnose-Build), Logfile: $LOG_FILE"

exec /home/maxx/freecad/install-claude-sandbox/bin/FreeCAD -l --log-file "$LOG_FILE" "$@"
