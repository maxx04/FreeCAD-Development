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
auto getPropetiesAsStringMap(App::DocumentObject* obj) -> std::map<std::string, std::string>;
auto getPropertiesAsStringMap(App::DocumentObject *obj) -> std::map<std::string, std::map<std::string, std::string>>;

auto GetOriginalObject(App::DocumentObject *obj) -> App::DocumentObject*;

} // namespace FCProject
