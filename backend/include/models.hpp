#pragma once

#include <functional>
#include <optional>
#include <string>
#include <utility>
#include <vector>

namespace fanselect {

struct MineParams {
    double q1 = 0.0;
    double hF = 0.0;
};

struct SelectionCoeffs {
    double k = 1.0;
};

struct EngineResult {
    double qFMs = 0.0;
    double hF = 0.0;
    double r = 0.0;
    std::vector<std::string> steps;
};

struct DualPeriodParams {
    double q1Easy = 0.0;
    double hFEasy = 0.0;
    double q1Hard = 0.0;
    double hFHard = 0.0;
};

struct DualPeriodResult {
    EngineResult easy;
    EngineResult hard;
    std::pair<std::vector<double>, std::vector<double>> easyCurve;
    std::pair<std::vector<double>, std::vector<double>> hardCurve;
    std::vector<std::string> steps;
};

struct FanCurvePoint {
    double q = 0.0;
    double h = 0.0;
    double eta = 0.0;
};

struct FanModel {
    std::string modelId;
    std::string series;
    std::string fanType = "counter_rotating";
    double ratedRpm = 0.0;
    std::pair<double, double> rpmRange;
    double motorKw = 0.0;
    int motorCount = 0;
    std::vector<FanCurvePoint> curvePoints;
    double bladeAngleDeg = 0.0;
    double railWidthMm = 0.0;
    std::string imagePath;
    std::string manufacturer;
    std::string productName;
    std::string productSpec;
    std::string motorModel;
    std::string factoryNo;

    double totalMotorKw() const { return motorKw * motorCount; }
    double qMin() const { return curvePoints.front().q; }
    double qMax() const { return curvePoints.back().q; }
    double hMin() const;
    double hMax() const;
};

struct Polynomial {
    std::vector<double> coeffs;
    double operator()(double x) const;
};

struct FanInterpolated {
    FanModel fan;
    Polynomial hPoly;
    Polynomial etaPoly;
    double qMin = 0.0;
    double qMax = 0.0;
    double r2H = 0.0;
    double r2Eta = 0.0;
};

struct SelectionCandidate {
    FanModel fan;
    double qOpEasy = 0.0;
    double hOpEasy = 0.0;
    double qOpHard = 0.0;
    double hOpHard = 0.0;
    double etaEasy = 0.0;
    double etaHard = 0.0;
    double nShaftEasy = 0.0;
    double nShaftHard = 0.0;
    double nMotorReq = 0.0;
    double baseQEasy = 0.0;
    double baseHEasy = 0.0;
    double baseQHard = 0.0;
    double baseHHard = 0.0;
    double nRatio = 0.0;
    double nEasyRpm = 0.0;
    double nHardRpm = 0.0;
    double powerMargin = 0.0;
    double score = 0.0;
    std::vector<std::string> steps;
};

struct SelectorResult {
    std::vector<SelectionCandidate> candidates;
    std::optional<SelectionCandidate> best;
    int screenedOut = 0;
    int rejectedEff = 0;
    std::vector<std::string> steps;
};

}  // namespace fanselect
