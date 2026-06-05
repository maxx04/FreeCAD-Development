#include "../include/MaterialUtils.h"

namespace FCProject {

std::string getNativeMaterialByName(const std::string& targetName) {
    if (targetName.empty()) {
        return "";
    }
    return targetName;
}

} // namespace FCProject
