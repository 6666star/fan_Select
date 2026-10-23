#pragma once

#include "models.hpp"

namespace fanselect {

EngineResult runEngine(const MineParams& params, const SelectionCoeffs& coeffs = {});

std::pair<std::vector<double>, std::vector<double>> pipelineCurve(
    double r,
    std::pair<double, double> qRange,
    int n = 100
);

DualPeriodResult runDual(
    const DualPeriodParams& params,
    const SelectionCoeffs& coeffs = {},
    int curveN = 200
);

}  // namespace fanselect
