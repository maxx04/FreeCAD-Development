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
#   6. Bei Erfolg: Feature-Patches (aktuell: FileDialog-Suchfilter) neu anwenden,
#      nochmal inkrementell bauen, installieren.
#   7. Bei JEDEM Fehlschlag (Patch passt nicht mehr, Build bricht): Abbruch
#      mit klarer Meldung, WELCHER Schritt betroffen ist - kein
#      automatisches Ueberspielen/Ignorieren, nichts wird automatisch
#      "repariert".
#
# Aufruf:
#   ./patches/update-and-rebuild-freecad.sh            # echt ausfuehren
#   ./patches/update-and-rebuild-freecad.sh --dry-run   # nur anzeigen, was passieren wuerde
#   JOBS=6 ./patches/update-and-rebuild-freecad.sh      # Parallelitaet manuell uebersteuern
#
# Log landet unter patches/update-logs/update-<Zeitstempel>.log
#
# WICHTIG zur Parallelitaet: NICHT einfach nproc nehmen. FreeCAD/OpenCASCADE-
# C++-Uebersetzungseinheiten sind sehr speicherhungrig (oft 1-2+ GB je
# cc1plus-Prozess); bei 12 Kernen und 15 GB RAM auf dieser Maschine hat ein
# -j12-Build zusammen mit VS Codes eigener IntelliSense-Indizierung schon
# einmal den gesamten verfuegbaren Speicher gesprengt - systemd-oomd hat
# daraufhin die komplette VS-Code-Prozessgruppe getoetet (inkl. der laufenden
# Claude-Code-Session/diesem Skript, da Claude Code selbst als VS-Code-
# Extension laeuft). Deshalb unten eine RAM-basierte, konservative
# Job-Obergrenze statt naiv $(nproc).

set -euo pipefail

FC_SRC="/home/maxx/freecad/freecad-source"
FC_INSTALL="/home/maxx/freecad/install"
PATCHES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${PATCHES_DIR}/update-logs"
TS="$(date +%Y%m%d-%H%M%S)"

# Grobe Faustregel: ~2 GB RAM pro parallelem Compile-Job einplanen, dabei
# 4 GB Luft fuer VS Code (inkl. dessen eigener C++-IntelliSense-Indizierung,
# die genau beim letzten Crash mit reinspielte) und den Rest des Systems
# lassen. Auf dieser 15-GB-Maschine ergibt das JOBS=5 statt der urspruenglich
# genutzten 12 (= nproc). Per JOBS=<n> env var uebersteuerbar.
if [[ -z "${JOBS:-}" ]]; then
  MEM_KB="$(awk '/MemTotal/ {print $2}' /proc/meminfo)"
  MEM_GB=$(( MEM_KB / 1024 / 1024 ))
  JOBS=$(( (MEM_GB - 4) / 2 ))
  [[ $JOBS -lt 2 ]] && JOBS=2
  CPU_JOBS="$(nproc)"
  [[ $JOBS -gt $CPU_JOBS ]] && JOBS=$CPU_JOBS
fi
LOG_FILE="${LOG_DIR}/update-${TS}.log"

