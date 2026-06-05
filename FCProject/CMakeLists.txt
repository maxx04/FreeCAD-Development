cmake_minimum_required(VERSION 3.16)
project(FCProject LANGUAGES CXX, Python)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

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
add_library(FCProjectCore SHARED 
    src/ProjectManager.cpp
    src/EntityCreator.cpp
    src/AssemblyCreator.cpp
    src/AssemblyPatternCommand.cpp
    src/AssemblyPatternCreator.cpp
    src/BOMCommand.cpp
    src/BOMManager.cpp
    src/Commands.cpp
    src/GeometryCreator.cpp
    src/InitGui.cpp
    src/MaterialUtils.cpp
    src/PartCreator.cpp
    src/PurchasedPartCreator.cpp
    src/RAWCreator.cpp
    src/TaskPanel.cpp
    src/Utils.cpp
    src/version.cpp
    src/Module.cpp
)

# 4. Inklusionspfade & Features
# FreeCAD_INCLUDE_DIRS wird durch find_package automatisch befüllt!
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
)

# Suche nach pybind11
find_package(pybind11 REQUIRED)

# Füge Module.cpp zu deinen Quellen hinzu
# Statt nur add_library(...)
if(NOT TARGET FCProject)
    add_library(FCProject SHARED 
        Init.py
        InitGui.py
    )
endif()


# Verbinde die Bibliothek mit PyBind11
target_link_libraries(FCProjectCore PRIVATE pybind11::module)

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
install(FILES 
    Init.py 
    InitGui.py 
    DESTINATION "${MY_MOD_DESTINATION}"
)

