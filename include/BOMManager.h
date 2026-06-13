#pragma once

#include <filesystem>
#include <string>
#include <vector>
#include <App/DocumentObject.h>
#include "FreeCADTypes.h"

namespace FCProject {

class BOMManager {

private:
    App::DocumentObject* rootAssembly{nullptr};

public:
    BOMManager() = default;
    
    BOMManager(const std::string& root_name);

    auto generateStructuralBom() -> std::vector<std::vector<std::string>>;

    auto exportToCsv(const std::string& targetDir) -> bool;

    auto exportToSpreadsheet(const std::string& targetDir) -> bool;

    auto GetOriginalObject(App::DocumentObject *obj) -> App::DocumentObject*;

};

} // namespace FCProject
