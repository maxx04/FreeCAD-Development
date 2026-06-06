#pragma once

#include <string>
#include <tuple>
#include <vector>
#include "FreeCADTypes.h"

namespace FCProject {

void ensureProperty(Element& obj, const std::string& name, const std::string& value);
std::vector<std::tuple<Element*, int>> walkUltimateEverything(Element* rootObject);
std::vector<std::tuple<Element*, int>> walkAssemblyIterative(Element* rootObject);
std::vector<std::tuple<Element*, int>> walkAssemblyCompleteInstances(Element* rootObject);
std::vector<Element*> getCleanChildren(Element* sourceObj);
std::string getArtikelId(Element* element);
void printPerfectAssemblyTree(Element* rootObject);
std::vector<std::tuple<Element*, int, std::string, std::vector<int>>> getAssemblyTree(Element* rootObject);
std::string resolvePdmValue(Element* obj, const std::string& propName);
std::map<std::string, std::string> extractPdmData(Element* obj);
void scanRecursive(Element* currentObj, const std::string& currentIndex, std::vector<std::vector<std::string>>& bomList, std::vector<Element*>& visitedObjects);

} // namespace FCProject
