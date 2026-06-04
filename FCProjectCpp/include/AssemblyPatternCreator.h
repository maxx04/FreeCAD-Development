#pragma once

#include <string>
#include <vector>
#include "FreeCADTypes.h"

namespace FCProject {

class AssemblyPatternCreator {
public:
    AssemblyPatternCreator(Element* assembly);
    void createPattern(Element* sourceElement, int count, double distance, const std::string& direction);

private:
    Element* assembly;
    Element* patternGroup{nullptr};
    void validateSourceElement(Element* element) const;
    Vector3 calculateOffsetVector(double distance, const std::string& direction, int index) const;
    Vector3 getDirectionVector(const std::string& direction) const;
    Element* duplicateElement(Element* sourceElement, const std::string& newLabel) const;
};

} // namespace FCProject
