cmake_minimum_required(VERSION 3.16)
project(FCProject)
#project(FCProject LANGUAGES CXX Python)
set(CMAKE_CXX_STANDARD 20)
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
# --- Pfade für FreeCAD ---
set(FC_SOURCE_DIR "/home/maxx/freecad/freecad-source")

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
link_directories("/home/maxx/freecad/install/lib")

# Manuelle Definition statt find_package
set(FreeCAD_SOURCE_DIR "/home/maxx/freecad/freecad-source")
include_directories("${FreeCAD_SOURCE_DIR}/src" "${FreeCAD_SOURCE_DIR}/src/App" "${FreeCAD_SOURCE_DIR}/src/Gui")

# Wir definieren hier die Basis-Bibliotheken, die du brauchst
# Wenn der Linker später meckert, müssen wir hier noch Pfade ergänzen
link_directories("/home/maxx/freecad/install/lib")

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
target_compile_definitions(FCProjectCore PRIVATE  $<$<CONFIG:Debug>:DEBUG> )

# 4. Inklusionspfade & Features
# FreeCAD_INCLUDE_DIRS wird durch find_package automatisch befüllt!
find_package(pybind11 REQUIRED)

target_include_directories(FCProjectCore PUBLIC
    include
    ${FreeCAD_INCLUDE_DIRS}
)
target_compile_features(FCProjectCore PUBLIC cxx_std_20)

# 5. Linken
# Die Bibliotheken FreeCADApp und FreeCADGui sind Teil von FreeCAD_LIBRARIES
target_link_libraries(FCProjectCore
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

# 6. Installation
# --- Modul-Installation ---
# Wir installieren in deinen lokalen FreeCAD-Installationsordner
# Das ist sauberer und benötigt kein sudo!
# Installiere direkt in das neue User-Modul-Verzeichnis
set(MY_MOD_DESTINATION "/home/maxx/.local/share/FreeCAD/v1-2/Mod/FCProject")

# Installiere die kompilierte Bibliothek (.so)
install(TARGETS FCProjectCore
    LIBRARY DESTINATION "${MY_MOD_DESTINATION}"
    RUNTIME DESTINATION "${MY_MOD_DESTINATION}"
)


# Kopiere die Python-Dateien mit in das Installationsverzeichnis

# Kopiert das gesamte Verzeichnis "resources" nach:
# ~/.local/share/FreeCAD/v1-2/Mod/FCProject/resources/

install(DIRECTORY resources/icons/ 
        DESTINATION "${MY_MOD_DESTINATION}/resources/icons"
)

install(DIRECTORY python/ 
        DESTINATION "${MY_MOD_DESTINATION}"
)


