"""Central configuration: factor definitions, default weights, caps, thresholds.

Everything that influences a star value lives in this one file, on purpose.
If a number here changes, INDEX_VERSION must change too (see CHANGELOG.md).
"""

from __future__ import annotations

INDEX_VERSION = "1.1.0"
SCHEMA_VERSION = "1.0"

# ---------------------------------------------------------------------------
# The six factors of the magnitude axis
# ---------------------------------------------------------------------------
FACTORS = ("reach", "duration", "intensity", "spillover", "behavior", "authority")

# Default weights. Must sum to 1.0 (asserted at import time).
# Rationale for each weight is in METHODOLOGY.md#weight-rationale
DEFAULT_WEIGHTS = {
    "reach": 0.22,
    "duration": 0.18,
    "intensity": 0.15,
    "spillover": 0.15,
    "behavior": 0.15,
    "authority": 0.15,
}

FACTOR_META = {
    "reach": {
        "zh": "触达规模",
        "en": "Reach",
        "question": "有多少人可能看到了？",
        "inputs": "话题阅读量、讨论量、热搜条数、跨平台覆盖数",
        "color": "#2f4858",
    },
    "duration": {
        "zh": "持续时间",
        "en": "Duration",
        "question": "这件事烧了多久才凉？",
        "inputs": "有效发酵天数、热度衰减半衰期",
        "color": "#33658a",
    },
    "intensity": {
        "zh": "情感强度",
        "en": "Intensity",
        "question": "情绪有多浓？（不看正负，只看绝对值）",
        "inputs": "逐条情感分的绝对值加权均值",
        "color": "#86bbd8",
    },
    "spillover": {
        "zh": "跨圈层外溢",
        "en": "Spillover",
        "question": "出娱乐版了吗？",
        "inputs": "非娱乐垂类的出现数量与占比",
        "color": "#f6ae2d",
    },
    "behavior": {
        "zh": "行为改变",
        "en": "Behavior change",
        "question": "有人因此改变了行为吗？",
        "inputs": "代言增减、票房/销量变化、机构回应、项目取消",
        "color": "#f26419",
    },
    "authority": {
        "zh": "权威介入",
        "en": "Authority",
        "question": "官方下场了吗？",
        "inputs": "央媒评论、地方官媒、行业协会表态、监管处罚",
        "color": "#b23a48",
    },
}

# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------
# "percentile": robust to outliers, cohort-relative, ordinal.
# "zscore":     normal CDF of the z-score, keeps interval information.
NORMALIZATION_METHODS = ("percentile", "zscore")
DEFAULT_NORMALIZATION = "percentile"

# ---------------------------------------------------------------------------
# Caps for count-like factors, so that one absurd outlier cannot dominate.
# ---------------------------------------------------------------------------
CAPS = {
    "spillover_sum": 1.0,      # normalised spillover is already in [0, 1]
    "behavior_sum": 4.0,       # weighted sum of observable actions, then /cap
    "authority_sum": 4.0,      # weighted sum of interventions, then /cap
    "half_life_days": 30.0,    # censored above 30 days
    "days_active": 90.0,       # censored above the cohort window length
}

# A day counts as "still fermenting" only above this share of the peak daily
# volume. At 10% an artist's ordinary background chatter saturates the metric
# and every artist looks like they fermented for the whole window.
DURATION_ACTIVE_THRESHOLD = 0.25

# ---------------------------------------------------------------------------
# Spillover: which verticals count, and how far from entertainment they are.
# 0.0 = still inside entertainment, higher = further out.
# ---------------------------------------------------------------------------
VERTICAL_WEIGHTS = {
    "entertainment": 0.0,
    "culture": 0.5,
    "sports": 0.8,
    "tech": 0.8,
    "society": 1.0,
    "legal": 1.0,
    "finance": 1.0,
    "politics": 1.2,
}
# raw_spillover = sum(vertical_weight * mention_share), each verified event in
# a vertical not seen in the mentions adds EVENT_VERTICAL_CREDIT * weight.
# The sum is divided by this constant, so "45%+ of the conversation happening
# in the far verticals" reads as a full 1.0.
SPILLOVER_NORMALIZER = 0.45
EVENT_VERTICAL_CREDIT = 0.25

