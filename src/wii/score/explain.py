"""Explainability: answer "why 7 stars and not 6?" with arithmetic.

The whole point of the six-factor design is that a star value can be taken
apart. This module produces, for a single artist:

  * each factor's raw value, normalised percentile, weight and contribution;
  * how much of the star total each factor alone accounts for;
  * the marginal sensitivity (stars gained per +0.1 percentile);
  * what it would take to reach the next whole star, and which factor is the
    cheapest single route there.

Nothing here re-runs the model: it only rearranges numbers that are already
in `ArtistScore`, so the explanation can never drift from the score.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .. import config
from .index import ArtistScore, IndexResult

STAR_SPAN = config.STAR_MAX - config.STAR_MIN  # 9


def _fmt_raw(factor: str, raw: float, diag: Dict[str, Any]) -> str:
    if factor == "reach":
        return (
            f"阅读 {diag.get('total_reads', 0):,} / 讨论 {diag.get('total_discussions', 0):,} / "
            f"热搜 {diag.get('hotsearch_entries', 0)} 条 / {len(diag.get('platforms', []))} 平台"
        )
    if factor == "duration":
        return f"有效发酵 {diag.get('active_days', 0)} 天 / 衰减半衰期 {diag.get('half_life_days', 0)} 天"
    if factor == "intensity":
        return f"情感强度 |s| 加权均值 {diag.get('weighted_mean_abs_sentiment', 0):.3f}"
    if factor == "spillover":
        vs = diag.get("verticals_reached") or ["无"]
        return "外溢到：" + "、".join(vs)
    if factor == "behavior":
        n = len(diag.get("items") or [])
        return f"{n} 项可观测行为改变（代言/票房/机构回应…）"
    if factor == "authority":
        n = len(diag.get("items") or [])
        return f"{n} 次权威介入（央媒/协会/监管）"
    return f"{raw:.3f}"


def explain_artist(score: ArtistScore, weights: Dict[str, float]) -> Dict[str, Any]:
    order = sorted(config.FACTORS, key=lambda f: -score.contribution[f])
    rows: List[Dict[str, Any]] = []
    for f in order:
        meta = config.FACTOR_META[f]
        w = weights[f]
        n = score.normalized[f]
        c = score.contribution[f]
        rows.append(
            {
                "factor": f,
                "label_zh": meta["zh"],
                "label_en": meta["en"],
                "question": meta["question"],
                "raw_value": round(score.raw[f], 4),
                "raw_display": _fmt_raw(f, score.raw[f], score.factors_diag.get(f, {})),
                "percentile": round(n, 4),
                "weight": round(w, 4),
                "contribution": round(c, 4),
                "contribution_pct": round(c / score.magnitude * 100, 2) if score.magnitude else 0.0,
                "star_equivalent": round(STAR_SPAN * c, 3),
                "stars_per_0_1_percentile": round(STAR_SPAN * w * 0.1, 4),
            }
        )

    # Distance to the next whole star. Displayed stars are rounded to 1 decimal,
    # so "next star" means the next integer boundary above the current value.
    next_star = min(config.STAR_MAX, float(int(score.stars) + 1))
    delta_m = (next_star - score.stars) / STAR_SPAN
    routes: List[Dict[str, Any]] = []
    for f in config.FACTORS:
        w = weights[f]
        need = delta_m / w if w > 0 else float("inf")
        feasible = need <= (1.0 - score.normalized[f]) + 1e-9
        routes.append(
            {
                "factor": f,
                "label_zh": config.FACTOR_META[f]["zh"],
                "required_percentile_gain": round(need, 4) if need != float("inf") else None,
                "feasible": feasible,
            }
        )
    feasible_routes = [r for r in routes if r["feasible"] and r["required_percentile_gain"]]
    feasible_routes.sort(key=lambda r: r["required_percentile_gain"])

    return {
        "artist": score.name,
        "artist_id": score.artist_id,
        "stars": score.stars,
        "magnitude": round(score.magnitude, 4),
        "valence": round(score.valence, 4),
        "valence_ci": {"low": score.valence_ci_low, "high": score.valence_ci_high},
        "valence_label": score.valence_diag.get("label"),
        "arithmetic": {
            "formula": "stars = 1 + 9 * sum(weight_i * percentile_i)",
            "magnitude": round(score.magnitude, 4),
            "check": round(config.STAR_MIN + STAR_SPAN * score.magnitude, 4),
            "one_star_equals_magnitude": round(1.0 / STAR_SPAN, 4),
            "note": "星级每涨 1 星，需要合成幅度提高 1/9 ≈ 0.1111；这张表说明这 0.1111 从哪来。",
        },
        "factors": rows,
        "dominant_factor": rows[0]["factor"] if rows else None,
        "next_star": {
            "current": score.stars,
            "target": next_star,
            "required_magnitude_gain": round(delta_m, 4),
            "cheapest_single_factor_route": feasible_routes[0] if feasible_routes else None,
            "all_routes": routes,
        },
    }


def explain_index(result: IndexResult, artist_id: Optional[str] = None) -> Dict[str, Any]:
    if artist_id:
        return explain_artist(result.by_id(artist_id), result.weights)
    return {
        "index_version": result.index_version,
        "weights": result.weights,
        "normalization": result.normalization,
        "artists": [explain_artist(a, result.weights) for a in result.ranked()],
    }


def render_text(explanation: Dict[str, Any]) -> str:
    """Plain-text rendering for the CLI."""
    lines: List[str] = []
    ci = explanation.get("valence_ci") or {}
    ci_txt = (
        f"，95% 区间 [{ci['low']:+.2f}, {ci['high']:+.2f}]"
        if ci.get("low") is not None and ci.get("high") is not None
        else "，样本不足未给区间"
    )
    head = (
        f"{explanation['artist']}  →  {explanation['stars']:.1f} 星"
        f"（合成幅度 {explanation['magnitude']:.4f}，极性 {explanation['valence']:+.3f}"
        f" {explanation.get('valence_label') or ''}{ci_txt}）"
    )
    lines.append(head)
    lines.append("=" * len(head))
    lines.append(f"{'因子':<10}{'权重':>6}{'归一':>8}{'贡献':>8}{'占星级':>8}  原始量")
    for row in explanation["factors"]:
        lines.append(
            f"{row['label_zh']:<10}{row['weight']:>6.2f}{row['percentile']:>8.3f}"
            f"{row['contribution']:>8.3f}{row['star_equivalent']:>8.2f}  {row['raw_display']}"
        )
    lines.append(
        f"{'合计':<10}{sum(r['weight'] for r in explanation['factors']):>6.2f}"
        f"{'':>8}{explanation['magnitude']:>8.3f}"
        f"{STAR_SPAN * explanation['magnitude']:>8.2f}"
    )
    nxt = explanation["next_star"]
    lines.append("")
    if nxt["required_magnitude_gain"] > 0:
        lines.append(
            f"距离 {nxt['target']:.0f} 星还差 Δ幅度 {nxt['required_magnitude_gain']:.4f}。"
        )
        route = nxt.get("cheapest_single_factor_route")
        if route:
            lines.append(
                f"单因子最省路径：把「{route['label_zh']}」的百分位再提高 "
                f"{route['required_percentile_gain']:.3f}。"
            )
        else:
            lines.append("没有任何单一因子能在当前数据下补足这个差额，需要多因子一起动。")
    else:
        lines.append("已在星级上限。")
    return "\n".join(lines)
