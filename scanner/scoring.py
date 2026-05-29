"""Turn raw signals into the checklist score.

Each layer is normalized to 0..1, then combined with config.WEIGHTS. The point
of the weighting is to rank by *leading* signals (gov stake, federal revenue)
rather than by the Trump shoutout itself -- chasing the shoutout means chasing
a rally that is usually already over.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List

from . import config


@dataclass
class Candidate:
    company: config.Company
    signals: Dict = field(default_factory=dict)
    layers: Dict[str, float] = field(default_factory=dict)  # 0..1 per layer
    score: float = 0.0                                       # 0..100

    @property
    def ticker(self) -> str:
        return self.company.ticker


def _federal_score(contract_total: float) -> float:
    # log scale: ~$10M -> 0.32, ~$100M -> 0.45, ~$1B -> 0.58, ~$9.7B -> ~0.68
    if contract_total <= 0:
        return 0.0
    return min(1.0, math.log10(contract_total + 1) / 10.5)


def _gov_stake_score(s: Dict) -> float:
    sec = min(1.0, s.get("sec_stake_hits", 0) / 4.0)
    congress = min(1.0, s.get("congress_buys", 0) / 3.0)
    # SEC stake language is the heavier tell; congress buys corroborate.
    return min(1.0, 0.65 * sec + 0.45 * congress)


def _positioning_score(s: Dict) -> float:
    spike = s.get("volume_spike", 1.0)
    spike_score = max(0.0, min(1.0, (spike - 1.0) / 2.0))   # 3x volume -> 1.0
    ret = s.get("ret_1m", 0.0)
    ret_score = max(0.0, min(1.0, ret / 0.30))               # +30% in a month -> 1.0
    options = s.get("options_flow", 0.0)                     # already 0..1
    insider = s.get("insider_buy", 0.0)                      # already 0..1
    holds = 1.0 if s.get("trump_holds") else 0.0             # Trump personally holds this stock
    # Options flow is the strongest positioning tell when present.
    return min(1.0, 0.35 * options + 0.20 * insider + 0.20 * holds + 0.15 * spike_score + 0.10 * ret_score)


def _exec_score(s: Dict) -> float:
    return min(1.0, s.get("exec_praise_hits", 0) / 2.0)


def _trump_score(s: Dict) -> float:
    return min(1.0, s.get("trump_mentions", 0) / 8.0)


def _truth_social_score(s: Dict) -> float:
    # 3 posts mentioning the company -> full score; 1 post -> 0.33
    return min(1.0, s.get("truth_social_hits", 0) / 3.0)


def _ceo_donor_score(s: Dict) -> float:
    # 2+ FEC-recorded donations to Trump committees -> full score
    return min(1.0, s.get("ceo_fec_donations", 0) / 2.0)


def _exec_order_score(s: Dict) -> float:
    # A single EO naming the company is already strong (0.5); 2+ maxes out.
    return min(1.0, s.get("exec_order_hits", 0) / 2.0)


def score_candidate(cand: Candidate) -> Candidate:
    s = cand.signals
    layers = {
        "gov_stake": _gov_stake_score(s),
        "federal_revenue": _federal_score(s.get("contract_total", 0.0)),
        "positioning": _positioning_score(s),
        "exec_alignment": _exec_score(s),
        "exec_order": _exec_order_score(s),
        "trump_mention": _trump_score(s),
        "truth_social": _truth_social_score(s),
        "ceo_donor": _ceo_donor_score(s),
    }
    total = sum(layers[k] * config.WEIGHTS[k] for k in config.WEIGHTS)
    cand.layers = layers
    cand.score = round(total * 100, 1)
    return cand


# Emoji flags for the report -- which layers actually fired.
LAYER_LABELS = {
    "gov_stake": "🏛️ Gov stake",
    "federal_revenue": "📑 Federal $",
    "positioning": "📈 Positioning",
    "exec_alignment": "🤝 Exec aligns",
    "exec_order": "📜 Exec Order",
    "trump_mention": "📣 Trump mention",
    "truth_social": "🔊 Truth Social",
    "ceo_donor": "💰 CEO donor",
}


def fired_layers(cand: Candidate, threshold: float = 0.25) -> List[str]:
    return [LAYER_LABELS[k] for k, v in cand.layers.items() if v >= threshold]
