#include <pybind11/pybind11.h>
#include "Utils_HW.h"

namespace py = pybind11;

PYBIND11_MODULE(FCProjectCore, m) {
    m.doc() = "FCProject C++ Kern-Funktionen";

    py::class_<Utils_HW>(m, "Utils_HW")
        .def(py::init<>())
        .def("sayHello", &Utils_HW::sayHello);
}