# FCPROJECT-PATCH (2026-09-27, Nutzerwunsch "PATCHES.txt anlegen, an dem beim Update Patches
# angewendet werden sollen"): ENV_PATCHES/FEATURE_PATCHES kommen jetzt aus PATCHES.txt (einzige
# Stelle zum Aktivieren/Deaktivieren eines Patches) statt hier hartkodiert zu sein - Grund und
# Hintergrund zu jedem einzelnen Patch steht weiterhin in README.md, nicht hier verdoppelt.
# Reine Build-Umgebungs-Patches (ENV) muessen VOR dem ersten Konfigurieren/Bauen angewendet
# sein, sonst schlaegt der Build unabhaengig von Feature-Fixes fehl - FEATURE-Patches werden
# erst nach einem gruenen Vanilla-Build wieder aufgelegt (siehe Ablauf oben).
parse_patch_list() {
  local section="$1" in_section=0 line
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    if [[ "$line" =~ ^\[([A-Z]+)\]$ ]]; then
      [[ "${BASH_REMATCH[1]}" == "$section" ]] && in_section=1 || in_section=0
      continue
    fi
    [[ $in_section -eq 0 ]] && continue
    [[ -z "$line" || "$line" == \#* ]] && continue
    printf '%s\n' "$line"
  done < "${PATCHES_DIR}/PATCHES.txt"
}
mapfile -t ENV_PATCHES < <(parse_patch_list ENV)
mapfile -t FEATURE_PATCHES < <(parse_patch_list FEATURE)

# Dateien, die die obigen Patches beruehren, werden AUTOMATISCH aus jedem Patch selbst
# ermittelt ("diff --git a/<Datei> b/..."-Zeilen) statt von Hand in einer zweiten Liste
# gepflegt zu werden - letzteres war wiederholt Ursache vergessener Eintraege, die einen
# Resume nach Abbruch faelschlich als "unerwartete Aenderung" durchfallen liessen (Vorfall
# 2026-08-18/2026-08-23).
files_touched_by_patches() {
  local p
  for p in "$@"; do
    # "|| true": unter set -o pipefail wuerde ein Patch ganz ohne "diff --git a/"-Zeile
    # (sollte nie vorkommen, aber besser defensiv) sonst die ganze Funktion vorzeitig
    # abbrechen und die restlichen Patches der Schleife stillschweigend auslassen.
    grep -E '^diff --git a/' "${PATCHES_DIR}/${p}" | sed -E 's#^diff --git a/(.+) b/.*#\1#' || true
  done | sort -u
}
mapfile -t ENV_PATCHED_FILES < <(files_touched_by_patches "${ENV_PATCHES[@]}")
mapfile -t FEATURE_PATCHED_FILES < <(files_touched_by_patches "${FEATURE_PATCHES[@]}")

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

# FCPROJECT-FIX (2026-09-25, Nutzer-Report nach Arbeitsumgebungswechsel - CMake-Schritt 5
# brach mit "ImportError: libshiboken6.abi3.so.6.11: cannot open shared object file" ab):
# CMakeLists.txt findet das venv-Python zwar ueber CMakeUserPresets.json, aber sobald dieses
# Python versucht, shiboken6/PySide6 zu importieren (fuer den PySide6.QtSvgWidgets-Check),
# braucht es passende .so-Dateien. SITE_PACKAGES/PySide6/Qt/lib (die alte Quelle) ist
# inzwischen LEER - die venv-PySide6-Installation wurde auf Version 6.11 aktualisiert, OHNE
# eigene Qt-/PySide-/shiboken-.so-Dateien zu buendeln (frueher: 6.6, mitgebuendelt). Die
# echten .so-Dateien fuer 6.11 liegen jetzt in einem separaten Qt6.11-Sysroot (vermutlich aus
# KDE-Neon-apt-Paketen extrahiert, siehe neon-qt6-pyside6/apt-sandbox/) - siehe identischer
# Befund + Live-Verifikation in run-freecad-26.3.sh (dort ausfuehrlicher kommentiert).
# Python-PAKETE (.py/.pyi) kommen weiterhin aus der venv, nur die .so-Bibliotheken aus dem
# Sysroot.
VENV_DIR="/home/maxx/Dokumente/FreeCAD-Development/.venv"
NEON_QT_LIB="/home/maxx/Dokumente/FreeCAD-Development/neon-qt6-pyside6/root/usr/lib/x86_64-linux-gnu"
if [[ -d "$VENV_DIR" ]]; then
  # shellcheck disable=SC1091
  source "${VENV_DIR}/bin/activate"
  export VIRTUAL_ENV="${VENV_DIR}"
  export LD_LIBRARY_PATH="${NEON_QT_LIB}:/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
  export PYTHONNOUSERSITE=1

  # FCPROJECT-FIX (2026-09-26, Nutzer-Report "signalmanager.h: Datei oder Verzeichnis nicht
  # gefunden" beim Bauen von src/Gui/PythonWrapper.cpp): reicht NICHT, das obige
  # LD_LIBRARY_PATH zu setzen - FreeCadMacros.cmake's find_pip_package() liest Header/.so
  # direkt AUS dem venv-Package-Verzeichnis selbst (site-packages/PySide6/include bzw.
  # .../PySide6/*.so.*), nicht aus LD_LIBRARY_PATH. Seit der 6.6->6.11-Migration (siehe
  # Kommentar oben) fehlen dort include/ komplett und die .so-Dateien liegen nur noch im
  # Neon-Sysroot - deshalb hier selbstheilend per Symlink nachbilden (idempotent, ueberlebt
  # eine venv-Neuinstallation). Ergaenzend werden veraltete CMakeCache-Eintraege (z.B. noch
  # auf "...so.6.6" zeigend, CACHE-Variablen werden von find_pip_package() NICHT
  # ueberschrieben, wenn schon gesetzt) unten in Schritt 5 per "-U" erzwungen neu ermittelt.
  VENV_PYSIDE="${VENV_DIR}/lib/python3.12/site-packages/PySide6"
  NEON_QT_INCLUDE="/home/maxx/Dokumente/FreeCAD-Development/neon-qt6-pyside6/root/usr/include/PySide6"
  if [[ -d "$VENV_PYSIDE" && -d "$NEON_QT_INCLUDE" ]]; then
    ln -sfn "$NEON_QT_INCLUDE" "${VENV_PYSIDE}/include"
    for so in "${NEON_QT_LIB}"/libpyside6*.abi3.so.*; do
      [[ -e "$so" ]] && ln -sfn "$so" "${VENV_PYSIDE}/$(basename "$so")"
    done
  fi
else
  echo "WARNUNG: venv '${VENV_DIR}' nicht gefunden - CMake-Schritt 5 (PySide6/shiboken6-Check) wird vermutlich fehlschlagen."
fi

# WICHTIG (Vorfall 2026-09-04): dieses Skript setzt voraus, dass FC_SRC auf einem
# PLAIN-Branch steht, der ein sauberer Vorfahre von origin/main ist (git-apply-
# basierte Patches, kein eigener Commit-Verlauf) - sonst schlaegt der ff-only-
# Merge in Schritt 2 unverstaendlich fehl ("Vorspulen nicht moeglich"), ohne dass
# der eigentliche Grund (falscher Branch) in der Fehlermeldung auftaucht. Kam vor,
# weil parallel ein Solver-Experiment auf einem eigenen Branch
# (fcproject/assembly-solver-fix) direkt in diesem Checkout lief. Solche
# Experimente gehoeren seit der "strikten Trennung" nach
# assembly-solver-sandbox/ (eigener, unabhaengiger sparse-checkout) - siehe
# dortige SANDBOX_NOTES.md. Lieber hier laut abbrechen als den ff-only-Fehler
# unkommentiert durchschlagen zu lassen.
CURRENT_BRANCH="$(git branch --show-current)"
if [[ "$CURRENT_BRANCH" != "main" ]]; then
  echo "FEHLER: ${FC_SRC} steht auf Branch '${CURRENT_BRANCH}', nicht 'main'."
  echo "Dieses Skript erwartet einen Plain-Branch, der sauber auf origin/main"
  echo "vorgespult werden kann. Falls hier ein Solver-Experiment lief: nach"
  echo "assembly-solver-sandbox/ auslagern (siehe dortige SANDBOX_NOTES.md),"
  echo "dann 'git checkout main' und dieses Skript erneut starten."
  exit 1
fi

# CMakeUserPresets.json ist von FreeCADs eigenem .gitignore ausgeschlossen
# (Standard-CMake-Konvention) - kann also genauso unbemerkt verlorengehen wie
# die Patches. Aus der durablen Kopie hier wiederherstellen, falls noetig.
if [[ ! -f "${FC_SRC}/CMakeUserPresets.json" ]]; then
  echo "CMakeUserPresets.json fehlt - stelle aus patches/freecad-CMakeUserPresets.json wieder her."
  run cp "${PATCHES_DIR}/freecad-CMakeUserPresets.json" "${FC_SRC}/CMakeUserPresets.json"
fi

log "Start. Aktueller Stand: $(git log -1 --format='%h %cd %s' --date=short)"
echo "Parallelitaet: JOBS=${JOBS} (nproc=$(nproc), RAM=${MEM_GB:-?}GB) - via JOBS=<n> env var uebersteuerbar."

log "Schritt 1/7: eigene Feature- UND Umgebungs-Patches aus freecad-source entfernen"
# WICHTIG: auch die Umgebungs-Patches muessen hier raus, nicht nur die
# Feature-Patches - sonst blockiert der ff-only-Merge in Schritt 2, sobald
# Upstream eine dieser Dateien ebenfalls aendert ("lokale Aenderungen wuerden
# ueberschrieben"). Schritt 4 legt sie danach frisch wieder auf einen
# pristinen Baum.
for f in "${FEATURE_PATCHED_FILES[@]}" "${ENV_PATCHED_FILES[@]}"; do
  run git checkout -- "$f"
done

# Alles, was jetzt noch als lokale Aenderung dasteht, kennt dieses Skript
# nicht - lieber abbrechen als es stillschweigend zu verlieren. Bekannte,
# erwartete Eintraege werden ausgefiltert: die harmlosen Submodule (git zeigt
# sie je nach Inhalt mal als "M" mal als "??" an).
if [[ $DRY_RUN -eq 0 ]]; then
  KNOWN_DIRTY=("src/3rdParty/OndselSolver" "src/Mod/AddonManager")
  UNEXPECTED=""
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    is_known=0
    for f in "${KNOWN_DIRTY[@]}"; do
      if [[ "$line" == *"$f" ]]; then
        is_known=1
        break
      fi
    done
    [[ $is_known -eq 0 ]] && UNEXPECTED+="${line}"$'\n'
  done < <(git status --porcelain)
  if [[ -n "$UNEXPECTED" ]]; then
    echo "FEHLER: unerwartete lokale Aenderungen in ${FC_SRC}, breche ab:"
    printf '%s' "$UNEXPECTED"
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
run cmake --preset FC-dev -U "PySide6_*" -U "Shiboken6_*"
run cmake --build --preset FC-dev --parallel "$JOBS"

log "Vanilla-Build gruen. Schritt 6/7: eigene Feature-Patches wieder anwenden"
# WICHTIG (Vorfall 2026-09-05): anders als die ENV_PATCHES in Schritt 4 werden
# Feature-Patches NICHT bei einem Fehlschlag stillschweigend uebersprungen - das
# waere genau das "automatische Ueberspielen/Ignorieren", das dieses Skript laut
# eigenem Kopf-Kommentar bewusst vermeiden soll (ein Feature wie der FileDialog-
# Suchfilter soll nicht kommentarlos aus dem gebauten FreeCAD verschwinden). Vorher
# fehlte hier ein --check: ein nicht mehr passender Patch liess "git apply" (unter
# set -euo pipefail) erst NACH dem kompletten, zeitaufwaendigen Vanilla-Build in
# Schritt 5 hart abbrechen. Jetzt: vorher pruefen, bei Fehlschlag SOFORT mit klarer
# Meldung abbrechen, statt die Bauzeit zu verschwenden.
for p in "${FEATURE_PATCHES[@]}"; do
  echo "--- ${p} ---"
  if ! git apply --check "${PATCHES_DIR}/${p}" 2>/tmp/fcproject-patch-check-err.txt; then
    echo "FEHLER: ${p} passt nicht mehr auf den aktuellen Stand:"
    cat /tmp/fcproject-patch-check-err.txt
    echo "Patch manuell an den aktuellen Code anpassen (patches/README.md pruefen)," \
         "dann das Skript erneut starten."
    exit 1
  fi
  run git apply "${PATCHES_DIR}/${p}"
done

echo "Feature-Patches drauf, nochmal inkrementell bauen"
run cmake --build --preset FC-dev --parallel "$JOBS"

log "Schritt 7/7: installieren"
run cmake --install "${FC_SRC}/build"
# Nur *.py hier extra nach install/ kopieren - .cpp/.h werden bereits ueber
# "cmake --install" als Teil der kompilierten .so ausgeliefert, dort existiert
# gar kein passendes Zielverzeichnis (App/-Unterordner fehlt im install-Baum).
for f in "${FEATURE_PATCHED_FILES[@]}"; do
  [[ "$f" == *.py ]] || continue
  run cp "${FC_SRC}/${f}" "${FC_INSTALL}/${f#src/}"
done

log "Fertig. Neuer Stand: $(git log -1 --format='%h %cd %s' --date=short)"
echo "Log gespeichert unter: ${LOG_FILE}"
