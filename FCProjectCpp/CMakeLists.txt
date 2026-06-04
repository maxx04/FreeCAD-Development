cmake_minimum_required(VERSION 3.16)
project(FCProjectCpp LANGUAGES CXX)

add_library(FCProjectCpp
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

target_include_directories(FCProjectCpp PUBLIC include)
target_compile_features(FCProjectCpp PUBLIC cxx_std_17)
