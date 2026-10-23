#pragma once

#include "models.hpp"

#include "fan_selector.pb.h"

namespace fanselect {

fanSelector::CandidateFan candidateToProto(const SelectionCandidate& candidate);

fanSelector::FanSelectionResponse buildSelectionResponse(
    const DualPeriodResult& dual,
    const SelectorResult& result
);

}  // namespace fanselect
