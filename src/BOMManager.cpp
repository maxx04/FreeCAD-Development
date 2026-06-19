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
#include <algorithm>
#include <Mod/Spreadsheet/App/Sheet.h>

FC_LOG_LEVEL_INIT("FCProject");

namespace App { class DocumentObject; }

namespace FCProject {

namespace {


} // namespace

BOMManager::BOMManager(const std::string& root_name)  {

    #ifdef DEBUG
        FC_LOG("Der Debug-Modus ist aktiv!");
    #else
        FC_LOG_WARNING("WARNUNG: Immer noch im Release-Modus!");
    #endif

    auto doc = App::GetApplication().getActiveDocument(); // Zugriff auf FreeCADs API
    if (!doc) return;
    
    auto obj = doc->getObject(root_name.c_str());
    if (obj) {
        rootAssembly = obj;

        std::string fileName = doc->getFileName();
        std::filesystem::path docDir = fileName.empty()
             ? std::filesystem::current_path(): std::filesystem::path(fileName).parent_path();


        exportToCsv(docDir.string());
        //HACK: Wird aktuell in Python aaufgerufen.
        // exportToSpreadsheet(docDir.string()); 


        auto myMap = getPropertiesAsStringMapbyGroup(obj);

        generateStructuralBom();

        printAssemblyTree(obj); // Debug-Ausgabe der Baumstruktur

        // Einzelnen Wert gezielt abfragen
        std::string gruppe = myMap["ArticleID"]["Group"];
        std::string wert   = myMap["ArticleID"]["Value"];

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

    // Merkt sich pro ArtikelID den Index der bereits erzeugten BOM-Zeile,
    // damit weitere Vorkommen (z.B. Pattern-Kopien) nicht als eigene Zeile
    // auftauchen, sondern nur die Menge der ersten Zeile erhöhen.
    std::map<std::string, size_t> articleRowIndex;

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
                // Deutsches Dezimal-Komma in Punkt umwandeln, damit std::stod
                // den Wert korrekt parst (z. B. "12,50" -> "12.50")
                std::string preisRoh = pdmInfo["Preis"];
                std::replace(preisRoh.begin(), preisRoh.end(), ',', '.');
                preisStr = std::to_string(std::stod(preisRoh));
            }
        } catch (...) {
            preisStr = pdmInfo["Preis"]; // Fallback, falls der Preis kein valides Double ist
        }

        auto existingRow = articleRowIndex.find(pdmInfo["ArticleID"]);
        if (existingRow == articleRowIndex.end()) {
            articleRowIndex[pdmInfo["ArticleID"]] = bomList.size();
            bomList.push_back({
                structureIndex,
                pdmInfo["ArticleID"],
                pdmInfo["Bezeichnung"],
                pdmInfo["Material"],
                pdmInfo["Rohling"],
                preisStr,
                "1"
            });
        } else {
            // Gleiche ArtikelID bereits vorhanden (z.B. Pattern-Kopie) -> nur Menge erhöhen
            std::string& menge = bomList[existingRow->second].back();
            int mengeWert = 1;
            try { mengeWert = std::stoi(menge); } catch (...) {}
            menge = std::to_string(mengeWert + 1);
        }
    }
    return bomList;
}

auto BOMManager::exportToCsv(const std::string& targetDir) -> std::string  {

    auto rows = generateStructuralBom();

    std::filesystem::path targetDirPath(targetDir);

    if (rows.empty()) return "";

    std::filesystem::path csvPath = targetDirPath / (std::string("BOM_Struktur_") + (rootAssembly ? rootAssembly->getNameInDocument() : "document") + ".csv");
    std::ofstream out(csvPath);

    if (!out) return "";

    out << "Position (Struktur-Index),Artikel-ID,Benennung,Werkstoff,Rohling/Halbzeug,Preis,Menge\n";

    for (auto& row : rows) {

        for (size_t i = 0; i < row.size(); ++i) {
            out << escapeCsvField(row[i]);
            if (i + 1 < row.size()) out << ",";
        }
        out << "\n";
    }
    return csvPath.string();
}

auto BOMManager::exportToSpreadsheet(const std::string& /*targetDir*/) -> bool{

    auto doc = App::GetApplication().getActiveDocument();
    if (!doc) return false;

    auto rows = generateStructuralBom();
    if (rows.empty()) return false;

    auto* sheet = doc->addObject<Spreadsheet::Sheet>("BOM_Struktur");
    if (!sheet) return false;

    static const std::vector<std::string> header = {
        "Position (Struktur-Index)", "Artikel-ID", "Benennung",
        "Werkstoff", "Rohling/Halbzeug", "Preis", "Menge"
    };
    static const char* columns[] = {"A", "B", "C", "D", "E", "F", "G"};

    for (size_t col = 0; col < header.size(); ++col) {
        std::string address = std::string(columns[col]) + "1";
        sheet->setCell(address.c_str(), header[col].c_str());
    }

    for (size_t r = 0; r < rows.size(); ++r) {
        for (size_t col = 0; col < rows[r].size() && col < std::size(columns); ++col) {
            std::string address = std::string(columns[col]) + std::to_string(r + 2);
            sheet->setCell(address.c_str(), rows[r][col].c_str());
        }
    }

    doc->recompute();
    return true;
}


} // namespace FCProject
