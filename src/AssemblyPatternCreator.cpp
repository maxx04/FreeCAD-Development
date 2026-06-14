// 1. Eigene Projekt-Header (Projekt-Schnittstellen immer zuerst)
#include "../include/AssemblyPatternCreator.h"

// 2. FreeCAD Core Basis-Header
#include <Base/Console.h>
#include <Base/Placement.h>
#include <Base/Rotation.h>

// 3. FreeCAD App- & Object-Header
#include <App/Application.h>
#include <App/DocumentObject.h>
#include <App/GroupExtension.h>
#include <App/Link.h>
#include <App/PropertyGeo.h>

// 4. C++ Standard Template Library (STL) Header
#include <cmath>
#include <stdexcept>
#include <string>

FC_LOG_LEVEL_INIT("FCProject");

namespace FCProject {

AssemblyPatternCreator::AssemblyPatternCreator(App::Document* doc, App::DocumentObject* assembly)
    : doc_(doc), assembly_(assembly) {
    validateAssembly();
}

AssemblyPatternCreator::AssemblyPatternCreator(const std::string& assemblyName) {
    doc_ = App::GetApplication().getActiveDocument();
    if (!doc_) {
        throw std::invalid_argument("Kein aktives Dokument vorhanden!");
    }

    assembly_ = doc_->getObject(assemblyName.c_str());
    if (!assembly_) {
        throw std::invalid_argument("Assembly-Objekt '" + assemblyName + "' wurde nicht gefunden!");
    }

    validateAssembly();
}

auto AssemblyPatternCreator::getObjectOrThrow(const std::string& name) const -> App::DocumentObject* {
    App::DocumentObject* obj = doc_->getObject(name.c_str());
    if (!obj) {
        throw std::invalid_argument("Objekt '" + name + "' wurde nicht gefunden!");
    }
    return obj;
}

auto AssemblyPatternCreator::validateAssembly() -> void {
    if (!doc_) {
        throw std::invalid_argument("Document ist nullptr!");
    }
    if (!assembly_) {
        throw std::invalid_argument("Assembly-Objekt ist nullptr!");
    }

    std::string typeName{assembly_->getTypeId().getName()};
    if (typeName != "Assembly::AssemblyObject") {
        throw std::invalid_argument("Objekt ist keine Assembly, sondern: " + typeName);
    }

    FC_LOG("FCProject: Assembly '" << assembly_->Label.getValue() << "' validiert.");
}

auto AssemblyPatternCreator::validateSourceElement(App::DocumentObject* element) const -> void {
    if (!element) {
        throw std::invalid_argument("Quell-Element ist nullptr!");
    }

    bool isValid = false;
    if (element->getPropertyByName("Shape") != nullptr) {
        isValid = true; // Hat Shape
    } else if (element->getTypeId().isDerivedFrom(Base::Type::fromName("Assembly::AssemblyObject"))) {
        isValid = true; // Assembly
    } else if (element->getTypeId().isDerivedFrom(Base::Type::fromName("App::Part"))) {
        isValid = true; // Part
    } else if (element->getTypeId().isDerivedFrom(Base::Type::fromName("PartDesign::Body"))) {
        isValid = true; // Body
    } else if (element->getTypeId().isDerivedFrom(Base::Type::fromName("App::Link"))) {
        isValid = true; // Link
    }

    if (!isValid) {
        throw std::invalid_argument("Quell-Element '" + std::string(element->Label.getValue()) +
                                      "' (Typ: " + std::string(element->getTypeId().getName()) + ") ist nicht gültig! "
                                      "Unterstützt: Part, Body, Assembly, Link, oder Elemente mit Shape.");
    }

    FC_LOG("FCProject: Quell-Element '" << element->Label.getValue() << "' validiert.");
}

auto AssemblyPatternCreator::addToGroup(App::DocumentObject* group, App::DocumentObject* obj) -> void {
    if (!group || !obj) return;

    if (auto* groupExt = group->getExtensionByType<App::GroupExtension>(true)) {
        groupExt->addObject(obj);
    } else {
        FC_WARN("FCProject: Objekt '" << group->Label.getValue() << "' unterstützt addObject nicht.");
    }
}

auto AssemblyPatternCreator::createPatternGroup(App::DocumentObject* sourceElement, const std::string& namePrefix,
                                                 const std::string& labelPrefix) -> void {
    auto* group = doc_->addObject("App::DocumentObjectGroup", (namePrefix + sourceElement->getNameInDocument()).c_str());
    if (!group) {
        throw std::runtime_error("Fehler beim Erstellen der Pattern-Gruppe!");
    }

    patternGroup_ = static_cast<App::DocumentObjectGroup*>(group);
    patternGroup_->Label.setValue(labelPrefix + sourceElement->Label.getValue());

    addToGroup(assembly_, patternGroup_);
}

auto AssemblyPatternCreator::getDirectionVector(const std::string& direction) const -> Base::Vector3d {
    if (direction == "Y-Achse") return Base::Vector3d(0.0, 1.0, 0.0);
    if (direction == "Z-Achse") return Base::Vector3d(0.0, 0.0, 1.0);
    return Base::Vector3d(1.0, 0.0, 0.0); // Default / "X-Achse"
}

auto AssemblyPatternCreator::calculateOffsetVector(double distance, const std::string& direction, int i) const -> Base::Vector3d {
    return getDirectionVector(direction) * (distance * i);
}

auto AssemblyPatternCreator::duplicateElement(App::DocumentObject* sourceElement,
                                               const std::string& newLabel) -> App::DocumentObject* {
    FC_LOG("FCProject: Dupliziere Element '" << sourceElement->Label.getValue()
           << "' (TypeId: " << sourceElement->getTypeId().getName() << ").");

    // Erstelle eine Link-Kopie, die auf das Quell-Element verweist.
    if (sourceElement->getPropertyByName("LinkedObject") != nullptr) {
        FC_LOG("FCProject: Erstelle Link-Kopie eines referenzierten Objekts.");

        auto* newObj = doc_->addObject("App::Link", ("link_" + newLabel).c_str());
        if (!newObj) {
            throw std::runtime_error("Element '" + std::string(sourceElement->Label.getValue()) +
                                      "' konnte nicht dupliziert werden: App::Link konnte nicht erstellt werden!");
        }

        auto* link = static_cast<App::Link*>(newObj);
        link->LinkedObject.setValue(sourceElement);
        link->Label.setValue(newLabel);
        return link;
    }

    throw std::runtime_error("Element '" + std::string(sourceElement->Label.getValue()) +
                              "' konnte nicht dupliziert werden: kein unterstützter Typ für die Duplizierung.");
}

auto AssemblyPatternCreator::copyAndPlaceElements(App::DocumentObject* sourceElement,
                                                   int count, double distance,
                                                   const std::string& direction) -> std::vector<App::DocumentObject*> {
    std::vector<App::DocumentObject*> copiedElements;

    for (int i = 1; i <= count; ++i) {
        try {
            Base::Vector3d offsetVector = calculateOffsetVector(distance, direction, i);

            App::DocumentObject* newElement = duplicateElement(
                sourceElement, std::string(sourceElement->Label.getValue()) + "_Copy_" + std::to_string(i));

            if (!newElement) {
                FC_WARN("FCProject: Element " << (i + 1) << " konnte nicht erstellt werden (nullptr returned).");
                continue;
            }

            // Positioniere das neue Element (falls möglich)
            if (auto* placementProp = dynamic_cast<App::PropertyPlacement*>(newElement->getPropertyByName("Placement"))) {
                Base::Placement currentPlacement = placementProp->getValue();
                Base::Placement newPlacement(currentPlacement.getPosition() + offsetVector, currentPlacement.getRotation());
                placementProp->setValue(newPlacement);
                FC_LOG("FCProject: Element " << i << "/" << count << " positioniert.");
            } else {
                FC_WARN("FCProject: Element " << i << " hat keine Placement-Property.");
            }

            // Füge zur Pattern-Gruppe hinzu und versuche, das Element in der Assembly einzuhängen
            addToGroup(patternGroup_, newElement);
            addToGroup(assembly_, newElement);

            copiedElements.push_back(newElement);
        } catch (const std::exception& e) {
            FC_ERR("FCProject: Fehler bei Element " << i << "/" << count << ": " << e.what());
            continue;
        }
    }

    if (copiedElements.empty()) {
        throw std::runtime_error("Keine Elemente konnten kopiert werden!");
    }

    FC_LOG("FCProject: " << copiedElements.size() << " Elemente erfolgreich erstellt.");
    return copiedElements;
}

auto AssemblyPatternCreator::createPattern(App::DocumentObject* sourceElement, int count, double distance,
                                            const std::string& direction) -> void {
    // 1. Validierungen für kopierbares Element
    validateSourceElement(sourceElement);

    // 2. Erstelle eine Pattern-Gruppe für Übersicht
    createPatternGroup(sourceElement, "Pattern_", "Pattern: ");

    // 3. Kopiere das Original-Element count mal und positioniere es
    copyAndPlaceElements(sourceElement, count, distance, direction);

    // 4. Joints zwischen den Elementen (Original und Kopien) werden hier nicht erstellt,
    // da dies auf der Python-only Assembly-Workbench-API (JointObject/UtilsAssembly) basiert.
    FC_WARN("FCProject: Joint-Erstellung ist im C++ Pattern-Creator nicht implementiert.");

    // 5. Recompute
    doc_->recompute();

    FC_LOG("FCProject: Pattern '" << patternGroup_->Label.getValue() << "' mit " << count << " Elementen erfolgreich erstellt!");
}

auto AssemblyPatternCreator::createPattern(const std::string& sourceElementName, int count, double distance,
                                            const std::string& direction) -> void {
    createPattern(getObjectOrThrow(sourceElementName), count, distance, direction);
}

auto AssemblyPatternCreator::createCircularPattern(const std::string& sourceElementName, int count, double radius) -> void {
    createCircularPattern(getObjectOrThrow(sourceElementName), count, radius);
}

auto AssemblyPatternCreator::createCircularPattern(App::DocumentObject* sourceElement, int count, double radius) -> void {
    if (count < 1) {
        throw std::invalid_argument("Anzahl muss mindestens 1 sein!");
    }
    if (radius <= 0.0) {
        throw std::invalid_argument("Radius muss > 0 sein!");
    }

    validateSourceElement(sourceElement);

    createPatternGroup(sourceElement, "CircularPattern_", "Circular Pattern: ");

    const double angleStep = 2.0 * M_PI / count;

    for (int i = 0; i < count; ++i) {
        double angle = angleStep * i;
        double x = radius * std::cos(angle);
        double y = radius * std::sin(angle);

        App::DocumentObject* newElement = duplicateElement(
            sourceElement, std::string(sourceElement->Label.getValue()) + "_Circular_" + std::to_string(i));

        if (auto* placementProp = dynamic_cast<App::PropertyPlacement*>(newElement->getPropertyByName("Placement"))) {
            Base::Placement currentPlacement = placementProp->getValue();
            Base::Vector3d position(x, y, currentPlacement.getPosition().z);
            Base::Placement newPlacement(position, Base::Rotation(Base::Vector3d(0.0, 0.0, 1.0), angle));
            placementProp->setValue(newPlacement);
        }

        addToGroup(patternGroup_, newElement);

        FC_LOG("FCProject: Circular-Element " << i << "/" << count << " erstellt.");
    }

    doc_->recompute();
    FC_LOG("FCProject: Circular Pattern '" << patternGroup_->Label.getValue() << "' erfolgreich erstellt!");
}

} // namespace FCProject