# ---------------------------------------------------------------------------
# Reach
# ---------------------------------------------------------------------------
# The platform universe used for the "breadth" sub-term. Adding a platform
# changes the index, so it is versioned with INDEX_VERSION.
PLATFORM_UNIVERSE = ("weibo", "douyin", "xiaohongshu", "bilibili", "zhihu", "kuaishou")
REACH_SUBWEIGHTS = {
    "reads": 0.40,
    "discussions": 0.25,
    "hotsearch": 0.20,
    "breadth": 0.15,
}
# China's netizen base, used only for the human-readable population proxy.
# Source: CNNIC 55th report (Jan 2025), 1.108 billion. Update when a new
# report lands; it changes only the display string, not the star value.
NETIZEN_BASE = 1_108_000_000

# ---------------------------------------------------------------------------
# Behavior-change action weights (counted from VERIFIED events only)
# ---------------------------------------------------------------------------
BEHAVIOR_ACTION_WEIGHTS = {
    "endorsement_terminated": 0.8,
    "endorsement_added": 0.5,
    "sales_delta_pct": 0.03,       # multiplied by abs(pct change)
    "market_move_pct": 0.04,       # multiplied by abs(pct change), stock/bond
    "production_cancelled": 0.9,
    "institutional_response": 0.8,
    "policy_followup": 1.2,
    "box_office_delta_pct": 0.02,  # multiplied by abs(pct change)
}

# ---------------------------------------------------------------------------
# Authority tiers (counted from VERIFIED events only)
# ---------------------------------------------------------------------------
AUTHORITY_TIER_WEIGHTS = {
    "central_media": 1.5,
    "local_media": 0.7,
    "industry_association": 1.0,
    "regulator": 2.0,
}

# ---------------------------------------------------------------------------
# Sentiment / valence
# ---------------------------------------------------------------------------
# |valence| below this band is displayed as "neutral"; it is NOT folded into
# the star value. Valence never touches the magnitude axis.
VALENCE_NEUTRAL_BAND = 0.15
# Spam / bot filtering: mentions flagged is_spam are excluded from all
# sentiment statistics and reported separately as spam_ratio.
SPAM_EXCLUDED = True

# Confidence interval for valence. Posts are the resampling unit; the seed is
# derived from the artist id, so the interval is reproducible.
# Below min_n we report no interval at all rather than a wide one that looks
# informative.
VALENCE_BOOTSTRAP = {
    "iterations": 400,
    "alpha": 0.05,
    "min_n": 30,
}

# Stability thresholds used by `wii validate`: how far may the ranking move
# when a single weight is nudged by ±5%? Exceeding this is a measurement
# problem, not a weight problem.
STABILITY = {
    "weight_delta": 0.05,
    "max_rank_shift": 2,
    "max_stars_shift": 0.6,
}

# Account weighting for sentiment aggregation.
ACCOUNT_WEIGHTS = {
    "verified_multiplier": 1.6,
    "followers_scale": 6.0,     # log10(1+followers)/scale, capped at 2.0
    "followers_cap": 2.0,
    "min_account_age_days": 90,  # younger accounts are treated as low-trust
    "young_account_multiplier": 0.4,
    "activity_floor": 0.5,
}

# ---------------------------------------------------------------------------
# Star mapping
# ---------------------------------------------------------------------------
STAR_MIN = 1.0
STAR_MAX = 10.0
STAR_DECIMALS = 1


def validate_weights(weights: dict) -> dict:
    """Normalise weights to sum to 1 and check that all factors are covered."""
    missing = set(FACTORS) - set(weights)
    extra = set(weights) - set(FACTORS)
    if missing:
        raise ValueError(f"weights missing factors: {sorted(missing)}")
    if extra:
        raise ValueError(f"weights contain unknown factors: {sorted(extra)}")
    if any(v < 0 for v in weights.values()):
        raise ValueError("weights must be non-negative")
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("weights must sum to a positive number")
    return {k: v / total for k, v in weights.items()}


WEIGHTS = validate_weights(DEFAULT_WEIGHTS)
