#include "engine.hpp"

#include <cmath>
#include <iomanip>
#include <sstream>
#include <stdexcept>
#include <tuple>

namespace fanselect {

namespace {

std::string fmt(double value, int precision = 3) {
    std::ostringstream oss;
    oss << std::fixed << std::setprecision(precision) << value;
    return oss.str();
}

std::tuple<double, std::vector<std::string>> calcQFan(
    const MineParams& params,
    const SelectionCoeffs& coeffs
) {
    const double qF = coeffs.k * params.q1;
    std::vector<std::string> steps;
    steps.push_back(
        "[flow] Q_f = K * Q1 = " + fmt(coeffs.k, 2) + " * " +
        fmt(params.q1, 4) + " = " + fmt(qF, 4) + " m3/s"
    );
    return {qF, steps};
}

std::pair<double, std::vector<std::string>> calcResistance(double hF, double qFMs) {
    std::vector<std::string> steps;
    if (qFMs <= 0.0) {
        steps.push_back("[resistance] Q_f <= 0, cannot calculate R");
        return {0.0, steps};
    }

    const double r = hF / (qFMs * qFMs);
    steps.push_back(
        "[resistance] R = H_f / Q_f^2 = " + fmt(hF, 2) + " / " +
        fmt(qFMs, 4) + "^2 = " + fmt(r, 6)
    );
    return {r, steps};
}

std::pair<EngineResult, std::vector<std::string>> calcPeriod(
    const std::string& label,
    double q1,
    double hF,
    const SelectionCoeffs& coeffs
) {
    MineParams params{q1, hF};
    EngineResult result = runEngine(params, coeffs);

    std::vector<std::string> steps;
    steps.push_back("[" + label + "] Q1=" + fmt(q1, 4) + " m3/s, h_f=" + fmt(hF, 2) + " Pa");
    for (const auto& s : result.steps) {
        steps.push_back("[" + label + "] " + s);
    }
    return {result, steps};
}

std::pair<std::pair<std::vector<double>, std::vector<double>>, std::vector<std::string>>
calcPipelineCurve(const std::string& label, double r, double qMax, int n) {
    std::vector<double> qList;
    std::vector<double> hList;
    qList.reserve(n);
    hList.reserve(n);

    for (int i = 0; i < n; ++i) {
        const double q = qMax * static_cast<double>(i) / static_cast<double>(n - 1);
        qList.push_back(q);
        hList.push_back(r * q * q);
    }

    std::vector<std::string> steps;
    steps.push_back(
        "[" + label + " pipeline] H = " + fmt(r, 6) +
        " * Q^2, Q range 0 -> " + fmt(qMax, 4) +
        " m3/s, points=" + std::to_string(n)
    );
    return {{qList, hList}, steps};
}

}  // namespace

EngineResult runEngine(const MineParams& params, const SelectionCoeffs& coeffs) {
    if (params.q1 <= 0.0) {
        throw std::invalid_argument("Q1 must be positive");
    }
    if (params.hF <= 0.0) {
        throw std::invalid_argument("h_f must be positive");
    }

    EngineResult result;
    auto [qF, flowSteps] = calcQFan(params, coeffs);
    result.qFMs = qF;
    result.steps.insert(result.steps.end(), flowSteps.begin(), flowSteps.end());

    result.hF = params.hF;
    result.steps.push_back("[pressure] H_f = h_f = " + fmt(result.hF, 2) + " Pa");

    auto [r, resistanceSteps] = calcResistance(result.hF, result.qFMs);
    result.r = r;
    result.steps.insert(result.steps.end(), resistanceSteps.begin(), resistanceSteps.end());

    return result;
}

std::pair<std::vector<double>, std::vector<double>> pipelineCurve(
    double r,
    std::pair<double, double> qRange,
    int n
) {
    std::vector<double> qList;
    std::vector<double> hList;
    qList.reserve(n);
    hList.reserve(n);

    for (int i = 0; i < n; ++i) {
        const double q = qRange.first +
            static_cast<double>(i) * (qRange.second - qRange.first) / static_cast<double>(n - 1);
        qList.push_back(q);
        hList.push_back(r * q * q);
    }
    return {qList, hList};
}

DualPeriodResult runDual(
    const DualPeriodParams& params,
    const SelectionCoeffs& coeffs,
    int curveN
) {
    DualPeriodResult result;

    auto [easy, easySteps] = calcPeriod("easy", params.q1Easy, params.hFEasy, coeffs);
    result.easy = easy;
    result.steps.insert(result.steps.end(), easySteps.begin(), easySteps.end());

    auto [hard, hardSteps] = calcPeriod("hard", params.q1Hard, params.hFHard, coeffs);
    result.hard = hard;
    result.steps.insert(result.steps.end(), hardSteps.begin(), hardSteps.end());

    const double qMax = result.hard.qFMs * 1.3;

    auto [easyCurve, easyCurveSteps] = calcPipelineCurve("easy", result.easy.r, qMax, curveN);
    result.easyCurve = easyCurve;
    result.steps.insert(result.steps.end(), easyCurveSteps.begin(), easyCurveSteps.end());

    auto [hardCurve, hardCurveSteps] = calcPipelineCurve("hard", result.hard.r, qMax, curveN);
    result.hardCurve = hardCurve;
    result.steps.insert(result.steps.end(), hardCurveSteps.begin(), hardCurveSteps.end());

    return result;
}

}  // namespace fanselect
