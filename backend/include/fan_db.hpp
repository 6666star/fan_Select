#pragma once

#include "models.hpp"

#include <tuple>
#include <vector>

namespace fanselect {

FanModel makeFanFromData(
    const std::string& modelId,
    const std::string& series,
    double rpm,
    std::pair<double, double> rpmRange,
    double motorKw,
    int motorCount,
    const std::vector<std::tuple<double, double, double>>& rawData,
    const std::string& fanType = "counter_rotating"
);

FanInterpolated buildFanInterpolated(
    const FanModel& fan,
    int hDeg = 2,
    int etaDeg = 4
);

const std::vector<FanModel>& fanDb();

}  // namespace fanselect
