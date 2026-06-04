#include "../include/PurchasedPartCreator.h"
#include <fstream>

namespace FCProject {

bool PurchasedPartCreator::create(const std::string& filePath, const std::string& baseName, const std::string& trailingName, const PropertyMap& config, const PropertyMap& properties) {
    std::ofstream out(filePath);
    if (!out) return false;
    out << "# FCProject PurchasedPartCreator placeholder for " << trailingName << "\n";
    out << "ArticleID=" << properties.at("__PureArticleID__") << "\n";
    return true;
}

} // namespace FCProject
