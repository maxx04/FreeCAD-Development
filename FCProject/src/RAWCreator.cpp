#include "../include/RAWCreator.h"
#include <fstream>

namespace FCProject {

bool RAWCreator::create(const std::string& filePath, const std::string& baseName, const std::string& trailingName, const PropertyMap& config, const PropertyMap& properties) {
    std::ofstream out(filePath);
    if (!out) return false;
    out << "# FCProject RAWCreator placeholder for " << trailingName << "\n";
    out << "ArticleID=" << properties.at("__PureArticleID__") << "\n";
    out << "Length=" << properties.at("Length") << "\n";
    return true;
}

} // namespace FCProject
