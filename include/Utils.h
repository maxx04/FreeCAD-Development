#pragma once

#include <string>
#include <tuple>
#include <vector>
#include <App/Application.h>
#include <App/Document.h>
#include "FreeCADTypes.h"

namespace FCProject {

void ensureProperty(Element& obj, const std::string& name, const std::string& value);
auto getCleanChildren(Element* sourceObj) -> std::vector<Element*>;
auto getArtikelId(Element* element) -> std::string;
void printAssemblyTree(Element* rootObject);
auto getAssemblyTree(Element* rootObject) -> std::vector<std::tuple<Element*, int, std::string, std::vector<int>>>;
auto resolvePdmValue(Element* obj, const std::string& propName) -> std::string;
auto extractPdmData(Element* obj) -> std::map<std::string, std::string>;
auto getPropetiesAsStringMap(Element* obj) -> std::map<std::string, std::string>;
auto getPropertiesAsStringMap(App::DocumentObject* obj) -> std::map<std::string, std::map<std::string, std::string>> ;

} // namespace FCProject
