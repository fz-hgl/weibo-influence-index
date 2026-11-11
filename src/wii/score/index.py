"""Compose the six normalised factors into a magnitude score and 1-10 stars.

The contract:

    M        = sum_i w_i * n_i          in [0, 1]
    stars    = 1 + 9 * M                in [1, 10]
    valence  = weighted mean sentiment  in [-1, 1]   <- separate axis

Stars are *relative to the cohort and window* they were computed on. Two
runs on different cohorts are not comparable; the report prints the cohort,
the window and a SHA-256 of the data so that no one can quietly compare
across them.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .. import config
from ..schema import Cohort
from . import factors as F
from .normalize import normalize


@dataclass
class ArtistScore:
    artist_id: str
    name: str
    raw: Dict[str, float]
    normalized: Dict[str, float]
    contribution: Dict[str, float]
    magnitude: float
    stars: float
    valence: float
    valence_sd: float
    factors_diag: Dict[str, Dict]
    valence_diag: Dict[str, Any]
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def stars_rounded(self) -> int:
        return int(round(self.stars))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artist_id": self.artist_id,
            "name": self.name,
            "stars": self.stars,
            "stars_display": f"{self.stars:.1f}",
            "magnitude": round(self.magnitude, 4),
            "valence": round(self.valence, 4),
            "valence_sd": round(self.valence_sd, 4),
            "valence_label": self.valence_diag.get("label"),
            "raw": {k: round(v, 4) for k, v in self.raw.items()},
            "normalized": {k: round(v, 4) for k, v in self.normalized.items()},
            "contribution": {k: round(v, 4) for k, v in self.contribution.items()},
            "factors": self.factors_diag,
            "valence_detail": self.valence_diag,
            "evidence": self.evidence,
            "meta": self.meta,
        }


@dataclass
class IndexResult:
    index_version: str
    normalization: str
    weights: Dict[str, float]
    cohort_label: str
    window_start: Optional[_dt.date]
    window_end: Optional[_dt.date]
    data_fingerprint: str
    tables_used: List[str]
    generated_at: str
    artists: List[ArtistScore]
    notes: List[str] = field(default_factory=list)

    def ranked(self) -> List[ArtistScore]:
        return sorted(self.artists, key=lambda a: (-a.stars, a.name))

    def by_id(self, artist_id: str) -> ArtistScore:
        for a in self.artists:
            if a.artist_id == artist_id:
                return a
        raise KeyError(artist_id)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index_version": self.index_version,
            "normalization": self.normalization,
            "weights": self.weights,
            "cohort": self.cohort_label,
            "window": {
                "start": self.window_start.isoformat() if self.window_start else None,
                "end": self.window_end.isoformat() if self.window_end else None,
            },
            "data_fingerprint": self.data_fingerprint,
            "tables_used": self.tables_used,
            "generated_at": self.generated_at,
            "notes": self.notes,
            "artists": [a.to_dict() for a in self.ranked()],
        }


def stars_from_magnitude(magnitude: float) -> float:
    m = 0.0 if magnitude < 0 else 1.0 if magnitude > 1 else magnitude
    stars = config.STAR_MIN + (config.STAR_MAX - config.STAR_MIN) * m
    return round(stars, config.STAR_DECIMALS)


def compute_index(
    cohort: Cohort,
    *,
    weights: Optional[Dict[str, float]] = None,
    normalization: str = config.DEFAULT_NORMALIZATION,
    cohort_label: str = "",
    fingerprint: str = "",
    tables_used: Optional[List[str]] = None,
    generated_at: str = "",
) -> IndexResult:
    if not cohort.artists:
        raise ValueError("cohort has no artists; nothing to score")
    if not cohort.mentions and not cohort.metrics:
        raise ValueError(
            "cohort has neither mentions nor platform_metrics; "
            "reach/duration/intensity cannot be computed"
        )
    if normalization not in config.NORMALIZATION_METHODS:
        raise ValueError(f"normalization must be one of {config.NORMALIZATION_METHODS}")

    weights = config.validate_weights(weights or config.DEFAULT_WEIGHTS)

    raw_all = F.compute_raw_cohort(cohort)

    # Normalise factor by factor across the cohort.
    normalized: Dict[str, Dict[str, float]] = {aid: {} for aid in raw_all}
    for factor in config.FACTORS:
        series = [raw_all[a.artist_id].values[factor] for a in cohort.artists]
        ranks = normalize(series, normalization)
        for artist, rank in zip(cohort.artists, ranks):
            normalized[artist.artist_id][factor] = rank

    scores: List[ArtistScore] = []
    for artist in cohort.artists:
        aid = artist.artist_id
        n = normalized[aid]
        contribution = {f: weights[f] * n[f] for f in config.FACTORS}
        magnitude = sum(contribution.values())
        val, val_sd, val_diag = F.valence(cohort, aid)

        events = sorted(cohort.events_of(aid), key=lambda e: e.date)
        evidence = [
            {
                "event_id": e.event_id,
                "date": e.date.isoformat(),
                "title": e.title,
                "event_type": e.event_type,
                "verticals": list(e.verticals),
                "sources": [s.to_dict() for s in e.sources],
                "behavior": e.behavior,
                "authority": e.authority,
                "synthetic": e.synthetic,
            }
            for e in events
        ]

        scores.append(
            ArtistScore(
                artist_id=aid,
                name=artist.name,
                raw=raw_all[aid].values,
                normalized=n,
                contribution=contribution,
                magnitude=magnitude,
                stars=stars_from_magnitude(magnitude),
                valence=val,
                valence_sd=val_sd,
                factors_diag=raw_all[aid].diagnostics,
                valence_diag=val_diag,
                evidence=evidence,
                meta={
                    "category": artist.category,
                    "fictional": artist.fictional,
                    "note": artist.note,
                    "n_verified_events": len(events),
                },
            )
        )

    notes = [
        "星级是「相对指数」：只在同一份 cohort 与同一时间窗内可比。",
        "星级只标在「影响幅度」轴上；情感极性单独用符号与颜色表示。",
        "所有因子原始量与归一后取值均可在 index.json / report.html 中逐项核对。",
    ]
    if any(a.meta.get("fictional") for a in scores):
        notes.append("本数据集含合成人物（fictional=true），仅用于方法演示，不对应真实自然人。")

    return IndexResult(
        index_version=config.INDEX_VERSION,
        normalization=normalization,
        weights=weights,
        cohort_label=cohort_label or f"{len(cohort.artists)} 位艺人",
        window_start=cohort.window_start,
        window_end=cohort.window_end,
        data_fingerprint=fingerprint,
        tables_used=tables_used or [],
        generated_at=generated_at,
        artists=scores,
        notes=notes,
    )
