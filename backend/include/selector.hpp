#pragma once

#include "models.hpp"

#include <optional>
#include <string>
#include <tuple>
#include <vector>

namespace fanselect {

std::tuple<std::vector<FanModel>, std::vector<FanModel>, std::vector<std::string>>
screenByRange(
    const std::vector<FanModel>& fans,
    double qEasy,
    double hEasy,
    double qHard,
    double hHard
);

std::tuple<std::optional<double>, std::optional<double>, std::vector<std::string>>
solveWorkingPoint(const FanInterpolated& fanInterpolated, double r);

std::tuple<
    double,
    double,
    double,
    double,
    double,
    bool,
    std::vector<std::string>
>
verifyEfficiency(
    const FanInterpolated& fanInterpolated,
    double uEasy,
    double hOpEasy,
    double uHard,
    double hOpHard,
    double qEasy,
    double qHard,
    double etaMin,
    double etaT,
    double kN
);

std::pair<double, std::vector<std::string>> scoreCandidate(
    double etaEasy,
    double etaHard,
    double nShaftHard,
    double nMotorInst
);

std::pair<std::optional<SelectionCandidate>, std::vector<std::string>>
evaluateOne(
    const FanModel& fan,
    double rEasy,
    double qEasy,
    double hEasy,
    double rHard,
    double qHard,
    double hHard,
    double etaMin,
    double etaT,
    double kN
);

SelectorResult runSelector(
    const DualPeriodResult& dualResult,
    double etaMin = 0.70,
    double etaT = 0.95,
    double kN = 1.15,
    const std::vector<FanModel>* fans = nullptr
);

}  // namespace fanselect
