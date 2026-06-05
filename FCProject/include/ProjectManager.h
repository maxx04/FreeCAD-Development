#pragma once

#include <string>

namespace FCProject {

class ProjectManagerCommand {
public:
    ProjectManagerCommand();
    std::string getDefaultProjectData(const std::string& projectName) const;
    bool initializeProject(const std::string& baseDir, const std::string& projectName, std::string& outMessage);
    bool isActive() const;

private:
    std::string scriptVersion;
};

} // namespace FCProject
