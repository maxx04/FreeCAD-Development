#include "../include/BOMCommand.h"
#include <iostream>

namespace FCProject {

bool BOMExportCommand::activated() {
    std::cout << "BOMExportCommand placeholder activated" << std::endl;
    return true;
}

bool BOMExportCommand::isActive() const {
    return true;
}

} // namespace FCProject
