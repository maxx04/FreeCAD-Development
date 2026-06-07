#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include "BOMManager.h"
#include "Utils_HW.h"

namespace py = pybind11;
using namespace FCProject;

PYBIND11_MODULE(FCProjectCore, m) {
    m.doc() = "FCProject C++ Core BOM Manager";

    // Kette ohne Semikolons in der Mitte!
    py::class_<BOMManager>(m, "BOMManager")
       .def(py::init<>())
       .def(py::init<std::string&>(), py::arg("root_name"))
       .def("generate_structural_bom", &BOMManager::generateStructuralBom)
       .def("export_to_csv", &BOMManager::exportToCsv)
       .def("export_to_spreadsheet", &BOMManager::exportToSpreadsheet); 

    py::class_<Utils_HW>(m, "Utils_HW")
       .def(py::init<>())
       .def("sayHello", static_cast<std::string (Utils_HW::*)(const std::string&)>(&Utils_HW::sayHello));
}