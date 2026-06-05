#pragma once

#include <string>
#include "EntityCreator.h"

namespace FCProject {

class TaskPanel {
public:
    TaskPanel();
    void show();

private:
    std::string projectName;
    std::string projectDir;
    void buildUI();
    void onCreateClicked();
    void onExportBomClicked();
    std::pair<std::string, std::string> getProjectContext() const;
    bool loadConfig();
};

} // namespace FCProject
