#pragma once

#include <string>

namespace FCProject {

class BOMExportCommand {
public:
    auto activated() -> bool;
    auto isActive() const -> bool;
};

} // namespace FCProject
