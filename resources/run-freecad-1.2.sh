#!/bin/bash
# Startet die selbst gebaute FreeCAD 1.2 mit den Qt-Bibliotheken/Plugins aus dem PySide6-venv,
# damit keine Qt-Plattform-Plugin-Fehler durch eine inkompatible System-Qt-Version auftreten.

# Gleiches venv-Setup wie in ~/.bashrc (Zeilen 119-128), damit FreeCAD
# exakt dieselbe Umgebung sieht wie ein Terminal mit aktiviertem venv.
source /home/maxx/Projects/FreeCAD-Development/.venv/bin/activate

PYSIDE_QT="${VIRTUAL_ENV}/lib/python3.12/site-packages/PySide6/Qt"

export QT_PLUGIN_PATH="${PYSIDE_QT}/plugins"
export LD_LIBRARY_PATH="${PYSIDE_QT}/lib:/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export PYTHONNOUSERSITE=1
export PYTHONPATH="${VIRTUAL_ENV}/lib/python3.12/site-packages"

exec /home/maxx/freecad/FreeCAD_weekly-2026.07.01-Linux-x86_64.AppImage "$@"
#exec /home/maxx/freecad/install/bin/FreeCAD "$@"