#pragma once

#include <string>
#include "FreeCADTypes.h"

namespace FCProject {

class EntityCreator {
public:
    EntityCreator(const std::string& projectName, const std::string& projectDir);
    std::string getNextAvailableNumber() const;
    std::string createPdmDocument(const std::string& compType, const std::string& compNum, PropertyMap& userProperties);

private:
    std::string projectName;
    std::string projectDir;
    PropertyMap configData;
    PropertyMap loadConfig() const;
};

} // namespace FCProject
