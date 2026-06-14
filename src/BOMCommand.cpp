#include "../include/BOMCommand.h"
#include <iostream>

namespace FCProject {

auto BOMExportCommand::activated() -> bool {
    std::cout << "BOMExportCommand placeholder activated" << std::endl;
    return true;
}

auto BOMExportCommand::isActive() const -> bool {
    return true;
}

} // namespace FCProject
