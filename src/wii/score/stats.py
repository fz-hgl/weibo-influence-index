"""Statistics that fit in a diff.

No numpy, no scipy: weighted means, a percentile function, and a seeded
bootstrap. The bootstrap is the only inferential tool in this repository, and
it is used for exactly one number — the sentiment polarity — because that is
the one number built by *sampling posts*, where resampling is defensible.

It is deliberately NOT used for reach: platform read counts are a census-like
counter with repeated exposure, not a sample. Attaching a confidence interval
to them would be fake precision (see METHODOLOGY.md §2.1 and §7).
"""

from __future__ import annotations

import math
import random
import zlib
from typing import Any, Dict, List, Optional, Sequence, Tuple


def weighted_mean(pairs: Sequence[Tuple[float, float]]) -> float:
    num = sum(v * w for v, w in pairs)
    den = sum(w for _, w in pairs)
    return num / den if den else 0.0


def weighted_sd(pairs: Sequence[Tuple[float, float]]) -> float:
    """Population-style weighted sd (documented as such in METHODOLOGY)."""
    mu = weighted_mean(pairs)
    num = sum(w * (v - mu) ** 2 for v, w in pairs)
    den = sum(w for _, w in pairs)
    if den <= 0 or len(pairs) < 2:
        return 0.0
    return math.sqrt(num / den)


def percentile(sorted_values: Sequence[float], q: float) -> float:
    """Linear-interpolation percentile on an already sorted sequence, q in [0,1]."""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    pos = q * (len(sorted_values) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return float(sorted_values[lo])
    frac = pos - lo
    return float(sorted_values[lo]) * (1.0 - frac) + float(sorted_values[hi]) * frac


def _seed_from(key: str) -> int:
    return zlib.crc32(key.encode("utf-8")) & 0xFFFFFFFF


def bootstrap_mean_ci(
    pairs: Sequence[Tuple[float, float]],
    *,
    key: str,
    iterations: int = 400,
    alpha: float = 0.05,
    min_n: int = 30,
) -> Tuple[Optional[float], Optional[float], Dict[str, Any]]:
    """Percentile bootstrap CI for a weighted mean over posts.

    Resampling unit is the post (cluster bootstrap): we draw n posts with
    replacement and recompute the weighted mean, so account weights are kept
    attached to their post. Seed is derived from `key` so the interval is
    reproducible from the artist id alone — a report screenshot stays checkable.
    """
    n = len(pairs)
    if n < min_n:
        return None, None, {
            "method": "cluster bootstrap (percentile)",
            "iterations": 0,
            "note": f"样本 {n} 条 < {min_n}，不给区间：样本太小时区间只会假装精确。",
        }

    rng = random.Random(_seed_from(key))
    means: List[float] = []
    for _ in range(iterations):
        sample = [pairs[rng.randrange(n)] for _ in range(n)]
        means.append(weighted_mean(sample))
    means.sort()
    lo = percentile(means, alpha / 2.0)
    hi = percentile(means, 1.0 - alpha / 2.0)
    return lo, hi, {
        "method": "cluster bootstrap (percentile)",
        "iterations": iterations,
        "alpha": alpha,
        "seed": _seed_from(key),
        "n": n,
        "note": "重抽样单位是「单条提及」；账号权重随提及一起移动。",
    }
