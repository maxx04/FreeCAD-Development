#include "../include/AssemblyPatternCreator.h"
#include <iostream>

namespace FCProject {

AssemblyPatternCreator::AssemblyPatternCreator(Element* assembly) : assembly(assembly) {}

void AssemblyPatternCreator::createPattern(Element* sourceElement, int count, double distance, const std::string& direction) {
    validateSourceElement(sourceElement);
    if (!assembly) {
        throw std::runtime_error("Keine Assembly vorhanden");
    }
    patternGroup = new Element();
    patternGroup->label = "Pattern: " + sourceElement->label;
    patternGroup->name = "Pattern_" + sourceElement->label;
    patternGroup->typeId = "App::DocumentObjectGroup";
    if (assembly) assembly->group.push_back(patternGroup);

    for (int i = 1; i <= count; ++i) {
        Element* copy = duplicateElement(sourceElement, sourceElement->label + "_Copy_" + std::to_string(i));
        Vector3 offset = calculateOffsetVector(distance, direction, i);
        copy->properties["Offset"] = std::to_string(offset.x) + "," + std::to_string(offset.y) + "," + std::to_string(offset.z);
        if (patternGroup) patternGroup->group.push_back(copy);
    }

    std::cout << "FCProject: Pattern '" << patternGroup->label << "' mit " << count << " Elementen erstellt." << std::endl;
}

void AssemblyPatternCreator::validateSourceElement(Element* element) const {
    if (!element) {
        throw std::invalid_argument("Quell-Element ist null");
    }
    if (element->label.empty()) {
        throw std::invalid_argument("Quell-Element besitzt kein Label");
    }
}

Vector3 AssemblyPatternCreator::calculateOffsetVector(double distance, const std::string& direction, int index) const {
    return getDirectionVector(direction) * (distance * static_cast<double>(index));
}

Vector3 AssemblyPatternCreator::getDirectionVector(const std::string& direction) const {
    if (direction == "Y-Achse") return {0.0, 1.0, 0.0};
    if (direction == "Z-Achse") return {0.0, 0.0, 1.0};
    return {1.0, 0.0, 0.0};
}

Element* AssemblyPatternCreator::duplicateElement(Element* sourceElement, const std::string& newLabel) const {
    if (!sourceElement) return nullptr;
    Element* result = new Element(*sourceElement);
    result->label = newLabel;
    result->name = newLabel;
    result->group.clear();
    result->features.clear();
    return result;
}

} // namespace FCProject
