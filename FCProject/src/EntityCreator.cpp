#include "../include/EntityCreator.h"
#include "PartCreator.h"
#include "AssemblyCreator.h"
#include "GeometryCreator.h"
#include "RAWCreator.h"
#include "PurchasedPartCreator.h"
#include <filesystem>
#include <fstream>
#include <regex>

namespace FCProject {

EntityCreator::EntityCreator(const std::string& projectName, const std::string& projectDir)
    : projectName(projectName.empty() ? "PROJ" : projectName),
      projectDir(projectDir.empty() ? std::filesystem::current_path().string() : projectDir),
      configData(loadConfig()) {
}

PropertyMap EntityCreator::loadConfig() const {
    PropertyMap config;
    std::filesystem::path jsonPath = std::filesystem::path(projectDir) / (std::filesystem::path(projectDir).filename().string() + ".json");
    if (!std::filesystem::exists(jsonPath)) return config;
    std::ifstream in(jsonPath);
    if (!in) return config;
    // TODO: JSON parsing is not implemented in this stub.
    return config;
}

std::string EntityCreator::getNextAvailableNumber() const {
    int highestNum = 0;
    std::regex pattern("^" + std::regex_replace(projectName, std::regex("([\\^\\$\\.\\|\\?\\*\\+\\(\\)\\[\\]\\{\\}])"), "\\\\$1") + "_(\\d{3})_[APRGB]");
    for (auto& entry : std::filesystem::directory_iterator(projectDir)) {
        if (!entry.is_regular_file()) continue;
        std::smatch match;
        std::string filename = entry.path().filename().string();
        if (std::regex_search(filename, match, pattern)) {
            int num = std::stoi(match[1].str());
            if (num > highestNum) highestNum = num;
        }
    }
    return (highestNum + 1 < 10 ? "00" : highestNum + 1 < 100 ? "0" : "") + std::to_string(highestNum + 1);
}

std::string EntityCreator::createPdmDocument(const std::string& compType, const std::string& compNum, PropertyMap& userProperties) {
    std::string basePdmId = projectName + "_" + compNum + "_" + compType + "_";
    std::string pdmBaseName = projectName + "_" + compNum + "_" + compType;
    std::string filenameWithTrailing = pdmBaseName + "_";
    std::filesystem::path outputPath = std::filesystem::path(projectDir) / (filenameWithTrailing + ".FCStd");

    userProperties["__PureArticleID__"] = basePdmId;

    std::string type = compType;
    if (type == "P") {
        PartCreator creator;
        creator.create(outputPath.string(), pdmBaseName, filenameWithTrailing, configData, userProperties);
    } else if (type == "A") {
        AssemblyCreator creator;
        creator.create(outputPath.string(), pdmBaseName, filenameWithTrailing, configData, userProperties);
    } else if (type == "G") {
        GeometryCreator creator;
        creator.create(outputPath.string(), pdmBaseName, filenameWithTrailing, configData, userProperties);
    } else if (type == "R") {
        RAWCreator creator;
        creator.create(outputPath.string(), pdmBaseName, filenameWithTrailing, configData, userProperties);
    } else if (type == "B") {
        PurchasedPartCreator creator;
        creator.create(outputPath.string(), pdmBaseName, filenameWithTrailing, configData, userProperties);
    } else {
        throw std::runtime_error("Unbekannter PDM-Komponenten-Typ: " + compType);
    }

    return filenameWithTrailing;
}

} // namespace FCProject
