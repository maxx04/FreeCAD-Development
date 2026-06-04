#include "../include/BOMManager.h"
#include "Utils.h"
#include <fstream>

namespace FCProject {

BOMManager::BOMManager() = default;

std::vector<std::vector<std::string>> BOMManager::generateStructuralBom(Element* rootAssembly) {
    std::vector<std::vector<std::string>> bomList;
    auto tree = getAssemblyTree(rootAssembly);
    for (auto& row : tree) {
        Element* obj;
        int depth;
        std::string artikelId;
        std::vector<int> indexPath;
        std::tie(obj, depth, artikelId, indexPath) = row;
        if (!obj || artikelId.empty() || artikelId == "None") continue;

        std::map<std::string, std::string> pdmInfo = extractPdmData(obj);
        std::string structureIndex;
        for (size_t i = 0; i < indexPath.size(); ++i) {
            if (i) structureIndex += "-";
            structureIndex += std::to_string(indexPath[i]);
        }
        bomList.push_back({structureIndex, pdmInfo["ArticleID"], pdmInfo["Bezeichnung"], pdmInfo["Material"], pdmInfo["Rohling"], std::to_string(std::stod(pdmInfo["Preis"])), "1"});
    }
    return bomList;
}

std::filesystem::path BOMManager::exportToCsv(const std::filesystem::path& targetDir, Element* rootAssembly) {
    auto rows = generateStructuralBom(rootAssembly);
    if (rows.empty()) return {};
    std::filesystem::path csvPath = targetDir / ("BOM_Struktur_" + (rootAssembly ? rootAssembly->name : "document") + ".csv");
    std::ofstream out(csvPath);
    if (!out) return {};
    out << "Position (Struktur-Index),Artikel-ID,Benennung,Werkstoff,Rohling/Halbzeug,Preis,Menge\n";
    for (auto& row : rows) {
        for (size_t i = 0; i < row.size(); ++i) {
            out << row[i];
            if (i + 1 < row.size()) out << ",";
        }
        out << "\n";
    }
    return csvPath;
}

bool BOMManager::exportToSpreadsheet(const std::filesystem::path& targetDir, Element* rootAssembly) {
    // Placeholder: In a C++ FreeCAD implementation, this would create a spreadsheet object.
    return exportToCsv(targetDir, rootAssembly).has_filename();
}

} // namespace FCProject
