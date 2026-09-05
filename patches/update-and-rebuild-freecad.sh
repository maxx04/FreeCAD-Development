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

# Reine Build-Umgebungs-Patches: muessen VOR dem ersten Konfigurieren/Bauen
# angewendet sein, sonst schlaegt der Build unabhaengig von Feature-Fixes fehl.
ENV_PATCHES=(
  "freecad-cmake-disable-tests.patch"
  "freecad-navigation-qbytearray-fix.patch"
  "freecad-propertyeditor-qstring-fix.patch"
)
# Dateien, die die obigen Umgebungs-Patches beruehren - werden in Schritt 1
# wie die Feature-Patches zurueckgesetzt (pristiner Baum fuer den ff-only-
# Merge) und in Schritt 4 frisch wieder angewendet.
ENV_PATCHED_FILES=(
  "CMakeLists.txt"
  "src/Gui/PreferencePages/DlgSettingsNavigation.cpp"
  "src/Mod/Start/Gui/GeneralSettingsWidget.cpp"
  "src/Gui/propertyeditor/PropertyEditor.cpp"
)

# Feature-/Bugfix-Patches: nur relevant fuer FCProjects eigenen Workflow,
# werden ERST nach einem gruenen Vanilla-Build wieder aufgelegt.
#
# WICHTIG (2026-09-05, Nutzerkorrektur - ersetzt die 2026-09-04-Regel "strikte
# Trennung, gar keine Assembly-Patches mehr hier"): jene Regel hatte zur Folge,
# dass JEDER Lauf dieses Skripts ein FreeCAD mit komplett VANILLA Assembly-Modul
# installierte - alle unten stehenden, bereits validierten (nicht-
# experimentellen) Assembly-Bugfixes gingen dabei automatisch verloren, ohne
# dass es auffiel (bestaetigt: JointObject.py der Installation war 0 Byte
# Unterschied zu sauberem main, obwohl die Fixes laengst dokumentiert waren -
# fuehrte zum "onDistanceChanged: Base::Quantity cannot be converted"-Vorfall).
# Automatische Anwendung dieser Patches hat vorher bereits mehrfach zuverlaessig
# funktioniert und ist wieder aktiv. NUR das aktiv laufende Experiment
# "Adressieren statt Kopieren" (freecad-assembly-addressing-utils.patch,
# freecad-assembly-link-subjoints-revert.patch) bleibt ausschliesslich in
# /home/maxx/Dokumente/FreeCAD-Development/assembly-solver-sandbox/patches/ und
# wird hier NICHT automatisch angewendet, solange es dort noch in aktiver
# Entwicklung ist.
#
# WICHTIG (Vorfall 2026-09-05, echter Kompilierfehler): freecad-assembly-
# jointobject.patch (grosser kumulativer Snapshot) ruft resolveJointReference()/
# ResolvedJointRef auf - die sind aber ERST durch freecad-assembly-addressing-
# utils.patch definiert (der oben genannte, bewusst ausgeschlossene aktive
# Sandbox-Patch). jointobject.patch ist textuell konfliktfrei anwendbar, aber
# NICHT ohne addressing-utils.patch kompilierbar - deshalb hier NICHT
# eingetragen. Stattdessen: freecad-assembly-quantity-signal-fix.patch, ein
# eigenstaendiger, aus jointobject.patch herausgeloester Mini-Fix (nur die
# valueChanged->textChanged-Signalverbindungen fuer die Joint-Distanz-/Winkel-
# Spinboxen, behebt GENAU den obigen "Base::Quantity cannot be converted"-Bug),
# ohne jede Abhaengigkeit zu addressing-utils.
# WICHTIG (Vorfall 2026-09-05, zweiter Fund): App::Link hat keine eigene "Shape"-Property
# im normalen Sinn - sie wird on-demand aus LinkedObject berechnet
# (LinkBaseExtension::extensionGetPropertyByName() schliesst "Shape" bewusst vom
# generischen Property-Forwarding aus, siehe src/App/Link.cpp). Ist LinkedObject waehrend
# der Lade-Kaskade einer Mehrdatei-Baugruppe noch nicht aufgeloest, fehlt das Attribut
# kurzzeitig komplett -> "'App.DocumentObject' object has no attribute 'Shape'" in
# UtilsAssembly.findPlacement(), reproduzierbar live per Python-Konsole verifiziert
# (selbstheilend: Sekunden spaeter, sobald alles geladen ist, wieder normal aufloesbar).
# freecad-assembly-link-shape-race-fix.patch behandelt das defensiv wie einen nicht
# aufloesbaren Sub-Element-Fall (Identity-Placement statt Absturz).
FEATURE_PATCHES=(
  "freecad-filedialog-search-filter.patch"
  "freecad-app-getplacementof-partdesign-feature.patch"
  "freecad-assembly-grounded-joint-nested-flex.patch"
  "freecad-assembly-quantity-signal-fix.patch"
  "freecad-assembly-viewprovider-null-crash.patch"
  "freecad-assembly-link-shape-race-fix.patch"
)
# WICHTIG: hier ALLE von den FEATURE_PATCHES beruehrten Dateien eintragen,
# nicht nur einen Teil - sonst faellt eine vergessene Datei beim Resume nach
# einem Abbruch faelschlich als "unerwartete Aenderung" durch Schritt 1 und muss
# jedes Mal von Hand bereinigt werden (siehe Vorfall 2026-08-18/2026-08-23).
FEATURE_PATCHED_FILES=(
  "src/Gui/FileDialog.cpp"
  "src/Gui/FileDialog.h"
  "src/App/DocumentObject.cpp"
  "src/App/Link.cpp"
  "src/Mod/Assembly/App/AssemblyLink.cpp"
  "src/Mod/Assembly/App/AssemblyLink.h"
  "src/Mod/Assembly/JointObject.py"
  "src/Mod/Assembly/Gui/ViewProviderAssembly.cpp"
  "src/Mod/Assembly/UtilsAssembly.py"
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
run cmake --preset FC-dev
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
