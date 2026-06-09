#include "../include/Utils.h"


//#include <Base/Writer.h>
#include <App/DocumentObject.h>

#include <App/DocumentObject.h>
#include <App/Property.h>
#include <App/ObjectIdentifier.h>
#include <Base/Console.h>
#include <App/Link.h> // WICHTIG: Enthält die Definition für Link-Objekte
#include <App/DocumentObject.h>
#include <App/PropertyLinks.h> // Wichtig für den Zugriff auf PropertyLink


#include <string>
#include <vector>
#include <algorithm>
#include <functional>
#include <sstream>
#include <iostream>
#include <set>
#include <map>
#include "Utils.h"

FC_LOG_LEVEL_INIT("FCProject");

namespace FCProject {

void ensureProperty(Element& obj, const std::string& name, const std::string& value) {
    obj.properties[name] = value;
}

auto getCleanChildren(Element* sourceObj) -> std::vector<Element*> {

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

auto getArtikelId(Element* element) -> std::string {
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

auto printAssemblyTree(Element* rootObject) -> void {
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
    ///HACK: wie tief die Verlinkung kann sein.

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

/// @brief 
/// @param obj 
/// @return 
auto getPropetiesAsStringMap(Element* obj) -> std::map<std::string, std::string> {
    std::map<std::string, std::string> propertiesMap;

    if (!obj) return propertiesMap;

    for (const auto& prop : obj->properties) {
        propertiesMap[prop.first] = prop.second;

    #ifdef DEBUG
        FC_LOG("obj:" << obj->name << ":Property: " << prop.first << " = " << prop.second);
    #endif

    }
    return propertiesMap;
}



auto getPropertiesAsStringMap(App::DocumentObject* in_obj) -> std::map<std::string, std::map<std::string, std::string>> {
    std::map<std::string, std::map<std::string, std::string>> propertiesMap;

    if (!in_obj) return propertiesMap;


    App::DocumentObject *originalObj = GetOriginalObject(in_obj);
    // ---------------------------------------------

    // Ab hier läuft dein Code exakt wie gewohnt weiter, 
    // arbeitet nun aber mit dem echten Zielobjekt!
    std::vector<App::Property*> propList;

    originalObj->getPropertyList(propList);

    for (const auto* prop : propList) {
        if (!prop) continue;

        std::string propName{prop->getName()}; 
        std::string propGroup = prop->getGroup() ? prop->getGroup() : "Base"; 
        std::string propType{prop->getTypeId().getName()}; 
        std::string propValue = "";         
        
        // --- REINES C++ TYP-CASTING ---
        if (prop->getTypeId() == App::PropertyString::getClassTypeId()) {
            propValue = static_cast<const App::PropertyString*>(prop)->getValue();
        }
        else if (prop->getTypeId() == App::PropertyFloat::getClassTypeId()) {
            propValue = std::to_string(static_cast<const App::PropertyFloat*>(prop)->getValue());
        }
        else if (prop->getTypeId() == App::PropertyInteger::getClassTypeId()) {
            propValue = std::to_string(static_cast<const App::PropertyInteger*>(prop)->getValue());
        }
        else if (prop->getTypeId() == App::PropertyBool::getClassTypeId()) {
            propValue = static_cast<const App::PropertyBool*>(prop)->getValue() ? "True" : "False";
        }
        else if (prop->getTypeId() == App::PropertyLink::getClassTypeId()) {
            const auto* linkProp = static_cast<const App::PropertyLink*>(prop);
            if (const App::DocumentObject* linkedObj = linkProp->getValue()) {
                propValue = linkedObj->getNameInDocument();
            } else {
                propValue = "None";
            }
        }
        else if (prop->getTypeId() == App::PropertyXLink::getClassTypeId()) {
            const auto* xlinkProp = static_cast<const App::PropertyXLink*>(prop);
            if (const App::DocumentObject* linkedObj = xlinkProp->getValue()) {
                propValue = linkedObj->getNameInDocument();
            } else {
                propValue = "None";
            }
        }
        else {
            propValue = "-"; 
        }

        propertiesMap[propName]["Group"] = propGroup;
        propertiesMap[propName]["Type"]  = propType;
        propertiesMap[propName]["Value"] = propValue;

    #ifdef FC_DEBUG
        FC_LOG("obj:" << originalObj->getNameInDocument() << " | Gruppe: " << propGroup 
                      << " | Name: " << propName << " (" << propType << ") = " << propValue);
    #endif
    }

    return propertiesMap;
}




auto GetOriginalObject(App::DocumentObject *obj) -> App::DocumentObject*
{
    if (!obj) return nullptr;

    while (obj)
    {
        // 1. Suche nach der C++ Eigenschaft "LinkedObject", die jeder Link besitzt
        auto *prop = obj->getPropertyByName("LinkedObject");
        
        if (prop)
        {
            // 2. REINER STRING-VERGLEICH: Verhindert den "BadType"-Laufzeitfehler komplett!
            // getTypeId().getName() liefert direkt den Text "App::PropertyLink"
            std::string typeName{prop->getTypeId().getName()};

            if (typeName == "App::PropertyLink" || typeName == "App::PropertyXLink")
            {
                // 3. Wenn der Typname als Text matcht, dürfen wir sicher casten
                auto *linkProp = static_cast<const App::PropertyLink*>(prop);
                App::DocumentObject *target = linkProp->getValue();

                // 4. Wenn ein echtes, neues Ziel existiert, folgen wir ihm weiter
                if (target && target != obj)
                {
                    obj = target;
                    continue; // Nächste Runde, falls Links verschachtelt sind
                }
            }
        }

        // Wenn es kein Link mehr ist oder das Ziel leer ist, abbrechen
        break;
    }

    return obj; // Liefert das finale, echte Geometrie-Objekt
}

} // namespace FCProject
