#include "converters.hpp"

#include "fan_db.hpp"

namespace fanselect {

fanSelector::CandidateFan candidateToProto(const SelectionCandidate& candidate) {
    fanSelector::CandidateFan out;
    out.set_modelid(candidate.fan.modelId);
    out.set_ratedrpm(candidate.fan.ratedRpm);
    out.set_motorpower(candidate.fan.motorKw);
    out.set_motorcount(candidate.fan.motorCount);
    out.set_floweasy(candidate.qOpEasy);
    out.set_presseasy(candidate.hOpEasy);
    out.set_flowhard(candidate.qOpHard);
    out.set_presshard(candidate.hOpHard);
    out.set_efficiencyeasy(candidate.etaEasy);
    out.set_efficiencyhard(candidate.etaHard);
    out.set_shaftpowereasy(candidate.nShaftEasy);
    out.set_shaftpowerhard(candidate.nShaftHard);
    out.set_requiredpower(candidate.nMotorReq);
    out.set_speedratio(candidate.nRatio);
    out.set_rpmeasy(candidate.nEasyRpm);
    out.set_rpmhard(candidate.nHardRpm);
    out.set_powermargin(candidate.powerMargin);
    out.set_score(candidate.score);
    out.set_basefloweasy(candidate.baseQEasy);
    out.set_basepresseasy(candidate.baseHEasy);
    out.set_baseflowhard(candidate.baseQHard);
    out.set_basepresshard(candidate.baseHHard);
    out.set_bladeangledeg(candidate.fan.bladeAngleDeg);
    out.set_railwidthmm(candidate.fan.railWidthMm);
    out.set_imagepath(candidate.fan.imagePath);
    out.set_manufacturer(candidate.fan.manufacturer);
    out.set_productname(candidate.fan.productName);
    out.set_productspec(candidate.fan.productSpec);
    out.set_motormodel(candidate.fan.motorModel);
    out.set_factoryno(candidate.fan.factoryNo);
    auto* plot = out.mutable_plotdata();
    plot->set_ratedrpm(candidate.fan.ratedRpm);
    plot->set_rpmmin(candidate.fan.rpmRange.first);
    plot->set_rpmmax(candidate.fan.rpmRange.second);
    for (const auto& point : candidate.fan.curvePoints) {
        auto* cp = plot->add_curvepoints();
        cp->set_q(point.q);
        cp->set_h(point.h);
        cp->set_eta(point.eta);
    }
    return out;
}

fanSelector::FanSelectionResponse buildSelectionResponse(
    const DualPeriodResult& dual,
    const SelectorResult& result
) {
    fanSelector::FanSelectionResponse response;

    auto* easy = response.mutable_easy();
    easy->set_flowrate(dual.easy.qFMs);
    easy->set_pressure(dual.easy.hF);
    easy->set_resistance(dual.easy.r);

    auto* hard = response.mutable_hard();
    hard->set_flowrate(dual.hard.qFMs);
    hard->set_pressure(dual.hard.hF);
    hard->set_resistance(dual.hard.r);

    response.set_totalfans(static_cast<int>(fanDb().size()));
    response.set_screenedout(result.screenedOut);
    response.set_rejectedbyeff(result.rejectedEff);

    for (const auto& candidate : result.candidates) {
        *response.add_candidates() = candidateToProto(candidate);
    }

    for (const auto& step : result.steps) {
        response.add_steps(step);
    }

    response.set_code(200);
    response.set_msg("success");

    return response;
}

}  // namespace fanselect
