#include "selector.hpp"

#include "config.hpp"
#include "fan_db.hpp"

#include <algorithm>
#include <cmath>
#include <functional>
#include <iomanip>
#include <sstream>

namespace fanselect {

namespace {

std::string fmt(double value, int precision = 3) {
    std::ostringstream oss;
    oss << std::fixed << std::setprecision(precision) << value;
    return oss.str();
}

double clamp(double value, double lo, double hi) {
    return std::max(lo, std::min(hi, value));
}

std::optional<double> bisectRoot(
    const std::function<double(double)>& f,
    double a,
    double b,
    double xtol
) {
    double fa = f(a);
    double fb = f(b);
    if (fa == 0.0) {
        return a;
    }
    if (fb == 0.0) {
        return b;
    }
    if (fa * fb > 0.0) {
        return std::nullopt;
    }

    for (int i = 0; i < 100; ++i) {
        const double mid = 0.5 * (a + b);
        const double fm = f(mid);
        if (std::abs(fm) < 1e-9 || std::abs(b - a) < xtol) {
            return mid;
        }
        if (fa * fm <= 0.0) {
            b = mid;
            fb = fm;
        } else {
            a = mid;
            fa = fm;
        }
    }
    return 0.5 * (a + b);
}

}  // namespace

std::tuple<std::vector<FanModel>, std::vector<FanModel>, std::vector<std::string>>
screenByRange(
    const std::vector<FanModel>& fans,
    double qEasy,
    double hEasy,
    double qHard,
    double hHard
) {
    std::vector<std::string> steps = {
        "[screen] easy Q=" + fmt(qEasy, 2) + " m3/s, H=" + fmt(hEasy, 1) + " Pa",
        "[screen] hard Q=" + fmt(qHard, 2) + " m3/s, H=" + fmt(hHard, 1) + " Pa",
        "[screen] fan count=" + std::to_string(fans.size()),
    };

    std::vector<FanModel> passed;
    std::vector<FanModel> rejected;

    for (const auto& fan : fans) {
        std::vector<std::string> reasons;
        if (fan.qMax() < qHard) {
            reasons.push_back("Q_max < hard Q");
        }
        if (fan.hMax() < hHard) {
            reasons.push_back("H_max < hard H");
        }
        if (fan.qMin() > qHard) {
            reasons.push_back("Q_min > hard Q");
        }

        const double rMin = fan.rpmRange.first / fan.ratedRpm;
        const double qMinVfd = fan.qMin() * rMin;
        if (qMinVfd > qEasy) {
            reasons.push_back("minimum VFD Q > easy Q");
        }

        if (reasons.empty()) {
            passed.push_back(fan);
            steps.push_back("  pass " + fan.modelId);
        } else {
            rejected.push_back(fan);
            steps.push_back("  reject " + fan.modelId + ": " + reasons.front());
        }
    }

    steps.push_back("[screen result] passed=" + std::to_string(passed.size()) +
                    ", rejected=" + std::to_string(rejected.size()));
    return {passed, rejected, steps};
}

std::tuple<std::optional<double>, std::optional<double>, std::vector<std::string>>
solveWorkingPoint(const FanInterpolated& fanInterpolated, double r) {
    std::vector<std::string> steps;

    const auto f = [&](double q) {
        return fanInterpolated.hPoly(q) - r * q * q;
    };

    std::vector<double> qScan;
    qScan.reserve(BRENTQ_SCAN_POINTS);
    for (int i = 0; i < BRENTQ_SCAN_POINTS; ++i) {
        const double q = fanInterpolated.qMax +
            static_cast<double>(i) * (fanInterpolated.qMin - fanInterpolated.qMax) / static_cast<double>(BRENTQ_SCAN_POINTS - 1);
        qScan.push_back(q);
    }

    for (size_t i = 0; i + 1 < qScan.size(); ++i) {
        const double f0 = f(qScan[i]);
        const double f1 = f(qScan[i + 1]);
        if (f0 * f1 < 0.0) {
            const double a = std::min(qScan[i], qScan[i + 1]);
            const double b = std::max(qScan[i], qScan[i + 1]);
            auto root = bisectRoot(f, a, b, ROOT_XTOL);
            if (root.has_value()) {
                const double qOp = *root;
                const double hOp = r * qOp * qOp;
                steps.push_back("intersection Q=" + fmt(qOp, 3) + " m3/s, H=" + fmt(hOp, 1) + " Pa");
                return {qOp, hOp, steps};
            }
        }
    }

    steps.push_back("no intersection found");
    return {std::nullopt, std::nullopt, steps};
}

std::tuple<double, double, double, double, double, bool, std::vector<std::string>>
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
) {
    const double etaEasy = clamp(fanInterpolated.etaPoly(uEasy), 0.01, 1.0);
    const double etaHard = clamp(fanInterpolated.etaPoly(uHard), 0.01, 1.0);

    const double nShaftEasy = qEasy * hOpEasy / (1000.0 * etaEasy * etaT);
    const double nShaftHard = qHard * hOpHard / (1000.0 * etaHard * etaT);
    const double nMotorReq = std::max(nShaftEasy, nShaftHard) * kN;
    const bool passed = etaEasy >= etaMin && etaHard >= etaMin;

    std::vector<std::string> steps = {
        "easy eta=" + fmt(etaEasy, 4) + ", shaft=" + fmt(nShaftEasy, 1) + " kW",
        "hard eta=" + fmt(etaHard, 4) + ", shaft=" + fmt(nShaftHard, 1) + " kW",
        "motor required >= " + fmt(nMotorReq, 1) + " kW",
    };

    return {etaEasy, etaHard, nShaftEasy, nShaftHard, nMotorReq, passed, steps};
}

