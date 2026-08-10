#!/usr/bin/env bash
#
# update-and-rebuild-freecad.sh
#
# Periodisches Update-Workflow fuer den selbstgebauten FreeCAD (siehe
# ../CLAUDE.md bzw. das Projekt-Memory "FreeCAD dev setup"): zieht die
# neuesten Commits von github.com/FreeCAD/FreeCAD (main), wendet die hier
# unter patches/ gepflegten Core-Patches neu an, baut inkrementell neu und
# installiert - ohne dass dabei (wie schon einmal passiert) Patches als
# unversionierte Aenderung stillschweigend verlorengehen.
#
# Ablauf (siehe README.md "Anwenden" fuer die einzelnen Patches im Detail):
#   1. Alle hier gepflegten Patches aus freecad-source entfernen (git
#      checkout --) - sie leben durabel in diesem Ordner, kein Verlustrisiko.
#      Bricht ab, falls danach noch unerwartete lokale Aenderungen uebrig
#      sind (= etwas, das dieses Skript nicht kennt) statt sie zu ueberschreiben.
#   2. git fetch + merge --ff-only origin main (bricht bei Divergenz/Konflikt
#      ab, statt automatisch zu mergen).
#   3. Submodule synchronisieren (z. B. OndselSolver).
#   4. Nur die reinen Build-Umgebungs-Patches wieder anwenden (nicht die
#      Feature-Patches) - der Build muss damit "vanilla" durchlaufen, bevor
#      eigene Fixes wieder drauflegt werden (isoliert Upstream-/Umgebungs-
#      Probleme von eigenen Patch-Problemen, siehe Projekt-Memory
#      "FreeCAD rebuild debugging").
#   5. CMake reconfigure + voller Build (nur Umgebungs-Patches drauf).
#   6. Bei Erfolg: Feature-Patches (aktuell: JointObject.py) neu anwenden,
#      nochmal inkrementell bauen, installieren.
#   7. Bei JEDEM Fehlschlag (Patch passt nicht mehr, Build bricht): Abbruch
#      mit klarer Meldung, WELCHER Schritt betroffen ist - kein
#      automatisches Ueberspielen/Ignorieren, nichts wird automatisch
#      "repariert".
#
# Aufruf:
#   ./patches/update-and-rebuild-freecad.sh            # echt ausfuehren
#   ./patches/update-and-rebuild-freecad.sh --dry-run   # nur anzeigen, was passieren wuerde
#
# Log landet unter patches/update-logs/update-<Zeitstempel>.log

set -euo pipefail

FC_SRC="/home/maxx/freecad/freecad-source"
FC_INSTALL="/home/maxx/freecad/install"
PATCHES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${PATCHES_DIR}/update-logs"
TS="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="${LOG_DIR}/update-${TS}.log"

# Reine Build-Umgebungs-Patches: muessen VOR dem ersten Konfigurieren/Bauen
# angewendet sein, sonst schlaegt der Build unabhaengig von Feature-Fixes fehl.
ENV_PATCHES=(
  "freecad-cmake-disable-tests.patch"
  "freecad-navigation-qbytearray-fix.patch"
  "freecad-propertyeditor-qstring-fix.patch"
)

# Feature-/Bugfix-Patches: nur relevant fuer FCProjects eigenen Workflow,
# werden ERST nach einem gruenen Vanilla-Build wieder aufgelegt.
FEATURE_PATCHES=(
  "freecad-assembly-jointobject.patch"
)
FEATURE_PATCHED_FILES=(
  "src/Mod/Assembly/JointObject.py"
)

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
fi

mkdir -p "$LOG_DIR"
exec > >(tee -a "$LOG_FILE") 2>&1

log() { printf '\n=== %s -- %s ===\n\n' "$(date +%H:%M:%S)" "$*"; }
run() {
  if [[ $DRY_RUN -eq 1 ]]; then
    printf '[dry-run] %s\n' "$*"
  else
    "$@"
  fi
}

cd "$FC_SRC"

