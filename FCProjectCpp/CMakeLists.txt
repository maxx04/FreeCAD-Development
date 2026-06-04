cmake_minimum_required(VERSION 3.16)
project(FCProjectCpp LANGUAGES CXX)

# --- WICHTIG: FreeCAD-Paket finden ---
# Dies setzt Variablen wie FreeCAD_INCLUDE_DIRS und FreeCAD_LIBRARIES
# Wir müssen CMake sagen, wo FreeCAD gebaut wurde
find_package(FreeCAD REQUIRED PATHS "/home/maxx/freecad/freecad-source/cmake")

# --- Bibliothek definieren ---
add_library(FCProjectCpp SHARED 
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
)

# --- Inklusionspfade und Features ---
target_include_directories(FCProjectCpp PUBLIC 
    include 
    ${FreeCAD_INCLUDE_DIRS}
)
target_compile_features(FCProjectCpp PUBLIC cxx_std_17)

# --- Abhängigkeiten verlinken ---
# Das ist der entscheidende Schritt, damit FreeCAD dein Modul versteht
target_link_libraries(FCProjectCpp 
    PUBLIC 
    FreeCADApp 
    FreeCADGui 
    ${FreeCAD_LIBRARIES}
    Qt6::Core Qt6::Gui Qt6::Widgets # Falls du Qt6 nutzt
)

# --- Modul-Installation ---
# Damit das Modul im 'Mod'-Ordner von FreeCAD landet
install(TARGETS FCProjectCpp DESTINATION Mod/FCProjectCpp)