#!/bin/bash
# Startet die selbst gebaute FreeCAD 26.3 mit den Qt-Bibliotheken/Plugins aus dem PySide6-venv,
# damit keine Qt-Plattform-Plugin-Fehler durch eine inkompatible System-Qt-Version auftreten.

# Gleiches venv-Setup wie in ~/.bashrc, damit FreeCAD
# exakt dieselbe Umgebung sieht wie ein Terminal mit aktiviertem venv.
source /home/maxx/Documents/FreeCAD-Development/.venv/bin/activate

PYSIDE_QT="${VIRTUAL_ENV}/lib/python3.12/site-packages/PySide6/Qt"

export QT_PLUGIN_PATH="${PYSIDE_QT}/plugins"
export LD_LIBRARY_PATH="${PYSIDE_QT}/lib:/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export PYTHONNOUSERSITE=1
export PYTHONPATH="${VIRTUAL_ENV}/lib/python3.12/site-packages"
# XWayland erzwingen: Coin3D (FreeCAD 3D-Engine) nutzt GLX, nicht EGL –
# nach Mutter-Update 46.2-16 werden Apps sonst nativ-Wayland gestartet, was crasht.
export QT_QPA_PLATFORM=xcb

exec /home/maxx/freecad/install/bin/FreeCAD -l "$@"
