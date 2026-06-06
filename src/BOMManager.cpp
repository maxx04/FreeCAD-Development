#include <App/Application.h>
#include <App/Document.h>
#include "../include/BOMManager.h"
#include "Utils.h"
#include <fstream>
#include <map>

namespace App { class DocumentObject; }

namespace FCProject {

BOMManager::BOMManager(const std::string& root_name)  {
    
    auto doc = App::GetApplication().getActiveDocument(); // Zugriff auf FreeCADs API
    if (!doc) return;
    
    auto obj = doc->getObject(root_name.c_str());

    if (obj) {
        // Hier müsstest du dein Element* aus dem FreeCAD-Objekt bauen
        // Das ist die "Konvertierungsfunktion"
        std::map<App::DocumentObject*, Element*> cache;
        this->rootAssembly = convertToElement(obj, cache); 
    }
}

auto BOMManager::generateStructuralBom() 
                        -> std::vector<std::vector<std::string>> {

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

        bomList.push_back({structureIndex, 
            pdmInfo["ArticleID"], 
            pdmInfo["Bezeichnung"], 
            pdmInfo["Material"], 
            pdmInfo["Rohling"], 
            std::to_string(std::stod(pdmInfo["Preis"])),
             "1"});
    }
    return bomList;
}

auto BOMManager::exportToCsv(const std::string& targetDir) -> bool {

    auto rows = generateStructuralBom();

    std::filesystem::path targetDirPath(targetDir);

    if (rows.empty()) return false;

    std::filesystem::path csvPath = targetDirPath / ("BOM_Struktur_" + (rootAssembly ? rootAssembly->label : "document") + ".csv");
    std::ofstream out(csvPath);

    if (!out) return false;

    out << "Position (Struktur-Index),Artikel-ID,Benennung,Werkstoff,Rohling/Halbzeug,Preis,Menge\n";

    for (auto& row : rows) {
        
        for (size_t i = 0; i < row.size(); ++i) {
            out << row[i];
            if (i + 1 < row.size()) out << ",";
        }
        out << "\n";
    }
    return true;
}

auto BOMManager::exportToSpreadsheet(const std::string& targetDir) -> bool {
    // Placeholder: In a C++ FreeCAD implementation, this would create a spreadsheet object.
    return exportToCsv(targetDir);
}

#include <App/DocumentObject.h>
#include <App/PropertyContainer.h>
#include <map>
#include <vector>

auto BOMManager::convertToElement(App::DocumentObject* obj, std::map<App::DocumentObject*, Element*>& cache) -> Element* {
    if (!obj) return nullptr;

    // Cache-Prüfung (jetzt mit der übergebenen Referenz!)
    if (cache.count(obj)) return cache[obj];

    Element* el = new Element();
    cache[obj] = el; // Objekt in den Cache schreiben

    el->name = obj->getNameInDocument();
    el->label = obj->Label.getValue(); 
    el->typeId = obj->getTypeId().getName();

    // 2. Richtiger Property-Abruf
    std::vector<App::Property*> props; 

    obj->getPropertyList(props); // 1. Schritt: Liste der NAMEN holen

    for (const auto& prop : props) {

        if (prop) {
            // Jetzt kannst du mit 'prop' arbeiten
            // z.B. el->properties[name] = prop->toString(); 
        }
    }

// 3. Rekursion (die Kinder holen)
    std::vector<App::DocumentObject*> children = obj->getOutList();
    for (auto* child : children) {
        Element* childEl = this->convertToElement(child, cache);
        if (childEl) {
            el->features.push_back(childEl);
        }
    }

    return el;
}

} // namespace FCProject
