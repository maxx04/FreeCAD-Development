#pragma once

#include <string>
#include "AssemblyPatternCreator.h"

namespace FCProject {

class AssemblyPatternCommand {
public:
    void activated();
    bool isActive() const;
private:
    AssemblyPatternCreator* creator{nullptr};
};

} // namespace FCProject
