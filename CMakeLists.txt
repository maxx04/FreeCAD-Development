cmake_minimum_required(VERSION 3.16)
project(FCProject)
#project(FCProject LANGUAGES CXX Python)

set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 1. Compile Commands immer aktivieren
set(CMAKE_EXPORT_COMPILE_COMMANDS ON CACHE BOOL "Export compile commands" FORCE)

# 2. Debug als Standard-Build-Typ setzen, aber nur, wenn noch nichts definiert ist
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Debug CACHE STRING "Choose the type of build" FORCE)

endif()




# --- Qt6 suchen ---
find_package(Qt6 REQUIRED COMPONENTS Core Gui Widgets)

# --- FreeCAD Include Pfade manuell (da wir keine Config-Datei haben) ---
# --- Pfade für FreeCAD (überschreibbar per CMakePresets.json je Rechner) ---
set(FC_SOURCE_DIR "/home/maxx/freecad/freecad-source" CACHE PATH "FreeCAD source checkout (headers)")
set(FC_LIB_DIR "/home/maxx/freecad/install/lib" CACHE PATH "Directory containing FreeCAD's shared libraries (Spreadsheet.so, libFreeCADApp.so, ...)")

include_directories(
    "${FC_SOURCE_DIR}/src"                # Hier findet er <Gui/Application.h>
    "${FC_SOURCE_DIR}/src/App"
    "${FC_SOURCE_DIR}/src/Gui"
    "${FC_SOURCE_DIR}/src/3rdParty/FastSignals/libfastsignals/include"
    "/usr/include/pybind11"  # Pfad zu pybind11-Headern, falls nötig
    # Pfad für PyCXX hinzufügen (ersetze den Pfad durch das, was 'find' dir ausgegeben hat)
    "${FC_SOURCE_DIR}/src/3rdParty/PyCXX"
)

# WICHTIG: Das hier verhindert den 'slots' Fehler in FastSignals
add_definitions(-DQT_NO_KEYWORDS)
# --- Bibliotheken ---
# Hier fügen wir die FreeCAD-Bibliotheken hinzu, sofern sie existieren
link_directories("${FC_LIB_DIR}")

# 3. Bibliothek definieren (nur einmal add_library!)
# Sammle C/C++-Quellen aus src/ (keine Python-Dateien in den C++-Quellen!)
file(GLOB FCPROJECT_SOURCES CONFIGURE_DEPENDS
    "${CMAKE_CURRENT_SOURCE_DIR}/src/*.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/*.cxx"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/*.cc"
)

if(NOT FCPROJECT_SOURCES)
    message(FATAL_ERROR "No C/C++ source files found in ${CMAKE_CURRENT_SOURCE_DIR}/src")
endif()

add_library(FCProjectCore SHARED ${FCPROJECT_SOURCES})
    # Das erzwingt das Makro DEBUG auf C++ Ebene, wenn CONFIG auf Debug steht
target_compile_definitions(FCProjectCore PRIVATE  $<$<CONFIG:Debug>:DEBUG> $<$<CONFIG:Debug>:FC_DEBUG>)

# RPATH setzen, damit zur Laufzeit z.B. Spreadsheet.so im FreeCAD-Lib-Verzeichnis gefunden wird
set_target_properties(FCProjectCore PROPERTIES
    BUILD_RPATH "${FC_LIB_DIR}"
    INSTALL_RPATH "${FC_LIB_DIR}"
)

# 4. Inklusionspfade & Features
# FreeCAD_INCLUDE_DIRS wird durch find_package automatisch befüllt!
find_package(pybind11 REQUIRED)
find_package(fmt REQUIRED) # für um beide Versionen benutzen 1.1.1 und 1.2

target_include_directories(FCProjectCore PUBLIC
    include
    ${FreeCAD_INCLUDE_DIRS}
)
target_compile_features(FCProjectCore PUBLIC cxx_std_20)

# 5. Linken
# Die Bibliotheken FreeCADApp und FreeCADGui sind Teil von FreeCAD_LIBRARIES
target_link_libraries(FCProjectCore
    PRIVATE
    fmt::fmt    # Bindet die fmt-Bibliothek direkt an dein Addon
    "${FC_LIB_DIR}/Spreadsheet.so" # Für Spreadsheet::Sheet (BOM-Export als Tabelle)
    PUBLIC
    ${FreeCAD_LIBRARIES}
    Qt6::Core Qt6::Gui Qt6::Widgets
    ${Python3_LIBRARIES}
    pybind11::module
)

# Python-Dateien werden nicht als CMake-Quellen gebaut.
# Sie werden später über install() in das Modulverzeichnis kopiert.
# Wenn du ein natives Python-Extension-Modul benötigst, füge hier C++-Quellen hinzu.

# WICHTIG: Das lib-Präfix entfernen, damit Python die Datei als "FCProject" erkennt
set_target_properties(FCProjectCore PROPERTIES PREFIX "")

# FC_MOD_DIR kann direkt per Preset gesetzt werden (Nutzerprofil-Ordnername
# unterscheidet sich je FreeCAD-Version/Rechner, z.B. v1-2 vs. v26-3).
# Ohne Preset-Vorgabe wird anhand CMAKE_PRES_DEV ein Fallback gewählt.
set(FC_MOD_DIR "" CACHE PATH "FreeCAD Mod-Verzeichnis, in das installiert wird")

if(NOT FC_MOD_DIR)
    if(NOT CMAKE_PRES_DEV)
        set(FC_MOD_DIR "/home/maxx/.local/share/FreeCAD/v1-1/Mod/FCProject")
        message(STATUS "Post-Build: Target für FreeCAD 1.1.1.")
    else()
        set(FC_MOD_DIR "/home/maxx/.local/share/FreeCAD/v1-2/Mod/FCProject")
        message(STATUS "Post-Build: Target für FreeCAD dev.")
    endif()
else()
    message(STATUS "Post-Build: Target ${FC_MOD_DIR} (aus Preset).")
endif()

# 6. Installation
# Installiere die kompilierte Bibliothek (.so)
install(TARGETS FCProjectCore
    LIBRARY DESTINATION "${FC_MOD_DIR}"
    RUNTIME DESTINATION "${FC_MOD_DIR}"
)

# Kopiere die Python-Dateien mit in das Installationsverzeichnis

# Kopiert das gesamte Verzeichnis "resources" nach:
# ~/.local/share/FreeCAD/v1-2/Mod/FCProject/resources/

install(DIRECTORY resources/icons/ 
            DESTINATION "${FC_MOD_DIR}/resources/icons"

)

install(DIRECTORY python/
        DESTINATION "${FC_MOD_DIR}"
        PATTERN "__pycache__" EXCLUDE
)

# Startskript nach ~/freecad/ installieren (PROGRAMS setzt automatisch +x)
install(PROGRAMS resources/run-freecad-1.2.sh
    DESTINATION "/home/maxx/freecad"
)

# Desktop-Eintrag nach ~/.local/share/applications/ installieren
install(FILES resources/freecaad.desktop
    DESTINATION "/home/maxx/.local/share/applications"
    RENAME "freecad-1-2.desktop"
)
