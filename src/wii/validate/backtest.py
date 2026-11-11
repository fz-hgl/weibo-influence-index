"""Validation: does the index agree with what we already believe?

Two kinds of checks, both declared in an `expectations.json` next to the data:

1. Rank recovery (statistical)
   The synthetic demo dataset carries a *latent* influence value per artist
   that the generator used to produce the raw tables, but that the scorer
   never sees. Spearman / Kendall between recovered stars and that latent
   value measures whether the pipeline can recover a known truth. On a real
   cohort you can instead put an expert-ordered ranking in `latent`.

2. Archetype assertions (semantic)
   Plain-language rules such as "the meltdown case must be >= 7 stars and
   valence < -0.3" or "the scientist's farewell must be top-2 on authority".
   These are the checks that catch a model which is numerically stable but
   substantively wrong.

When a check fails, the fix is to revisit weights or factor definitions —
never to edit the expectation. That rule is the whole reason this file exists.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .. import config
from ..score.index import IndexResult


# ---------------------------------------------------------------------------
# Rank correlation, no numpy in sight
# ---------------------------------------------------------------------------
def _ranks(xs: Sequence[float]) -> List[float]:
    n = len(xs)
    order = sorted(range(n), key=lambda i: xs[i])
    out = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            out[order[k]] = avg
        i = j + 1
    return out


def spearman(xs: Sequence[float], ys: Sequence[float]) -> float:
    if len(xs) != len(ys) or len(xs) < 2:
        return 0.0
    rx, ry = _ranks(xs), _ranks(ys)
    n = len(rx)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = sum((a - mx) ** 2 for a in rx) ** 0.5
    dy = sum((b - my) ** 2 for b in ry) ** 0.5
    if dx == 0 or dy == 0:
        return 0.0
    return num / (dx * dy)


def kendall_tau(xs: Sequence[float], ys: Sequence[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    concordant = discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            a = xs[i] - xs[j]
            b = ys[i] - ys[j]
            if a == 0 or b == 0:
                continue
            if a * b > 0:
                concordant += 1
            else:
                discordant += 1
    total = concordant + discordant
    return (concordant - discordant) / total if total else 0.0


# ---------------------------------------------------------------------------
# Expectations file
# ---------------------------------------------------------------------------
@dataclass
class Check:
    name: str
    passed: bool
    detail: str

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass
class BacktestReport:
    checks: List[Check] = field(default_factory=list)
    spearman: Optional[float] = None
    kendall: Optional[float] = None
    top_k_overlap: Optional[int] = None

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "spearman": None if self.spearman is None else round(self.spearman, 4),
            "kendall": None if self.kendall is None else round(self.kendall, 4),
            "top_k_overlap": self.top_k_overlap,
            "checks": [c.to_dict() for c in self.checks],
        }


def _rank_map(result: IndexResult) -> Dict[str, int]:
    return {a.artist_id: i + 1 for i, a in enumerate(result.ranked())}


def _compare(value: float, op: str, target: float) -> bool:
    return {
        "ge": value >= target,
        "gt": value > target,
        "le": value <= target,
        "lt": value < target,
        "eq": abs(value - target) < 1e-9,
    }.get(op, False)


def _resolve_metric(result: IndexResult, artist_id: str, metric: str) -> float:
    score = result.by_id(artist_id)
    ranks = _rank_map(result)
    if metric == "stars":
        return score.stars
    if metric == "magnitude":
        return score.magnitude
    if metric == "valence":
        return score.valence
    if metric == "rank":
        return float(ranks[artist_id])
    if metric.startswith("percentile."):
        factor = metric.split(".", 1)[1]
        return score.normalized[factor]
    if metric.startswith("raw."):
        factor = metric.split(".", 1)[1]
        return score.raw[factor]
    raise ValueError(f"unknown metric in rule: {metric!r}")


def run_backtest(result: IndexResult, expectations: Dict[str, Any]) -> BacktestReport:
    report = BacktestReport()
    ids = [a.artist_id for a in result.ranked()]

    latent: Dict[str, float] = expectations.get("latent") or {}
    thresholds = expectations.get("thresholds") or {}
    if latent:
        common = [i for i in ids if i in latent]
        if len(common) >= 3:
            recovered = [result.by_id(i).stars for i in common]
            truth = [float(latent[i]) for i in common]
            rho = spearman(recovered, truth)
            tau = kendall_tau(recovered, truth)
            report.spearman, report.kendall = rho, tau

            rho_min = float(thresholds.get("spearman_min", 0.7))
            report.checks.append(
                Check(
                    "rank_recovery.spearman",
                    rho >= rho_min,
                    f"Spearman ρ = {rho:.3f}（阈值 ≥ {rho_min:.2f}，n = {len(common)}）",
                )
            )
            tau_min = float(thresholds.get("kendall_min", 0.5))
            report.checks.append(
                Check(
                    "rank_recovery.kendall",
                    tau >= tau_min,
                    f"Kendall τ = {tau:.3f}（阈值 ≥ {tau_min:.2f}）",
                )
            )

            k = int(thresholds.get("top_k", 3))
            top_recovered = sorted(common, key=lambda i: -result.by_id(i).stars)[:k]
            top_truth = sorted(common, key=lambda i: -float(latent[i]))[:k]
            overlap = len(set(top_recovered) & set(top_truth))
            report.top_k_overlap = overlap
            need = int(thresholds.get("top_k_overlap_min", max(1, k - 1)))
            report.checks.append(
                Check(
                    f"rank_recovery.top{k}",
                    overlap >= need,
                    f"Top-{k} 重合 {overlap}/{k}（要求 ≥ {need}）："
                    f"指数={[result.by_id(i).name for i in top_recovered]}，"
                    f"基准={[result.by_id(i).name for i in top_truth]}",
                )
            )
        else:
            report.checks.append(
                Check("rank_recovery", True, f"latent 只覆盖 {len(common)} 位，样本不足，跳过")
            )

    for rule in expectations.get("rules") or []:
        artist_id = rule.get("artist_id")
        metric = rule.get("metric", "stars")
        op = rule.get("op", "ge")
        target = float(rule.get("value", 0.0))
        label = rule.get("label") or f"{artist_id}.{metric} {op} {target}"
        try:
            value = _resolve_metric(result, artist_id, metric)
        except (KeyError, ValueError) as exc:
            report.checks.append(Check(f"rule:{label}", False, f"无法求值：{exc}"))
            continue
        ok = _compare(value, op, target)
        report.checks.append(
            Check(
                f"rule:{label}",
                ok,
                f"实测 {metric} = {value:.4f}，要求 {op} {target:g}"
                + ("" if ok else "  ← 不符合常识，回去调权重或因子定义"),
            )
        )

    return report


def load_expectations(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def render_text(report: BacktestReport) -> str:
    lines = ["校验结果", "=" * 8]
    head = f"{'PASS' if report.passed else 'FAIL'}  " f"({sum(1 for c in report.checks if c.passed)}/{len(report.checks)} 项通过)"
    lines.append(head)
    for c in report.checks:
        mark = "✓" if c.passed else "✗"
        lines.append(f"  [{mark}] {c.name}: {c.detail}")
    lines.append("")
    lines.append(
        "规则说明：任何一项失败，正确的动作是回去调权重或因子定义，而不是改期望值。"
    )
    return "\n".join(lines)


def weight_sensitivity(
    cohort,
    base_weights: Optional[Dict[str, float]] = None,
    *,
    normalization: str = config.DEFAULT_NORMALIZATION,
    deltas: Sequence[float] = (0.05, -0.05),
) -> List[Dict[str, Any]]:
    """Move each weight by ±delta and report how much the ranking moves.

    A factor whose 5% nudge reshuffles the board is a factor whose measurement
    you should not trust yet. Cheap to compute, and it is the first thing a
    reviewer will ask about.
    """
    from ..score.index import compute_index

    base_weights = base_weights or dict(config.DEFAULT_WEIGHTS)
    base = compute_index(cohort, weights=base_weights, normalization=normalization)
    base_rank = {a.artist_id: i + 1 for i, a in enumerate(base.ranked())}

    rows: List[Dict[str, Any]] = []
    for factor in config.FACTORS:
        worst = 0
        details = []
        for delta in deltas:
            trial = dict(base_weights)
            trial[factor] = max(0.0, trial[factor] + delta)
            res = compute_index(cohort, weights=trial, normalization=normalization)
            trial_rank = {a.artist_id: i + 1 for i, a in enumerate(res.ranked())}
            shift = max(abs(base_rank[i] - trial_rank[i]) for i in base_rank)
            worst = max(worst, shift)
            details.append({"delta": delta, "max_rank_shift": shift})
        rows.append(
            {
                "factor": factor,
                "label_zh": config.FACTOR_META[factor]["zh"],
                "max_rank_shift": worst,
                "trials": details,
                "stable": worst <= 1,
            }
        )
    rows.sort(key=lambda r: -r["max_rank_shift"])
    return rows
