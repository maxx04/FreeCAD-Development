#pragma once

#include <string>
#include "FreeCADTypes.h"

namespace FCProject {

class PurchasedPartCreator {
public:
    bool create(const std::string& filePath, const std::string& baseName, const std::string& trailingName, const PropertyMap& config, const PropertyMap& properties);
};

} // namespace FCProject
