#pragma once

#include <map>
#include <string>
#include <vector>

namespace FCProject {

struct Vector3 {
    double x{0.0};
    double y{0.0};
    double z{0.0};

    Vector3() = default;
    Vector3(double x_, double y_, double z_) : x(x_), y(y_), z(z_) {}
    Vector3 operator*(double scalar) const { return {x * scalar, y * scalar, z * scalar}; }
};

struct Element {
    std::string name;
    std::string label;
    std::string typeId;
    std::vector<Element*> group;
    std::vector<Element*> features;
    Element* origin{nullptr};
    Element* linkedObject{nullptr};
    std::map<std::string, std::string> properties;
};

using PropertyMap = std::map<std::string, std::string>;

} // namespace FCProject
