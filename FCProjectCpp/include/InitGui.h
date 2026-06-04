#pragma once

#include <string>

namespace FCProject {

class InitGui {
public:
    void initialize();
    void activated();
    std::string getClassName() const;
};

} // namespace FCProject
