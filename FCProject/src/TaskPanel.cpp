#include "../include/TaskPanel.h"
#include <filesystem>
#include <iostream>

namespace FCProject {

TaskPanel::TaskPanel() {
    auto [name, dir] = getProjectContext();
    projectName = name;
    projectDir = dir;
}

void TaskPanel::show() {
    buildUI();
}

void TaskPanel::buildUI() {
    std::cout << "TaskPanel placeholder for project " << projectName << std::endl;
}

void TaskPanel::onCreateClicked() {
}

void TaskPanel::onExportBomClicked() {
}

std::pair<std::string, std::string> TaskPanel::getProjectContext() const {
    return {projectName.empty() ? "PROJ" : projectName, projectDir.empty() ? std::filesystem::current_path().string() : projectDir};
}

bool TaskPanel::loadConfig() {
    return false;
}

} // namespace FCProject
