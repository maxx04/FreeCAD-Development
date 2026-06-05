#include "../include/AssemblyPatternCommand.h"
#include <iostream>

namespace FCProject {

void AssemblyPatternCommand::activated() {
    std::cout << "AssemblyPatternCommand activated placeholder" << std::endl;
}

bool AssemblyPatternCommand::isActive() const {
    return true;
}

} // namespace FCProject
