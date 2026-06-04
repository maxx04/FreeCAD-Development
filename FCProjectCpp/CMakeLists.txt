cmake_minimum_required(VERSION 3.16)
project(FCProjectCpp LANGUAGES CXX)

add_library(FCProjectCpp
    src/BOMManager.cpp
    src/AssemblyPatternCommand.cpp
    src/Utils.cpp
    src/PurchasedPartCreator.cpp
    src/Commands.cpp
    src/AssemblyCreator.cpp
    src/ProjectManager.cpp
    src/InitGui.cpp
    src/GeometryCreator.cpp
    src/version.cpp
    src/MaterialUtils.cpp
    src/AssemblyPatternCreator.cpp
    src/RAWCreator.cpp
    src/EntityCreator.cpp
    src/PartCreator.cpp
    src/BOMCommand.cpp
    src/TaskPanel.cpp
)

target_include_directories(FCProjectCpp PUBLIC include)
