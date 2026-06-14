#pragma once

#include <string>
#include <vector>
#include <App/Document.h>
#include <App/DocumentObject.h>
#include <App/DocumentObjectGroup.h>
#include <Base/Vector3D.h>

namespace FCProject {

// Erstellt Array-Pattern (linear/zirkular) von Elementen in einer Assembly.
// Hinweis: Die Joint-Erstellung zwischen den Pattern-Elementen (siehe
// python/AssemblyPatternCreator.py) basiert auf der Python-only Assembly-
// Workbench-API (JointObject/UtilsAssembly) und ist hier bewusst nicht
// portiert.
class AssemblyPatternCreator {
public:
    AssemblyPatternCreator(App::Document* doc, App::DocumentObject* assembly);

    // Komfort-Konstruktor für die Python-Bindung: sucht die Assembly im
    // aktiven Dokument anhand ihres internen Namens.
    explicit AssemblyPatternCreator(const std::string& assemblyName);

    // Erstellt ein lineares Array-Pattern eines Elements.
    auto createPattern(App::DocumentObject* sourceElement, int count = 3, double distance = 600.0,
                        const std::string& direction = "X-Achse") -> void;

    // Komfort-Überladung für die Python-Bindung: sucht das Quell-Element im
    // aktiven Dokument anhand seines internen Namens.
    auto createPattern(const std::string& sourceElementName, int count = 3, double distance = 600.0,
                        const std::string& direction = "X-Achse") -> void;

    // Erstellt ein Zirkular-Pattern eines Elements um die Z-Achse.
    auto createCircularPattern(App::DocumentObject* sourceElement, int count = 3, double radius = 50.0) -> void;

    // Komfort-Überladung für die Python-Bindung: sucht das Quell-Element im
    // aktiven Dokument anhand seines internen Namens.
    auto createCircularPattern(const std::string& sourceElementName, int count = 3, double radius = 50.0) -> void;

private:
    App::Document* doc_{nullptr};
    App::DocumentObject* assembly_{nullptr};
    App::DocumentObjectGroup* patternGroup_{nullptr};

    auto validateAssembly() -> void;
    auto validateSourceElement(App::DocumentObject* element) const -> void;
    auto createPatternGroup(App::DocumentObject* sourceElement, const std::string& namePrefix,
                             const std::string& labelPrefix) -> void;

    auto copyAndPlaceElements(App::DocumentObject* sourceElement, int count,
                               double distance, const std::string& direction) -> std::vector<App::DocumentObject*>;

    auto calculateOffsetVector(double distance, const std::string& direction, int i) const -> Base::Vector3d;
    auto getDirectionVector(const std::string& direction) const -> Base::Vector3d;

    // Dupliziert ein Element als App::Link auf das Quell-Element.
    auto duplicateElement(App::DocumentObject* sourceElement, const std::string& newLabel) -> App::DocumentObject*;

    // Sucht ein Objekt im Dokument anhand seines internen Namens (wirft bei Fehlschlag).
    auto getObjectOrThrow(const std::string& name) const -> App::DocumentObject*;

    static auto addToGroup(App::DocumentObject* group, App::DocumentObject* obj) -> void;
};

} // namespace FCProject
