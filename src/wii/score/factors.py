"""Raw (pre-normalisation) computation for the six factors.

Every function here returns a number in a documented, human-checkable unit
plus a diagnostics dict. No cross-artist comparison happens at this stage —
that is `normalize.py`'s job. Keeping the two apart is what makes the pipeline
auditable: you can print a single artist's raw factors and verify them by hand
against the platform pages.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

from .. import config
from ..schema import Cohort, Mention
from .stats import bootstrap_mean_ci, weighted_mean, weighted_sd


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _log10p(x: float) -> float:
    return math.log10(1.0 + max(0.0, x))


_weighted_mean = weighted_mean
_weighted_sd = weighted_sd


def daily_volume(mentions: Sequence[Mention], *, exclude_spam: bool = True) -> Dict[str, int]:
    """Mentions per ISO date, deduplicated, spam-filtered."""
    out: Dict[str, int] = defaultdict(int)
    for m in mentions:
        if exclude_spam and m.is_spam:
            continue
        out[m.date.isoformat()] += 1
    return dict(sorted(out.items()))


# ---------------------------------------------------------------------------
# F1 reach
# ---------------------------------------------------------------------------
def raw_reach(cohort: Cohort, artist_id: str) -> Tuple[float, Dict]:
    rows = cohort.metrics_of(artist_id)
    reads = sum(r.reads for r in rows)
    disc = sum(r.discussions for r in rows)
    hot = sum(r.hotsearch_entries for r in rows)
    platforms = {r.platform for r in rows if r.reads > 0 or r.discussions > 0}

    # Different platforms are not additive (a douyin view != a weibo read), so
    # only the *count of platforms reached* enters the formula, not their
    # merged traffic. This is a deliberate under-count, documented in
    # METHODOLOGY.md#known-limits.
    breadth = min(1.0, len(platforms) / len(config.PLATFORM_UNIVERSE))
    sub = config.REACH_SUBWEIGHTS
    value = (
        sub["reads"] * _log10p(reads)
        + sub["discussions"] * _log10p(disc)
        + sub["hotsearch"] * _log10p(hot)
        + sub["breadth"] * breadth
    )
    diagnostics = {
        "total_reads": reads,
        "total_discussions": disc,
        "hotsearch_entries": hot,
        "platforms": sorted(platforms),
        "platform_breadth": round(breadth, 3),
        "log10_reads": round(_log10p(reads), 3),
        "log10_discussions": round(_log10p(disc), 3),
        "log10_hotsearch": round(_log10p(hot), 3),
        "population_proxy_share": round(reads / config.NETIZEN_BASE, 4),
        "population_proxy_note": (
            "话题累计阅读量 / 全国网民规模，是曝光次数的口径代理，不是去重人数。"
            "该值不放大大屏，也不进入星级。"
        ),
    }
    return value, diagnostics


# ---------------------------------------------------------------------------
# F2 duration
# ---------------------------------------------------------------------------
def _linregress(xs: Sequence[float], ys: Sequence[float]) -> Tuple[float, float]:
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return 0.0, my
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx
    return slope, my - slope * mx


def decay_half_life(series: Sequence[int], threshold_ratio: float = 0.05) -> Tuple[float, Dict]:
    """Half-life in days of the post-peak tail, fit on log(volume) ~ day offset.

    Returns (half_life_days, diagnostics). 0.0 means "not fittable"
    (fewer than 3 usable points or no decay at all).
    """
    if not series:
        return 0.0, {"fit_points": 0, "note": "no data"}
    peak_idx = max(range(len(series)), key=lambda i: series[i])
    peak = series[peak_idx]
    if peak <= 0:
        return 0.0, {"fit_points": 0, "note": "empty series"}

    xs: List[float] = []
    ys: List[float] = []
    cutoff = max(1.0, peak * threshold_ratio)
    for i in range(peak_idx, len(series)):
        if series[i] >= cutoff:
            xs.append(float(i - peak_idx))
            ys.append(math.log(series[i]))
    if len(xs) < 3:
        return 0.0, {"fit_points": len(xs), "note": "too few points after peak"}

    slope, _ = _linregress(xs, ys)
    if slope >= -1e-6:
        return config.CAPS["half_life_days"], {
            "fit_points": len(xs),
            "slope": round(slope, 5),
            "note": "no measurable decay inside the window (censored)",
        }
    hl = math.log(2.0) / (-slope)
    hl = min(hl, config.CAPS["half_life_days"])
    return hl, {"fit_points": len(xs), "slope": round(slope, 5)}


def raw_duration(cohort: Cohort, artist_id: str) -> Tuple[float, Dict]:
    volume = daily_volume(cohort.mentions_of(artist_id))
    if not volume:
        return 0.0, {"active_days": 0, "half_life_days": 0.0, "note": "no mentions"}

    dates = sorted(volume)
    series = [volume[d] for d in dates]
    peak = max(series)
    threshold = config.DURATION_ACTIVE_THRESHOLD
    active = sum(1 for v in series if v >= threshold * peak)
    active = min(active, config.CAPS["days_active"])

    hl, hl_diag = decay_half_life(series)
    value = 0.55 * active + 0.45 * hl
    diagnostics = {
        "active_days": active,
        "active_threshold": threshold,
        "half_life_days": round(hl, 2),
        "peak_daily_mentions": peak,
        "first_day": dates[0],
        "last_day": dates[-1],
        "decay_fit": hl_diag,
        "formula": f"0.55 * active_days(≥{threshold:.0%} peak) + 0.45 * half_life_days",
    }
    return value, diagnostics


# ---------------------------------------------------------------------------
# F3 intensity (absolute emotional charge, sign-free)
# ---------------------------------------------------------------------------
def _clean_mentions(cohort: Cohort, artist_id: str) -> List[Mention]:
    return [m for m in cohort.mentions_of(artist_id) if not (config.SPAM_EXCLUDED and m.is_spam)]


def raw_intensity(cohort: Cohort, artist_id: str) -> Tuple[float, Dict]:
    ms = _clean_mentions(cohort, artist_id)
    if not ms:
        return 0.0, {"n": 0}
    pairs = [(abs(m.sentiment), m.weight) for m in ms]
    value = _weighted_mean(pairs)
    strong = sum(1 for m in ms if abs(m.sentiment) >= 0.6) / len(ms)
    diagnostics = {
        "n_mentions": len(ms),
        "weighted_mean_abs_sentiment": round(value, 4),
        "share_strong_sentiment": round(strong, 4),
        "note": "取绝对值均值：骂得很凶和夸得很凶在这里同样计入强度。",
    }
    return value, diagnostics


# ---------------------------------------------------------------------------
# F4 spillover
# ---------------------------------------------------------------------------
def raw_spillover(cohort: Cohort, artist_id: str) -> Tuple[float, Dict]:
    """Weighted share of the conversation that left the entertainment pages.

    Smooth by design: a threshold rule ("a vertical counts only above 5%")
    creates cliffs where one mention flips a factor by several percentiles, and
    cliffs are indistinguishable from noise in the report. Instead every
    vertical contributes in proportion to its share, weighted by how far it is
    from entertainment, then normalised so that roughly 45% weighted share is
    a full 1.0.
    """
    ms = _clean_mentions(cohort, artist_id)
    counts = Counter(m.vertical for m in ms)
    total = sum(counts.values())

    contributions: Dict[str, float] = {}
    for vertical, weight in config.VERTICAL_WEIGHTS.items():
        if vertical == "entertainment" or weight <= 0:
            continue
        share = counts.get(vertical, 0) / total if total else 0.0
        if share > 0:
            contributions[vertical] = round(weight * share, 5)

    # A verified event in a vertical the mentions never reached still counts,
    # at a fraction of a full share: one press release is not a conversation.
    event_verticals = {v for e in cohort.events_of(artist_id) for v in e.verticals if v != "entertainment"}
    for vertical in event_verticals:
        if vertical in contributions:
            continue
        weight = config.VERTICAL_WEIGHTS.get(vertical, 0.0)
        if weight > 0:
            contributions[vertical] = round(weight * config.EVENT_VERTICAL_CREDIT, 5)

    raw_sum = sum(contributions.values())
    value = min(1.0, raw_sum / config.SPILLOVER_NORMALIZER)
    diagnostics = {
        "verticals_reached": sorted(contributions),
        "vertical_contributions": contributions,
        "raw_sum": round(raw_sum, 4),
        "normalizer": config.SPILLOVER_NORMALIZER,
        "vertical_shares": {
            k: round(v / total, 4) for k, v in counts.most_common() if total
        },
        "note": "只对娱乐以外的垂类计分，按垂类距离加权；娱乐版内部吵架不计外溢。",
    }
    return value, diagnostics


# ---------------------------------------------------------------------------
# F5 behavior change (verified events only)
# ---------------------------------------------------------------------------
def raw_behavior(cohort: Cohort, artist_id: str) -> Tuple[float, Dict]:
    events = cohort.events_of(artist_id)
    w = config.BEHAVIOR_ACTION_WEIGHTS
    items: List[Dict] = []
    total = 0.0
    for e in events:
        for action, amount in e.behavior.items():
            if action not in w:
                continue
            multiplier = w[action]
            # Percentage-type actions scale with magnitude, count-type actions
            # scale with the count itself.
            points = multiplier * abs(amount) if action.endswith("_pct") else multiplier * amount
            total += points
            items.append(
                {
                    "event_id": e.event_id,
                    "date": e.date.isoformat(),
                    "action": action,
                    "amount": amount,
                    "points": round(points, 3),
                }
            )
    value = min(1.0, total / config.CAPS["behavior_sum"])
    return value, {
        "items": items,
        "raw_sum": round(total, 3),
        "cap": config.CAPS["behavior_sum"],
        "n_events": len(events),
    }


# ---------------------------------------------------------------------------
# F6 authority
# ---------------------------------------------------------------------------
def raw_authority(cohort: Cohort, artist_id: str) -> Tuple[float, Dict]:
    events = cohort.events_of(artist_id)
    w = config.AUTHORITY_TIER_WEIGHTS
    items: List[Dict] = []
    total = 0.0
    for e in events:
        for tier, count in e.authority.items():
            if tier not in w or count <= 0:
                continue
            points = w[tier] * count
            total += points
            publishers = sorted({s.publisher for s in e.sources if s.publisher})
            items.append(
                {
                    "event_id": e.event_id,
                    "date": e.date.isoformat(),
                    "tier": tier,
                    "count": count,
                    "points": round(points, 3),
                    "publishers": publishers,
                }
            )
    value = min(1.0, total / config.CAPS["authority_sum"])
    return value, {
        "items": items,
        "raw_sum": round(total, 3),
        "cap": config.CAPS["authority_sum"],
        "n_events": len(events),
    }


# ---------------------------------------------------------------------------
# Valence: reported next to the stars, never inside them
# ---------------------------------------------------------------------------
def valence(cohort: Cohort, artist_id: str) -> Tuple[float, float, Dict]:
    """Returns (weighted mean sentiment, weighted sd, diagnostics)."""
    ms = _clean_mentions(cohort, artist_id)
    all_ms = cohort.mentions_of(artist_id)
    if not ms:
        return 0.0, 0.0, {"n": 0, "n_raw": len(all_ms)}

    pairs = [(m.sentiment, m.weight) for m in ms]
    mean = _weighted_mean(pairs)
    sd = _weighted_sd(pairs)
    pos = sum(1 for m in ms if m.sentiment > config.VALENCE_NEUTRAL_BAND) / len(ms)
    neg = sum(1 for m in ms if m.sentiment < -config.VALENCE_NEUTRAL_BAND) / len(ms)
    neu = 1.0 - pos - neg
    spam = len(all_ms) - len(ms)
    lo, hi, ci_diag = bootstrap_mean_ci(
        pairs,
        key=f"valence:{artist_id}",
        iterations=config.VALENCE_BOOTSTRAP["iterations"],
        alpha=config.VALENCE_BOOTSTRAP["alpha"],
        min_n=config.VALENCE_BOOTSTRAP["min_n"],
    )
    diagnostics = {
        "n": len(ms),
        "n_raw": len(all_ms),
        "spam_excluded": spam,
        "spam_ratio": round(spam / len(all_ms), 4) if all_ms else 0.0,
        "share_positive": round(pos, 4),
        "share_neutral": round(neu, 4),
        "share_negative": round(neg, 4),
        "label": valence_label(mean),
        "ci_low": None if lo is None else round(lo, 4),
        "ci_high": None if hi is None else round(hi, 4),
        "ci": ci_diag,
        "note": (
            "情感极性只描述舆论的语调分布，不代表当事人是否做了被指责的事。"
            "负面比例高可能源于大规模谣言。事实请看 events_verified.jsonl。"
            "区间来自对提及的重抽样，只回答「换一批帖子，均值会飘多少」。"
        ),
    }
    return mean, sd, diagnostics


def valence_label(v: float) -> str:
    if v > config.VALENCE_NEUTRAL_BAND:
        return "偏正面"
    if v < -config.VALENCE_NEUTRAL_BAND:
        return "偏负面"
    return "中性 / 撕裂"


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------
@dataclass
class RawFactors:
    artist_id: str
    values: Dict[str, float] = field(default_factory=dict)
    diagnostics: Dict[str, Dict] = field(default_factory=dict)


def compute_raw_cohort(cohort: Cohort) -> Dict[str, RawFactors]:
    out: Dict[str, RawFactors] = {}
    for artist in cohort.artists:
        aid = artist.artist_id
        raw = RawFactors(artist_id=aid)
        for name, fn in (
            ("reach", raw_reach),
            ("duration", raw_duration),
            ("intensity", raw_intensity),
            ("spillover", raw_spillover),
            ("behavior", raw_behavior),
            ("authority", raw_authority),
        ):
            value, diag = fn(cohort, aid)
            raw.values[name] = value
            raw.diagnostics[name] = diag
        out[aid] = raw
    return out
