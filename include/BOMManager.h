#pragma once

#include <filesystem>
#include <string>
#include <vector>
#include <App/DocumentObject.h>
#include "FreeCADTypes.h"

namespace FCProject {

class BOMManager {

private:
    Element* rootAssembly{nullptr};

public:
    BOMManager() = default;
    
    BOMManager(const std::string& root_name);

    auto generateStructuralBom() -> std::vector<std::vector<std::string>>;

    auto exportToCsv(const std::string& targetDir) -> bool;

    auto exportToSpreadsheet(const std::string& targetDir) -> bool;

    auto convertToElement(App::DocumentObject* obj, std::map<App::DocumentObject*, Element*>& cache) -> Element*;

};

} // namespace FCProject
