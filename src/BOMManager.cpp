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
        // Hier müsstest du dein Element* aus dem FreeCAD-Objekt bauen
        // Das ist die "Konvertierungsfunktion"
        std::map<App::DocumentObject*, Element*> cache;
        this->rootAssembly = convertToElement(obj, cache); 

        auto myMap = getPropertiesAsStringMap(obj);

        // Einzelnen Wert gezielt abfragen
        std::string gruppe = myMap["Label"]["Group"];
        std::string wert   = myMap["Label"]["Value"];

        //getPropetiesAsStringMap(this->rootAssembly);
    }
}

auto BOMManager::generateStructuralBom() 
                        -> std::vector<std::vector<std::string>> {

    std::vector<std::vector<std::string>> bomList;

    auto tree = getAssemblyTree(rootAssembly);

    #ifdef DEBUG
        printAssemblyTree(rootAssembly); // Optional: Ausgabe der Baumstruktur in der Konsole                     
    #endif

    std::vector<int> visibleIndexCounters;
    int previousDepth = -1;

    for (auto& row : tree) {

        Element* obj;
        int depth;
        std::string artikelId;
        std::vector<int> indexPath;
        std::tie(obj, depth, artikelId, indexPath) = row;

        if (!obj || artikelId.empty() || artikelId == "None") continue;

        // Nur sichtbare BOM-Einträge nummerieren, damit keine Lücken wie 1.3
        // entstehen, wenn ein Baumknoten ohne Artikel-ID ausgefiltert wird.
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

        std::map<std::string, std::string> pdmInfo = extractPdmData(obj);

        std::string structureIndex = "'"; // Apostroph, damit Excel die führenden Nullen nicht entfernt

        for (int i = 0; i <= depth; ++i) {
            if (i) structureIndex += ".";
            structureIndex += std::to_string(visibleIndexCounters[i]);
        }

        #ifdef DEBUG
            FC_LOG("Objekt: " << obj->name << ", ArtikelID: " << artikelId << ", Struktur-Index: " << structureIndex);
        #endif

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

auto BOMManager::convertToElement(App::DocumentObject* obj, std::map<App::DocumentObject*, Element*>& cache) -> Element* {
    if (!obj) return nullptr; // Kein Eingabeobjekt: nichts zu konvertieren

    // Cache-Prüfung: bereits konvertiertes Objekt wiederverwenden
    if (cache.count(obj)) return cache[obj];

    Element* el = new Element();
    cache[obj] = el; // Objekt zur Wiederverwendung cachen

    // Basisdaten vom FreeCAD-Objekt ins Element übernehmen
    el->name = obj->getNameInDocument();
    el->label = obj->Label.getValue();
    el->typeId = obj->getTypeId().getName();

    // 2. Property-Abruf: nur stringbasierte Properties ins Map übertragen
    std::vector<App::Property*> props;
    obj->getPropertyList(props); // Alle Properties des Objekts sammeln

    for (const auto& prop : props) {
        if (!prop) continue; // Sicherheitscheck

        if (prop->getTypeId() == App::PropertyString::getClassTypeId()) {
            // Nur PropertyString auswerten
            auto* strProp = static_cast<const App::PropertyString*>(prop);
            std::string text = strProp->getStrValue(); // String-Wert lesen
            el->properties.emplace(prop->getName(), text); // im Element speichern

            #ifdef DEBUG
                FC_LOG(el->name << ":\t" << prop->getName() << "\t- " << text);
            #endif
        }
    }

    // 3. Rekursion: Origin, Group, Features und verlinktes Objekt verarbeiten

    if (auto* originProp = obj->getPropertyByName("Origin")) {
        if (auto* originLink = dynamic_cast<App::PropertyLink*>(originProp)) {
            if (auto* originObj = originLink->getValue()) {
                el->origin = this->convertToElement(originObj, cache); // Origin-Kind konvertieren
            }
        }
    }

    if (auto* groupProp = obj->getPropertyByName("Group")) {
        if (auto* groupLinks = dynamic_cast<App::PropertyLinkList*>(groupProp)) {
            for (auto* child : groupLinks->getValue()) {
                if (!child) continue; // Null-Zeiger ignorieren
                Element* childEl = this->convertToElement(child, cache);
                if (childEl) {
                    el->group.push_back(childEl); // Gruppe als direktes Kind speichern
                }
            }
        }
    }

    if (auto* featuresProp = obj->getPropertyByName("Features")) {
        if (auto* featureLinks = dynamic_cast<App::PropertyLinkList*>(featuresProp)) {
            for (auto* child : featureLinks->getValue()) {
                if (!child) continue; // Null-Zeiger ignorieren
                Element* childEl = this->convertToElement(child, cache);
                if (childEl) {
                    el->features.push_back(childEl); // Feature-Kind speichern
                }
            }
        }
    }

    if (auto* linked = obj->getLinkedObject(false)) {
        if (linked != obj) {
            el->linkedObject = this->convertToElement(linked, cache); // Verlinktes Objekt auflösen
        }
    }

    return el; // Fertiges Element zurückgeben
}

} // namespace FCProject
