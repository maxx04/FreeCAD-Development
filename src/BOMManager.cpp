#include <App/Application.h>
#include <App/Document.h>
#include <App/PropertyStandard.h>
#include <Base/Console.h>
#include "../include/BOMManager.h"
#include <App/DocumentObject.h>
#include <App/PropertyContainer.h>
#include <map>
#include <vector>
#include "Utils.h"
#include <fstream>

FC_LOG_LEVEL_INIT("FCProject");

namespace App { class DocumentObject; }

namespace FCProject {


// Hilfsfunktion für FreeCAD 1.1.1 (C-String-Variante)
inline std::string safeStringCast(const char* ptr) {
    return ptr != nullptr ? std::string(ptr) : std::string();
}

// Hilfsfunktion für FreeCAD 1.2dev (string_view-Variante)
inline std::string safeStringCast(std::string_view view) {
    return std::string(view);
}

BOMManager::BOMManager(const std::string& root_name)  {

    #ifdef DEBUG
        FC_LOG("ERFOLG: Der Debug-Modus ist aktiv!");
    #else
        FC_LOG_WARNING("WARNUNG: Immer noch im Release-Modus!");
    #endif

    auto doc = App::GetApplication().getActiveDocument(); // Zugriff auf FreeCADs API
    if (!doc) return;
    
    auto obj = doc->getObject(root_name.c_str());
    if (obj) {


        auto myMap = getPropertiesAsStringMap(obj);

        // Einzelnen Wert gezielt abfragen
        std::string gruppe = myMap["Label"]["Group"];
        std::string wert   = myMap["Label"]["Value"];

    }
}

auto BOMManager::generateStructuralBom() -> std::vector<std::vector<std::string>> {
    std::vector<std::vector<std::string>> bomList;

    // getAssemblyTree liefert jetzt direkt App::DocumentObject* anstelle von App::DocumentObject*
    auto tree = getAssemblyTree(rootAssembly);

    #ifdef DEBUG
        printAssemblyTree(rootAssembly);                     
    #endif

    std::vector<int> visibleIndexCounters;
    int previousDepth = -1;

    for (auto& row : tree) {
        // Änderung: Nutze direkt den nativen FreeCAD-Typ App::DocumentObject*
        App::DocumentObject* obj = nullptr;
        int depth;
        std::string artikelId;
        std::vector<int> indexPath;
        std::tie(obj, depth, artikelId, indexPath) = row;

        if (!obj || artikelId.empty() || artikelId == "None") continue;

        if (depth > previousDepth) {
            if (static_cast<int>(visibleIndexCounters.size()) <= depth) {
                visibleIndexCounters.resize(depth + 1);
            }
            for (int d = previousDepth + 1; d <= depth; ++d) {
                visibleIndexCounters[d] = 1;
            }
        }
        else if (depth == previousDepth) {
            visibleIndexCounters[depth] += 1;
        }
        else {
            visibleIndexCounters.resize(depth + 1);
            visibleIndexCounters[depth] += 1;
        }

        previousDepth = depth;

        // Änderung: extractPdmData verarbeitet das native FreeCAD-Objekt direkt
        std::map<std::string, std::string> pdmInfo = extractPdmData(obj);

        std::string structureIndex = "'"; 

        for (int i = 0; i <= depth; ++i) {
            if (i) structureIndex += ".";
            structureIndex += std::to_string(visibleIndexCounters[i]);
        }

        #ifdef DEBUG
            // Versionenunabhängiges Auslesen des Namens über getNameInDocument()
            FC_LOG("Objekt: " << obj->getNameInDocument() << ", ArtikelID: " << artikelId << ", Struktur-Index: " << structureIndex);
        #endif

        // Preis-Konvertierung zur Sicherheit in einen try-catch-Block packen
        std::string preisStr = "0.0";
        try {
            if (!pdmInfo["Preis"].empty()) {
                preisStr = std::to_string(std::stod(pdmInfo["Preis"]));
            }
        } catch (...) {
            preisStr = pdmInfo["Preis"]; // Fallback, falls der Preis kein valides Double ist
        }

        bomList.push_back({
            structureIndex, 
            pdmInfo["ArticleID"], 
            pdmInfo["Bezeichnung"], 
            pdmInfo["Material"], 
            pdmInfo["Rohling"], 
            preisStr,
            "1"
        });
    }
    return bomList;
}

auto BOMManager::exportToCsv(const std::string& targetDir) -> bool {

    auto rows = generateStructuralBom();

    std::filesystem::path targetDirPath(targetDir);

    if (rows.empty()) return false;

    std::filesystem::path csvPath = targetDirPath / (std::string("BOM_Struktur_") + (rootAssembly ? rootAssembly->getNameInDocument() : "document") + ".csv");
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


} // namespace FCProject
