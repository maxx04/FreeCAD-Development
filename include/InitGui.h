#pragma once

#include <string>

namespace FCProject {

class InitGui {
public:
    auto initialize() -> void;
    auto activated() -> void;
    auto getClassName() const -> std::string;
};

} // namespace FCProject
