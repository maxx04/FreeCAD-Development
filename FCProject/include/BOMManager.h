#pragma once

#include <filesystem>
#include <string>
#include <vector>
#include "FreeCADTypes.h"

namespace FCProject {

class BOMManager {
public:
    BOMManager();
    std::vector<std::vector<std::string>> generateStructuralBom(Element* rootAssembly);
    std::filesystem::path exportToCsv(const std::filesystem::path& targetDir, Element* rootAssembly);
    bool exportToSpreadsheet(const std::filesystem::path& targetDir, Element* rootAssembly);
};

} // namespace FCProject
