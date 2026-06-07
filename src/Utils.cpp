
#include <Base/Console.h>
#include "../include/Utils.h"
#include <algorithm>
#include <functional>
#include <iostream>
#include <set>

FC_LOG_LEVEL_INIT("FCProject");

namespace FCProject {

void ensureProperty(Element& obj, const std::string& name, const std::string& value) {
    obj.properties[name] = value;
}

std::vector<std::tuple<Element*, int>> walkUltimateEverything(Element* rootObject) {
    std::vector<std::tuple<Element*, int>> result;
    if (!rootObject) {
        result.emplace_back(nullptr, 0);
        return result;
    }

    std::set<Element*> visited;
    std::function<void(Element*, int)> traverse = [&](Element* obj, int depth) {
        if (!obj || visited.count(obj)) return;
        visited.insert(obj);
        result.emplace_back(obj, depth);

        std::vector<Element*> children;
        if (!obj->group.empty()) {
            children.insert(children.end(), obj->group.begin(), obj->group.end());
        }
        if (!obj->features.empty()) {
            children.insert(children.end(), obj->features.begin(), obj->features.end());
        }
        if (obj->origin) children.push_back(obj->origin);
        if (obj->linkedObject) {
            Element* linked = obj->linkedObject;
            if (!linked->group.empty()) children.insert(children.end(), linked->group.begin(), linked->group.end());
            if (!linked->features.empty()) children.insert(children.end(), linked->features.begin(), linked->features.end());
            if (linked->origin) children.push_back(linked->origin);
        }

        for (auto* child : children) {
            traverse(child, depth + 1);
        }
    };

    traverse(rootObject, 0);
    result.emplace_back(nullptr, 0);
    return result;
}

std::vector<std::tuple<Element*, int>> walkAssemblyIterative(Element* rootObject) {
    std::vector<std::tuple<Element*, int>> result;
    if (!rootObject) {
        result.emplace_back(nullptr, 0);
        return result;
    }

    std::vector<std::pair<Element*, int>> stack{{rootObject, 0}};
    std::set<Element*> visited;

    while (!stack.empty()) {
        auto [obj, depth] = stack.back();
        stack.pop_back();
        if (!obj || visited.count(obj)) continue;
        visited.insert(obj);
        result.emplace_back(obj, depth);

        std::vector<Element*> children;
        if (!obj->group.empty()) children.insert(children.end(), obj->group.begin(), obj->group.end());
        if (!obj->features.empty()) children.insert(children.end(), obj->features.begin(), obj->features.end());
        if (obj->origin) children.push_back(obj->origin);
        if (obj->linkedObject) {
            Element* target = obj->linkedObject;
            if (!target->group.empty()) children.insert(children.end(), target->group.begin(), target->group.end());
            if (!target->features.empty()) children.insert(children.end(), target->features.begin(), target->features.end());
            if (target->origin) children.push_back(target->origin);
        }

        for (auto it = children.rbegin(); it != children.rend(); ++it) {
            stack.emplace_back(*it, depth + 1);
        }
    }

    result.emplace_back(nullptr, 0);
    return result;
}

std::vector<std::tuple<Element*, int>> walkAssemblyCompleteInstances(Element* rootObject) {
    std::vector<std::tuple<Element*, int>> result;
    if (!rootObject) {
        result.emplace_back(nullptr, 0);
        return result;
    }

    struct Item { Element* obj; int depth; std::vector<Element*> path; };
    std::vector<Item> stack{{rootObject, 0, {}}};

    while (!stack.empty()) {
        auto item = stack.back();
        stack.pop_back();
        if (!item.obj) continue;
        if (std::find(item.path.begin(), item.path.end(), item.obj) != item.path.end()) continue;
        item.path.push_back(item.obj);
        result.emplace_back(item.obj, item.depth);

        std::vector<Element*> children;
        if (item.obj->origin) children.push_back(item.obj->origin);
        if (!item.obj->group.empty()) children.insert(children.end(), item.obj->group.begin(), item.obj->group.end());
        if (!item.obj->features.empty()) children.insert(children.end(), item.obj->features.begin(), item.obj->features.end());
        if (item.obj->linkedObject) {
            Element* target = item.obj->linkedObject;
            if (target->origin) children.push_back(target->origin);
            if (!target->group.empty()) children.insert(children.end(), target->group.begin(), target->group.end());
            if (!target->features.empty()) children.insert(children.end(), target->features.begin(), target->features.end());
        }

        for (auto it = children.rbegin(); it != children.rend(); ++it) {
            stack.push_back({*it, item.depth + 1, item.path});
        }
    }

    result.emplace_back(nullptr, 0);
    return result;
}

std::vector<Element*> getCleanChildren(Element* sourceObj) {
    std::vector<Element*> items;
    if (!sourceObj) return items;
    if (sourceObj->origin) items.push_back(sourceObj->origin);

    std::vector<Element*> rawGroup = sourceObj->group;
    std::vector<Element*> rawFeatures = sourceObj->features;
    std::set<Element*> hiddenInSubfolders;

    for (auto* c : rawGroup) {
        if (c && (c->typeId == "App::DocumentObjectGroup" || c->typeId == "Assembly::JointGroup")) {
            for (auto* sub : c->group) {
                if (sub) hiddenInSubfolders.insert(sub);
            }
        }
    }

    for (auto* c : rawGroup) {
        if (c && hiddenInSubfolders.count(c) == 0 && std::find(items.begin(), items.end(), c) == items.end()) {
            items.push_back(c);
        }
    }
    for (auto* c : rawFeatures) {
        if (c && std::find(items.begin(), items.end(), c) == items.end()) {
            items.push_back(c);
        }
    }
    return items;
}

std::string getArtikelId(Element* element) {
    if (!element) return "None";
    if (element->properties.count("ArticleID") && !element->properties.at("ArticleID").empty()) {
        return element->properties.at("ArticleID");
    }
    Element* current = element;
    while (current && current->linkedObject) {
        current = current->linkedObject;
        if (current->properties.count("ArticleID") && !current->properties.at("ArticleID").empty()) {
            return current->properties.at("ArticleID");
        }
    }
    return "None";
}

void printPerfectAssemblyTree(Element* rootObject) {
    if (!rootObject) {
        std::cout << "Kein Objekt übergeben." << std::endl;
        return;
    }

    #ifdef DEBUG
        FC_LOG("\n--- START DER BAUGRUPPEN-ANALYSE ---");
    #endif  

    struct Item { Element* obj; int depth; std::vector<Element*> path; std::vector<bool> flags; };
    std::vector<Item> stack{{rootObject, 0, {}, {}}};

    while (!stack.empty()) {

        Item item = stack.back();

        stack.pop_back();

        if (!item.obj) continue;

        if (std::find(item.path.begin(), item.path.end(), item.obj) != item.path.end()) continue;

        item.path.push_back(item.obj);

        std::string prefix;
        for (size_t i = 0; i + 1 < item.flags.size(); ++i) {
            prefix += item.flags[i] ? "    " : "│   ";
        }
        if (!item.flags.empty()) {
            prefix += item.flags.back() ? "└── " : "├── ";
        }

        std::string artikelId = getArtikelId(item.obj);
        
        #ifdef DEBUG
            FC_LOG(prefix << item.obj->label << " [ID: " << artikelId << "] (" << item.obj->typeId << ")");
        #endif

        std::vector<Element*> children = getCleanChildren(item.obj);
        if (item.obj->linkedObject) {
            for (auto* child : getCleanChildren(item.obj->linkedObject)) {
                if (std::find(children.begin(), children.end(), child) == children.end()) {
                    children.push_back(child);
                }
            }
        }

        for (int i = static_cast<int>(children.size()) - 1; i >= 0; --i) {

            bool childIsLast = (i == static_cast<int>(children.size()) - 1);

            auto nextFlags = item.flags;

            nextFlags.push_back(childIsLast);

            stack.push_back({children[i], item.depth + 1, item.path, nextFlags});

        }
    }

    #ifdef DEBUG
        FC_LOG("🏁 --- ANALYSE ERFOLGREICH BEENDET ---");
    #endif
}

auto getAssemblyTree(Element* rootObject) -> std::vector<std::tuple<Element*, int, std::string, std::vector<int>>> {

    std::vector<std::tuple<Element*, int, std::string, std::vector<int>>> assemblyTree; // Ergebnis-Container für den Assembly-Baum

    if (!rootObject) {
        FC_LOG("Kein Objekt übergeben."); // Wenn kein Eingabeobjekt vorhanden ist, Log schreiben
        return assemblyTree; // Leeres Ergebnis zurückgeben
    }
    #ifdef DEBUG
        FC_LOG("\n--- START DURCHLAUF ---"); // Debug-Ausgabe zum Beginn der Traversierung
    #endif

    struct Item { Element* obj; int depth; std::vector<Element*> path; std::vector<bool> flags; std::vector<int> indexPath; }; // Stack-Eintrag für Traversierung

    std::vector<Item> stack{{rootObject, 0, {}, {}, {1}}}; // Root-Objekt auf den Stack legen

    while (!stack.empty()) {

        Item item = stack.back(); // Aktuellen Stack-Eintrag lesen

        stack.pop_back(); // Eintrag aus dem Stack entfernen

        if (!item.obj) continue; // Falls das Objekt null ist, überspringen

        if (std::find(item.path.begin(), item.path.end(), item.obj) != item.path.end()) continue; // Zyklus vermeiden

        item.path.push_back(item.obj); // Objekt zum aktuellen Pfad hinzufügen

        std::string artikelId = getArtikelId(item.obj); // Artikel-ID für das Objekt ermitteln

        #ifdef DEBUG

            FC_LOG(item.obj->label << " [ID: " << artikelId << "] (" << item.obj->typeId << ")"); // Debug-Ausgabe für den aktuellen Knoten

        #endif

        assemblyTree.emplace_back(item.obj, item.depth, artikelId, item.indexPath); // Knoten zum Ergebnis hinzufügen

        std::vector<Element*> children{}; // Kinderliste für das aktuelle Objekt initialisieren

        if (item.obj->linkedObject) {

            for (auto* child : getCleanChildren(item.obj->linkedObject)) {

                if (std::find(children.begin(), children.end(), child) == children.end()) 
                {
                    children.push_back(child); // Einzigartige Kinder aus dem verlinkten Objekt hinzufügen
                }
            }
        }
        else
            children = getCleanChildren(item.obj); // Direkte Kinder hinzufügen, falls kein verlinktes Objekt vorhanden ist
        


        for (int i = static_cast<int>(children.size()) - 1; i >= 0; --i) {

            bool childIsLast = (i == static_cast<int>(children.size()) - 1); // Prüfen, ob aktuelles Kind das letzte ist

            auto nextFlags = item.flags; // Flag-Liste kopieren

            nextFlags.push_back(childIsLast); // Füge Flag für das Kind hinzu

            auto childIndexPath = item.indexPath; // Indexpfad kopieren

            childIndexPath.push_back(i + 1); // Kind-Index zum Pfad hinzufügen

            stack.push_back({children[i], item.depth + 1, item.path, nextFlags, childIndexPath}); // Kind als neuen Stack-Eintrag hinzufügen
        }
    }
    #ifdef DEBUG
        FC_LOG("🏁 --- ANALYSE ERFOLGREICH BEENDET ---"); // Debug-Ausgabe nach Abschluss der Traversierung
    #endif



    return assemblyTree; // Ergebnisliste zurückgeben
}

auto resolvePdmValue(Element* obj, const std::string& propName) -> std::string {

    if (!obj) return {};

    Element* target = obj;

    if (obj->linkedObject) target = obj->linkedObject;

    if (target->properties.count(propName) && !target->properties.at(propName).empty()) {
        return target->properties.at(propName);
    }

    if (!target->group.empty()) {

        for (auto* child : target->group) {

            if (!child || !child->properties.count(propName)) continue;

            if (!child->properties.at(propName).empty()) 
            {
                return child->properties.at(propName);
            }
        }
    }
    return {};
}

auto extractPdmData(Element* obj) -> std::map<std::string, std::string> {

    std::map<std::string, std::string> result;

    result["ArticleID"] = resolvePdmValue(obj, "ArticleID");
    result["Bezeichnung"] = resolvePdmValue(obj, "Bezeichnung");

    if (result["Bezeichnung"].empty()) {
        result["Bezeichnung"] = resolvePdmValue(obj, "ProfilTyp");
    }

    result["Material"] = resolvePdmValue(obj, "MaterialName");

    if (result["Material"].empty() && obj->linkedObject && !obj->linkedObject->properties["ShapeMaterial"].empty()) {
        result["Material"] = obj->linkedObject->properties["ShapeMaterial"];
    }

    if (result["Material"].empty()) result["Material"] = "-";

    std::string preis = resolvePdmValue(obj, "Preis");

    result["Preis"] = preis.empty() ? "0.0" : preis;

    std::string rohling = "-";

    Element* pdmObj = obj->linkedObject ? obj->linkedObject : obj;

    if (pdmObj->typeId != "Assembly::AssemblyObject") {

        if (pdmObj->properties.count("BasiertAufHalbzeug") && !pdmObj->properties.at("BasiertAufHalbzeug").empty()) 
        {
            rohling = pdmObj->properties.at("BasiertAufHalbzeug");
        }
    }
    result["Rohling"] = rohling;

    return result;
}

void scanRecursive(Element* currentObj, const std::string& currentIndex, std::vector<std::vector<std::string>>& bomList, std::vector<Element*>& visitedObjects) {
    if (!currentObj || std::find(visitedObjects.begin(), visitedObjects.end(), currentObj) != visitedObjects.end()) {
        return;
    }
    visitedObjects.push_back(currentObj);
    Element* scanTarget = currentObj->linkedObject ? currentObj->linkedObject : currentObj;
    for (auto* child : scanTarget->group) {
        if (!child) continue;
        if (resolvePdmValue(child, "ArticleID").empty()) continue;
        std::string newIndex = currentIndex.empty() ? "1" : currentIndex + "-1";
        auto pdmInfo = extractPdmData(child);
        bomList.push_back({newIndex, pdmInfo["ArticleID"], pdmInfo["Bezeichnung"], pdmInfo["Material"], pdmInfo["Rohling"], "1"});
        Element* targetChild = child->linkedObject ? child->linkedObject : child;
        if (!targetChild->group.empty()) {
            scanRecursive(child, newIndex, bomList, visitedObjects);
        }
    }
}

} // namespace FCProject
