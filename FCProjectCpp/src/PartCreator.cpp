#include "../include/PartCreator.h"
#include <fstream>
#include <iostream>

namespace FCProject {

bool PartCreator::create(const std::string& filePath, const std::string& baseName, const std::string& trailingName, const PropertyMap& config, const PropertyMap& properties) {
    std::ofstream out(filePath);
    if (!out) return false;
    out << "# FCProject PartCreator placeholder for " << trailingName << "\n";
    out << "ArticleID=" << properties.at("__PureArticleID__") << "\n";
    return true;
}

} // namespace FCProject
