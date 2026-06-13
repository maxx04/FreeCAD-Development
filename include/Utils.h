#pragma once

#include <string>
#include <tuple>
#include <vector>
#include <App/Application.h>
#include <App/Document.h>
#include "FreeCADTypes.h"

namespace FCProject {

//void ensureProperty(App::DocumentObject& obj, const std::string& name, const std::string& value);
auto getCleanChildren(App::DocumentObject* sourceObj) -> std::vector<App::DocumentObject*>;
auto getArtikelId(App::DocumentObject* obj) -> std::string;
void printAssemblyTree(App::DocumentObject* rootObject);
auto getAssemblyTree(App::DocumentObject* rootObject) -> std::vector<std::tuple<App::DocumentObject*, int, std::string, std::vector<int>>>;
auto resolvePdmValue(App::DocumentObject* obj, const std::string& propName) -> std::string;
auto extractPdmData(App::DocumentObject* obj) -> std::map<std::string, std::string>;
auto getPropertiesAsStringMapbyGroup(App::DocumentObject *obj) -> std::map<std::string, std::map<std::string, std::string>>;
auto GetOriginalObject(App::DocumentObject *obj) -> App::DocumentObject*;

// Hilfsfunktion für FreeCAD 1.1.1 (C-String-Variante)
inline std::string safeStringCast(const char* ptr) {
    return ptr != nullptr ? std::string(ptr) : std::string();
}

// Hilfsfunktion für FreeCAD 1.2dev (string_view-Variante)
inline std::string safeStringCast(std::string_view view) {
    return std::string(view);
}


} // namespace FCProject
