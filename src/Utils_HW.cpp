#include "Utils_HW.h"

Utils_HW::Utils_HW() {}

auto Utils_HW::sayHello(const std::string& name) -> std::string {
    return "Hello " + name + " from C++!";
}