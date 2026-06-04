#include "../include/ProjectManager.h"
#include <filesystem>
#include <fstream>

namespace FCProject {

ProjectManagerCommand::ProjectManagerCommand() : scriptVersion("1.1") {}

std::string ProjectManagerCommand::getDefaultProjectData(const std::string& projectName) const {
    std::string json;
    json += "{\n";
    json += "  \"Configuration\": {\n";
    json += "    \"Version\": \"" + scriptVersion + "\",\n";
    json += "    \"CreatedBy\": \"unknown\",\n";
    json += "    \"CreationDate\": \"1970-01-01\"\n";
    json += "  },\n";
    json += "  \"ProjectMetadata\": {\n";
    json += "    \"ProjectName\": \"" + projectName + "\",\n";
    json += "    \"FreeCADVersion\": \"1.1\"\n";
    json += "  },\n";
    json += "  \"Entities\": {\n";
    json += "    \"P\": { \"Label\": \"P - Einzelteil (Part)\", \"FreeCADType\": \"PartDesign::Body\", \"Prefix\": \"BODY\", \"Properties\": {} },\n";
    json += "    \"A\": { \"Label\": \"A - Baugruppe (Assembly)\", \"FreeCADType\": \"Assembly::AssemblyObject\", \"Prefix\": \"ASM\", \"Properties\": {} },\n";
    json += "    \"R\": { \"Label\": \"R - Halbzeug (Profile/Rohmaterial)\", \"FreeCADType\": \"PartDesign::Body\", \"Prefix\": \"RAW\", \"Properties\": {} },\n";
    json += "    \"G\": { \"Label\": \"G - Geometrie (Skelett/Referenz)\", \"FreeCADType\": \"App::Part\", \"Prefix\": \"SKEL\", \"Properties\": {} },\n";
    json += "    \"B\": { \"Label\": \"B - Kaufteil (Purchased Component)\", \"FreeCADType\": \"App::Part\", \"Prefix\": \"PUR\", \"Properties\": {} }\n";
    json += "  }\n";
    json += "}\n";
    return json;
}

bool ProjectManagerCommand::initializeProject(const std::string& baseDir, const std::string& projectName, std::string& outMessage) {
    std::filesystem::path basePath(baseDir);
    if (!std::filesystem::exists(basePath)) {
        outMessage = "Arbeitsverzeichnis existiert nicht.";
        return false;
    }
    std::filesystem::path projectFolder = basePath / ("PROJ_" + projectName);
    std::filesystem::create_directories(projectFolder);
    std::filesystem::path jsonPath = projectFolder / ("PROJ_" + projectName + ".json");
    std::ofstream outFile(jsonPath);
    if (!outFile) {
        outMessage = "Konnte Projektdatei nicht schreiben.";
        return false;
    }
    outFile << getDefaultProjectData(projectName);
    outFile.close();
    outMessage = "Projekt initialisiert: " + projectFolder.string();
    return true;
}

bool ProjectManagerCommand::isActive() const {
    return true;
}

} // namespace FCProject
