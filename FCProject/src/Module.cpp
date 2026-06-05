#include <pybind11/pybind11.h>
#include "../include/InitGui.h"
#include <pybind11/detail/common.h>

namespace py = pybind11;

// Diese Funktion wird von Python beim "import FCProjectCpp" aufgerufen
PYBIND11_MODULE(FCProjectCore, m) {
    m.doc() = "FCProjectCpp Modul für FreeCAD";

    // Hier registrieren wir deine Klasse, damit Python sie nutzen kann
    py::class_<FCProject::InitGui>(m, "InitGui")
        .def(py::init<>())
   //     .def("initialize", &FCProject::InitGui::initialize)
   //     .def("activated", &FCProject::InitGui::activated)
        .def("getClassName", &FCProject::InitGui::getClassName);
}