std::pair<double, std::vector<std::string>> scoreCandidate(
    double etaEasy,
    double etaHard,
    double nShaftHard,
    double nMotorInst
) {
    const double sHard = std::min(etaHard / SCORE_ETA_REF, 1.0);
    const double sEasy = std::min(etaEasy / SCORE_ETA_REF, 1.0);
    const double utilization = nMotorInst > 0.0 ? nShaftHard / nMotorInst : 0.0;
    const double sMotor = std::max(0.0, 1.0 - std::abs(utilization - 0.80) / 0.80);

    const double score = SCORE_W_ETA_HARD * sHard +
        SCORE_W_ETA_EASY * sEasy +
        SCORE_W_MOTOR * sMotor;

    std::vector<std::string> steps = {
        "score hard=" + fmt(sHard, 3) +
        ", easy=" + fmt(sEasy, 3) +
        ", motor=" + fmt(sMotor, 3) +
        ", total=" + fmt(score, 4)
    };
    return {score, steps};
}

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
) {
    std::vector<std::string> steps = {"--- " + fan.modelId + " ---"};
    const FanInterpolated fanInterpolated = buildFanInterpolated(fan, FIT_H_DEGREE, FIT_ETA_DEGREE);

    auto [uEasy, hBaseEasy, easySteps] = solveWorkingPoint(fanInterpolated, rEasy);
    steps.insert(steps.end(), easySteps.begin(), easySteps.end());
    auto [uHard, hBaseHard, hardSteps] = solveWorkingPoint(fanInterpolated, rHard);
    steps.insert(steps.end(), hardSteps.begin(), hardSteps.end());

    if (!uEasy.has_value() || !uHard.has_value()) {
        steps.push_back("reject: no curve intersection");
        return {std::nullopt, steps};
    }

    const double nEasyRpm = fan.ratedRpm * qEasy / *uEasy;
    const double nHardRpm = fan.ratedRpm * qHard / *uHard;

    if (nEasyRpm < fan.rpmRange.first || nEasyRpm > fan.rpmRange.second) {
        steps.push_back("reject: easy rpm out of range");
        return {std::nullopt, steps};
    }
    if (nHardRpm < fan.rpmRange.first || nHardRpm > fan.rpmRange.second) {
        steps.push_back("reject: hard rpm out of range");
        return {std::nullopt, steps};
    }

    auto [etaEasy, etaHard, nShaftEasy, nShaftHard, nMotorReq, effOk, effSteps] =
        verifyEfficiency(fanInterpolated, *uEasy, hEasy, *uHard, hHard, qEasy, qHard, etaMin, etaT, kN);
    steps.insert(steps.end(), effSteps.begin(), effSteps.end());

    if (!effOk) {
        steps.push_back("reject: efficiency below threshold");
        return {std::nullopt, steps};
    }
    if (fan.totalMotorKw() < nMotorReq) {
        steps.push_back("reject: installed motor power is insufficient");
        return {std::nullopt, steps};
    }

    auto [score, scoreSteps] = scoreCandidate(etaEasy, etaHard, nShaftHard, fan.totalMotorKw());
    steps.insert(steps.end(), scoreSteps.begin(), scoreSteps.end());

    SelectionCandidate candidate;
    candidate.fan = fan;
    candidate.qOpEasy = qEasy;
    candidate.hOpEasy = hEasy;
    candidate.qOpHard = qHard;
    candidate.hOpHard = hHard;
    candidate.baseQEasy = *uEasy;
    candidate.baseHEasy = rEasy * (*uEasy) * (*uEasy);
    candidate.baseQHard = *uHard;
    candidate.baseHHard = rHard * (*uHard) * (*uHard);
    candidate.etaEasy = etaEasy;
    candidate.etaHard = etaHard;
    candidate.nShaftEasy = nShaftEasy;
    candidate.nShaftHard = nShaftHard;
    candidate.nMotorReq = nMotorReq;
    candidate.nRatio = nHardRpm / nEasyRpm;
    candidate.nEasyRpm = nEasyRpm;
    candidate.nHardRpm = nHardRpm;
    candidate.powerMargin = (fan.totalMotorKw() - nShaftHard) / fan.totalMotorKw() * 100.0;
    candidate.score = score;
    candidate.steps = steps;

    steps.push_back("pass: score=" + fmt(score, 4));
    return {candidate, steps};
}