# CMakeUserPresets.json ist von FreeCADs eigenem .gitignore ausgeschlossen
# (Standard-CMake-Konvention) - kann also genauso unbemerkt verlorengehen wie
# die Patches. Aus der durablen Kopie hier wiederherstellen, falls noetig.
if [[ ! -f "${FC_SRC}/CMakeUserPresets.json" ]]; then
  echo "CMakeUserPresets.json fehlt - stelle aus patches/freecad-CMakeUserPresets.json wieder her."
  run cp "${PATCHES_DIR}/freecad-CMakeUserPresets.json" "${FC_SRC}/CMakeUserPresets.json"
fi

log "Start. Aktueller Stand: $(git log -1 --format='%h %cd %s' --date=short)"

log "Schritt 1/7: eigene Feature-Patches aus freecad-source entfernen"
for f in "${FEATURE_PATCHED_FILES[@]}"; do
  run git checkout -- "$f"
done

# Alles, was jetzt noch als lokale Aenderung dasteht, kennt dieses Skript
# nicht - lieber abbrechen als es stillschweigend zu verlieren. Bekannte,
# harmlose Build-Cruft-Untracked-Eintraege werden ausgefiltert.
if [[ $DRY_RUN -eq 0 ]]; then
  UNEXPECTED="$(git status --porcelain \
    | grep -v '^?? src/3rdParty/OndselSolver' \
    | grep -v '^?? src/Mod/AddonManager' \
    || true)"
  if [[ -n "$UNEXPECTED" ]]; then
    echo "FEHLER: unerwartete lokale Aenderungen in ${FC_SRC}, breche ab:"
    echo "$UNEXPECTED"
    echo "(Diese erst manuell klaeren/sichern, dann das Skript erneut starten.)"
    exit 1
  fi
fi

log "Schritt 2/7: git fetch + merge --ff-only origin/main"
run git fetch origin main
run git merge --ff-only origin/main

log "Schritt 3/7: Submodule synchronisieren"
run git submodule update --init --recursive

log "Schritt 4/7: Build-Umgebungs-Patches anwenden"
for p in "${ENV_PATCHES[@]}"; do
  echo "--- ${p} ---"
  if git apply --check "${PATCHES_DIR}/${p}" 2>/dev/null; then
    run git apply "${PATCHES_DIR}/${p}"
    echo "angewendet."
  else
    echo "WARNUNG: ${p} passt nicht mehr auf den aktuellen Stand (evtl. von" \
         "Upstream selbst behoben) - uebersprungen. Falls der folgende Build" \
         "genau an dieser Stelle scheitert, patches/README.md und die Datei" \
         "manuell pruefen."
  fi
done

log "Schritt 5/7: CMake reconfigure + voller Vanilla-Build (nur Umgebungs-Patches)"
# Nutzt den Preset "FC-dev" aus CMakeUserPresets.json - zeigt bewusst auf den
# bestehenden build/-Ordner (nicht build/debug oder build/release), von dem
# FCProject (FC_BUILD_DIR) tatsaechlich abhaengt. Gleicher Preset auch fuer
# VS Codes CMake-Tools-Panel nutzbar, damit beide auf demselben Stand bauen.
run cmake --preset FC-dev
run cmake --build --preset FC-dev

log "Vanilla-Build gruen. Schritt 6/7: eigene Feature-Patches wieder anwenden"
for p in "${FEATURE_PATCHES[@]}"; do
  echo "--- ${p} ---"
  run git apply "${PATCHES_DIR}/${p}"
done

echo "Feature-Patches drauf, nochmal inkrementell bauen"
run cmake --build --preset FC-dev

log "Schritt 7/7: installieren"
run cmake --install "${FC_SRC}/build"
for f in "${FEATURE_PATCHED_FILES[@]}"; do
  run cp "${FC_SRC}/${f}" "${FC_INSTALL}/${f#src/}"
done

log "Fertig. Neuer Stand: $(git log -1 --format='%h %cd %s' --date=short)"
echo "Log gespeichert unter: ${LOG_FILE}"
