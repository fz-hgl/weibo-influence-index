"""Cross-artist normalisation of factor raw values.

Two methods, both documented, both reversible by hand with a calculator:

percentile
    rank / (n-1), ties get the average rank. Robust to outliers, ordinal.
    Loses the distance between neighbours. This is the default because the
    raw factors have wildly different units (log read counts vs. day counts)
    and one 3-billion-read outlier should not squash everyone else to zero.

zscore
    Phi((x - mean) / sd), i.e. the z-score pushed through the normal CDF so
    it lands in (0, 1). Keeps interval information, assumes rough normality.
"""

from __future__ import annotations

import math
from typing import List, Sequence


def percentile_ranks(values: Sequence[float]) -> List[float]:
    n = len(values)
    if n == 0:
        return []
    if n == 1:
        return [0.5]

    order = sorted(range(n), key=lambda i: values[i])
    out = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0  # 1-based average rank for the tie group
        normalised = (avg_rank - 1.0) / (n - 1.0)
        for k in range(i, j + 1):
            out[order[k]] = normalised
        i = j + 1
    return out


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _stdev(xs: Sequence[float]) -> float:
    if len(xs) < 2:
        return 0.0
    mu = _mean(xs)
    var = sum((x - mu) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(var)


def normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def zscore_ranks(values: Sequence[float]) -> List[float]:
    if not values:
        return []
    mu = _mean(values)
    sd = _stdev(values)
    if sd == 0.0:
        return [0.5] * len(values)
    return [normal_cdf((v - mu) / sd) for v in values]


def normalize(values: Sequence[float], method: str) -> List[float]:
    if method == "percentile":
        return percentile_ranks(values)
    if method == "zscore":
        return zscore_ranks(values)
    raise ValueError(f"unknown normalisation method: {method!r}")


def clip01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x