SelectorResult runSelector(
    const DualPeriodResult& dualResult,
    double etaMin,
    double etaT,
    double kN,
    const std::vector<FanModel>* fans
) {
    const auto& sourceFans = fans ? *fans : fanDb();

    const double qEasy = dualResult.easy.qFMs;
    const double hEasy = dualResult.easy.hF;
    const double rEasy = dualResult.easy.r;
    const double qHard = dualResult.hard.qFMs;
    const double hHard = dualResult.hard.hF;
    const double rHard = dualResult.hard.r;

    SelectorResult result;
    result.steps = {
        "fan selection start",
        "easy Q=" + fmt(qEasy, 3) + ", H=" + fmt(hEasy, 1) + ", R=" + fmt(rEasy, 6),
        "hard Q=" + fmt(qHard, 3) + ", H=" + fmt(hHard, 1) + ", R=" + fmt(rHard, 6),
    };

    auto [passedFans, rejectedFans, screenSteps] =
        screenByRange(sourceFans, qEasy, hEasy, qHard, hHard);
    result.steps.insert(result.steps.end(), screenSteps.begin(), screenSteps.end());
    result.screenedOut = static_cast<int>(rejectedFans.size());

    for (const auto& fan : passedFans) {
        auto [candidate, steps] = evaluateOne(
            fan,
            rEasy,
            qEasy,
            hEasy,
            rHard,
            qHard,
            hHard,
            etaMin,
            etaT,
            kN
        );
        result.steps.insert(result.steps.end(), steps.begin(), steps.end());
        if (candidate.has_value()) {
            result.candidates.push_back(*candidate);
        } else {
            result.rejectedEff += 1;
        }
    }

    std::sort(result.candidates.begin(), result.candidates.end(), [](const auto& a, const auto& b) {
        return a.score > b.score;
    });

    if (!result.candidates.empty()) {
        result.best = result.candidates.front();
    }

    result.steps.push_back(
        "summary total=" + std::to_string(sourceFans.size()) +
        ", screened_out=" + std::to_string(result.screenedOut) +
        ", rejected_after_screen=" + std::to_string(result.rejectedEff) +
        ", candidates=" + std::to_string(result.candidates.size())
    );

    return result;
}

}  // namespace fanselect
