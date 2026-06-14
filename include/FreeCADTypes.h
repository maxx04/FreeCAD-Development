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
    auto operator*(double scalar) const -> Vector3 { return {x * scalar, y * scalar, z * scalar}; }
}; 


using PropertyMap = std::map<std::string, std::string>;

} // namespace FCProject
