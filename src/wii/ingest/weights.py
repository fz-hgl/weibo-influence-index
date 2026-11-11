"""Account weighting — the cheapest defence against 控评 and 水军.

A raw mention count treats a 10-million-follower verified account and a
two-day-old account that posts 400 times a day as one unit of "public
opinion". They are not.

    w = base * (1.6 if verified)
              * (1 + min(2.0, log10(1+followers)/6))
              * (0.4 if account_age < 90d)
              * (0.5 + min(1.0, activity))

Every multiplier is in config.ACCOUNT_WEIGHTS, so a reviewer can disagree with
one number without touching code. The result is a weight, not a verdict: a
sock puppet still counts as a mention, it just weighs a fifth as much, and its
share is reported as `spam_ratio` rather than being silently deleted.
"""

from __future__ import annotations

import math
from typing import Any, Dict

from .. import config


def account_weight(
    followers: int = 0,
    verified: bool = False,
    account_age_days: int = 365,
    activity: float = 0.5,
) -> float:
    cfg = config.ACCOUNT_WEIGHTS
    w = 1.0
    if verified:
        w *= cfg["verified_multiplier"]
    followers = max(0, int(followers))
    w *= 1.0 + min(
        cfg["followers_cap"], math.log10(1 + followers) / cfg["followers_scale"]
    )
    if account_age_days < cfg["min_account_age_days"]:
        w *= cfg["young_account_multiplier"]
    w *= cfg["activity_floor"] + min(1.0, max(0.0, float(activity)))
    return round(w, 4)


def describe() -> Dict[str, Any]:
    return {
        "formula": "base * verified * followers * age * activity",
        "config": dict(config.ACCOUNT_WEIGHTS),
        "example": {
            "verified_10m_followers_active": account_weight(10_000_000, True, 2000, 0.9),
            "ordinary_300_followers": account_weight(300, False, 1500, 0.6),
            "new_account_spamming": account_weight(5, False, 3, 1.0),
        },
    }
