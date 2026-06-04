#include <pybind11/pybind11.h>
#include "../include/InitGui.h" // Dein Header

namespace py = pybind11;

PYBIND11_MODULE(FCProjectCpp, m) {
    // Hier exportieren wir deine Klasse
    py::class_<FCProject::InitGui>(m, "InitGui")
        .def(py::init<>())
        .def("initialize", &FCProject::InitGui::initialize)
        .def("activated", &FCProject::InitGui::activated);
}