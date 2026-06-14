#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include "AssemblyPatternCreator.h"
#include "BOMManager.h"
#include "Utils_HW.h"

namespace py = pybind11;
using namespace FCProject;

PYBIND11_MODULE(FCProjectCore, m) {
    m.doc() = "FCProject C++ Core BOM Manager";

    // Kette ohne Semikolons in der Mitte!
    py::class_<BOMManager>(m, "BOMManager")
       .def(py::init<>())
       .def(py::init<const std::string&>(), py::arg("root_name"))
       .def("generate_structural_bom", &BOMManager::generateStructuralBom)
       .def("export_to_csv", &BOMManager::exportToCsv)
       .def("export_to_spreadsheet", &BOMManager::exportToSpreadsheet); 

    py::class_<Utils_HW>(m, "Utils_HW")
       .def(py::init<>())
       .def("sayHello", static_cast<std::string (Utils_HW::*)(const std::string&)>(&Utils_HW::sayHello));

    py::class_<AssemblyPatternCreator>(m, "AssemblyPatternCreator")
       .def(py::init<const std::string&>(), py::arg("assembly_name"))
       .def("create_pattern",
            static_cast<void (AssemblyPatternCreator::*)(const std::string&, int, double, const std::string&)>(
                &AssemblyPatternCreator::createPattern),
            py::arg("source_element_name"), py::arg("count") = 3, py::arg("distance") = 600.0,
            py::arg("direction") = "X-Achse")
       .def("create_circular_pattern",
            static_cast<void (AssemblyPatternCreator::*)(const std::string&, int, double)>(
                &AssemblyPatternCreator::createCircularPattern),
            py::arg("source_element_name"), py::arg("count") = 3, py::arg("radius") = 50.0);
}