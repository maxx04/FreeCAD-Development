// 1. Eigene Projekt-Header (Projekt-Schnittstellen immer zuerst)
#include "../include/Utils.h"

// 2. FreeCAD Core Basis-Header
#include <Base/Console.h>

// 3. FreeCAD App- & Object-Header
#include <App/DocumentObject.h>
#include <App/Property.h>
#include <App/ObjectIdentifier.h>

// 4. FreeCAD Link-, Gruppen- & Property-Typen
#include <App/Link.h>
#include <App/PropertyLinks.h>
#include <App/PropertyStandard.h>

// 5. C++ Standard Template Library (STL) Header (Alphabetisch sortiert)
#include <algorithm>
#include <functional>
#include <iostream>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <tuple>
#include <vector>


FC_LOG_LEVEL_INIT("FCProject");

namespace FCProject {


// Hilfsfunktion zum sicheren Auslesen von Link-Listen (für Group und Features)
auto getObjectsFromLinkListProperty(const App::DocumentObject* obj, const char* propName) -> std::vector<App::DocumentObject*> {
    std::vector<App::DocumentObject*> result;
    if (!obj) return result;
    
    if (auto* prop = obj->getPropertyByName(propName)) {
        if (auto* linkList = dynamic_cast<const App::PropertyLinkList*>(prop)) {
            return linkList->getValue();
        }
    }
    return result;
}

auto getCleanChildren(App::DocumentObject* sourceObj) -> std::vector<App::DocumentObject*> {
    std::vector<App::DocumentObject*> items;
    if (!sourceObj) return items;

    // 1. Origin auslesen (falls vorhanden als PropertyLink)
    if (auto* originProp = sourceObj->getPropertyByName("Origin")) {
        if (auto* originLink = dynamic_cast<const App::PropertyLink*>(originProp)) {
            if (auto* originObj = originLink->getValue()) {
                items.push_back(originObj);
            }
        }
    }

    // 2. Gruppen und Features über die offiziellen Properties holen
    std::vector<App::DocumentObject*> rawGroup = getObjectsFromLinkListProperty(sourceObj, "Group");
    std::vector<App::DocumentObject*> rawFeatures = getObjectsFromLinkListProperty(sourceObj, "Features");

    std::set<App::DocumentObject*> hiddenInSubfolders;

    // Unterordner durchsuchen (App::DocumentObjectGroup oder Assembly::JointGroup)
    for (const auto* c : rawGroup) {
        if (c) {
            std::string typeName{c->getTypeId().getName()};
            if (typeName == "App::DocumentObjectGroup" || typeName == "Assembly::JointGroup") {
                std::vector<App::DocumentObject*> subGroup = getObjectsFromLinkListProperty(c, "Group");
                for (auto* sub : subGroup) {
                    if (sub) {
                        hiddenInSubfolders.insert(sub);
                    }
                }
            }
        }
    }

    // Elemente ohne Duplikate in die Liste eintragen
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

auto printAssemblyTree(App::DocumentObject* rootObject) -> void {
    if (!rootObject) {
        #ifdef DEBUG
            FC_LOG("Kein Objekt übergeben.");
        #else
            std::cout << "Kein Objekt übergeben." << std::endl;
        #endif
        return;
    }

    #ifdef DEBUG
        FC_LOG("\n--- START DER BAUGRUPPEN-ANALYSE ---");
    #endif  

    struct Item { 
        App::DocumentObject* obj; 
        int depth; 
        std::vector<App::DocumentObject*> path; 
        std::vector<bool> flags; 
    };
    std::vector<Item> stack{{rootObject, 0, {}, {}}};

    while (!stack.empty()) {
        Item item = stack.back();
        stack.pop_back();

        if (!item.obj) continue;

        // Zyklusschutz über physische C++ Pointer-Adressen im RAM
        if (std::find(item.path.begin(), item.path.end(), item.obj) != item.path.end()) continue;

        item.path.push_back(item.obj);

        std::string prefix;
        for (size_t i = 0; i + 1 < item.flags.size(); ++i) {
            prefix += item.flags[i] ? "    " : "│   ";
        }
        if (!item.flags.empty()) {
            prefix += item.flags.back() ? "└── " : "├── ";
        }

        std::string artikelId = resolvePdmValue(item.obj, "ArticleID");
        if (artikelId.empty()) artikelId = "None";

        #ifdef DEBUG
            // Versionenunabhängiges Auslesen von Label und Typname über die FreeCAD API
            std::string currentLabel = item.obj->Label.getStrValue();
            std::string currentType{item.obj->getTypeId().getName()};
            FC_LOG(prefix << currentLabel << " [ID: " << artikelId << "] (" << currentType << ")");
        #endif

        // Kinder über deine neue getCleanChildren sammeln
        std::vector<App::DocumentObject*> children = getCleanChildren(item.obj);
        
        // Verlinktes Objekt auflösen und dessen Kinder hinzufügen, falls vorhanden
        App::DocumentObject* linkedObj = item.obj->getLinkedObject(false);
        if (linkedObj && linkedObj != item.obj) {
            for (auto* child : getCleanChildren(linkedObj)) {
                if (child && std::find(children.begin(), children.end(), child) == children.end()) {
                    children.push_back(child);
                }
            }
        }

        // Kinder in umgekehrter Reihenfolge auf den Stack legen
        for (int i = static_cast<int>(children.size()) - 1; i >= 0; --i) {
            bool childIsLast = (i == static_cast<int>(children.size()) - 1);

            auto nextFlags = item.flags;
            nextFlags.push_back(childIsLast);

            stack.push_back({children[i], item.depth + 1, item.path, nextFlags});
        }
    }

    #ifdef DEBUG
        FC_LOG("🏁 --- DURCHLAUF BEENDET ---");
    #endif
}

auto getAssemblyTree(App::DocumentObject* rootObject) -> std::vector<std::tuple<App::DocumentObject*, int, std::string, std::vector<int>>> {
    std::vector<std::tuple<App::DocumentObject*, int, std::string, std::vector<int>>> assemblyTree; 

    if (!rootObject) {
        #ifdef DEBUG
            FC_LOG("Kein Objekt übergeben."); 
        #endif
        return assemblyTree; 
    }

    #ifdef DEBUG
        FC_LOG("\n--- START DURCHLAUF ---"); 
    #endif

    struct Item { 
        App::DocumentObject* obj; 
        int depth; 
        std::vector<App::DocumentObject*> path; 
        std::vector<bool> flags; 
        std::vector<int> indexPath; 
    }; 

    std::vector<Item> stack{{rootObject, 0, {}, {}, {1}}}; 

    while (!stack.empty()) {
        Item item = stack.back(); 
        stack.pop_back(); 

        if (!item.obj) continue; 

        // Zyklusschutz über die echten C++ Objekt-Pointer im RAM
        if (std::find(item.path.begin(), item.path.end(), item.obj) != item.path.end()) continue; 

        item.path.push_back(item.obj); 

        // Holt die Artikel-ID direkt vom FreeCAD-Objekt
        std::string artikelId = resolvePdmValue(item.obj, "ArticleID");
        if (artikelId.empty()) artikelId = "None";

        #ifdef DEBUG
            // Versionenunabhängiges Auslesen von Label und Typname
            std::string currentLabel{item.obj->Label.getValue()};
            std::string currentType{item.obj->getTypeId().getName()};
            FC_LOG(currentLabel << " [ID: " << artikelId << "] (" << currentType << ")"); 
        #endif

        assemblyTree.emplace_back(item.obj, item.depth, artikelId, item.indexPath); 

        // Kinder über getCleanChildren sammeln (wie in printAssemblyTree)
        std::vector<App::DocumentObject*> children = getCleanChildren(item.obj);

        // Verlinktes Objekt auflösen und dessen Kinder hinzufügen, falls vorhanden
        App::DocumentObject* linkedObj = item.obj->getLinkedObject(false);
        if (linkedObj && linkedObj != item.obj) {
            for (auto* child : getCleanChildren(linkedObj)) {
                if (child && std::find(children.begin(), children.end(), child) == children.end()) {
                    children.push_back(child);
                }
            }
        }

        // Kinder in umgekehrter Reihenfolge auf den Stack legen
        for (int i = static_cast<int>(children.size()) - 1; i >= 0; --i) {
            bool childIsLast = (i == static_cast<int>(children.size()) - 1); 

            auto nextFlags = item.flags; 
            nextFlags.push_back(childIsLast); 

            auto childIndexPath = item.indexPath; 
            childIndexPath.push_back(i + 1); 

            stack.push_back({children[i], item.depth + 1, item.path, nextFlags, childIndexPath}); 
        }
    }

    #ifdef DEBUG
        FC_LOG("🏁 --- DURCHLAUF BEENDET ---"); 
    #endif

    return assemblyTree; 
}

auto resolvePdmValue(App::DocumentObject* obj, const std::string& propName) -> std::string {
    if (!obj) return {};

    // Prüft, ob ein Wert aus der Properties-Map sinnvoll gefüllt ist
    auto isUsable = [](const std::string& value) {
        return !value.empty() && value != "-" && value != "None";
    };

    // 1. Verlinkte Objekte auflösen (z. B. App::Link -> echtes Geometrie-Objekt)
    App::DocumentObject* target = GetOriginalObject(obj);
    if (!target) target = obj;

    auto props = getPropertiesAsStringMapbyGroup(target);
    auto it = props.find(propName);
    if (it != props.end() && isUsable(it->second["Value"])) {
        return it->second["Value"];
    }

    // 2. Falls am Objekt selbst nicht vorhanden, in den direkten Kindern (Group) suchen
    for (auto* child : getObjectsFromLinkListProperty(target, "Group")) {
        if (!child) continue;

        auto childProps = getPropertiesAsStringMapbyGroup(child);
        auto childIt = childProps.find(propName);
        if (childIt != childProps.end() && isUsable(childIt->second["Value"])) {
            return childIt->second["Value"];
        }
    }

    return {};
}

auto extractPdmData(App::DocumentObject* obj) ->  std::map<std::string, std::string> {
    // Hinweis: Rückgabetyp im Header anpassen, falls dort noch App::DocumentObject* stand.
    std::map<std::string, std::string> result;

    if (!obj) return result;

    // 1. Einfache Werte über resolvePdmValue holen (durchsucht Objekt, Link-Ziel und Group-Kinder)
    result["ArticleID"] = resolvePdmValue(obj, "ArticleID");
    result["Bezeichnung"] = resolvePdmValue(obj, "Bezeichnung");

    if (result["Bezeichnung"].empty()) {
        result["Bezeichnung"] = resolvePdmValue(obj, "ProfilTyp");
    }

    result["Material"] = resolvePdmValue(obj, "MaterialName");

    // Fallback für Material aus dem verlinkten Objekt ("ShapeMaterial") holen
    if (result["Material"].empty()) {
        result["Material"] = resolvePdmValue(obj, "ShapeMaterial");
    }

    if (result["Material"].empty()) {
        result["Material"] = "-";
    }

    std::string preis = resolvePdmValue(obj, "Preis");
    result["Preis"] = preis.empty() ? "0.0" : preis;

    // 2. Rohling/Halbzeug-Ermittlung direkt aus den FreeCAD-Properties auslesen
    App::DocumentObject* pdmObj = GetOriginalObject(obj);
    if (!pdmObj) pdmObj = obj;

    std::string rohling = "-";
    std::string currentType{pdmObj->getTypeId().getName()};

    if (currentType != "Assembly::AssemblyObject") {
        std::string halbzeugValue = resolvePdmValue(obj, "BasiertAufHalbzeug");
        if (!halbzeugValue.empty()) {
            rohling = halbzeugValue;
        }
    }
    result["Rohling"] = rohling;

    return result;
}

auto getPropertiesAsStringMapbyGroup(App::DocumentObject* in_obj) -> std::map<std::string, std::map<std::string, std::string>> {
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

 //       const Base::Type& typeId = prop->getTypeId();
 //       std::string_view propType = typeId.getName();  // Bei 1.1.1 ist getName() auf Base::Type

        std::string propType = safeStringCast(prop->getTypeId().getName());
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

// Maskiert ein Feld für CSV (RFC 4180): Felder mit Komma, Anführungszeichen
// oder Zeilenumbruch werden in Anführungszeichen gesetzt, enthaltene
// Anführungszeichen werden verdoppelt.
auto escapeCsvField(const std::string& field) -> std::string {

    if (field.find_first_of(",\"\n\r") == std::string::npos) {
        return field;
    }

    std::string escaped = "\"";

    for (char c : field) {
        if (c == '"') escaped += '"';
        escaped += c;
    }
    escaped += "\"";

    return escaped;
}

} // namespace FCProject
