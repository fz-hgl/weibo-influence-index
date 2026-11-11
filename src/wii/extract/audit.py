"""Human spot-check loop.

An LLM extractor without an accuracy number is a rumour generator. The rule
for this project: sample at least 100 extracted events, label them by hand,
publish the accuracy in the report. This module makes that loop mechanical
instead of aspirational.

    1. wii audit-sample --data data/demo --n 100        -> review.csv
    2. open review.csv, fill the `verdict` column
    3. wii audit-score --csv review.csv                 -> accuracy.json

Verdict vocabulary (keep it small so the numbers mean something):
    ok           事件真实存在，时间与标题都与来源一致
    bad_date     事件存在但时间错
    bad_title    事件存在但描述失真（把指控写成了事实等）
    no_source    给出的链接打不开或与内容无关
    fabricated   来源里没有这件事
"""

from __future__ import annotations

import csv
import random
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

FIELDS = [
    "event_id",
    "artist_id",
    "date",
    "title",
    "event_type",
    "verticals",
    "source_url",
    "synthetic",
    "verdict",
    "reviewer_note",
]

VERDICTS = ("ok", "bad_date", "bad_title", "no_source", "fabricated")


def sample_for_review(
    events: Sequence[Dict[str, Any]], n: int = 100, seed: int = 7
) -> List[Dict[str, Any]]:
    rows = list(events)
    rng = random.Random(seed)
    if len(rows) > n:
        rows = rng.sample(rows, n)
    out: List[Dict[str, Any]] = []
    for ev in rows:
        sources = ev.get("sources") or [{}]
        out.append(
            {
                "event_id": ev.get("event_id", ""),
                "artist_id": ev.get("artist_id", ""),
                "date": ev.get("date", ""),
                "title": ev.get("title", ""),
                "event_type": ev.get("event_type", ""),
                "verticals": "|".join(ev.get("verticals") or []),
                "source_url": sources[0].get("url", ""),
                "synthetic": ev.get("synthetic", False),
                "verdict": "",
                "reviewer_note": "",
            }
        )
    out.sort(key=lambda r: (r["artist_id"], r["date"], r["event_id"]))
    return out


def write_review_csv(path: Path, rows: Sequence[Dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return len(rows)


def read_review_csv(path: Path) -> List[Dict[str, str]]:
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        return [dict(r) for r in csv.DictReader(fh)]


def score_review(rows: Sequence[Dict[str, str]]) -> Dict[str, Any]:
    labelled = [r for r in rows if (r.get("verdict") or "").strip()]
    if not labelled:
        return {
            "labelled": 0,
            "pending": len(rows),
            "message": "还没有任何标注；accuracy 无法计算，请不要对外声称有准确率。",
        }
    counter = Counter((r["verdict"] or "").strip() for r in labelled)
    ok = counter.get("ok", 0)
    unknown = {k: v for k, v in counter.items() if k not in VERDICTS}
    return {
        "labelled": len(labelled),
        "pending": len(rows) - len(labelled),
        "accuracy": round(ok / len(labelled), 4),
        "accuracy_wilson_95": precision_interval(ok, len(labelled)),
        "by_verdict": dict(counter),
        "unknown_verdicts": unknown,
        "thresholds": {
            "ship_if_accuracy_at_least": 0.9,
            "note": "低于 0.9 先改 prompt / 换模型 / 加规则，不要改标注。",
        },
    }


def coverage_by_artist(events: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    return dict(Counter(e.get("artist_id", "") for e in events))


def precision_interval(ok: int, n: int, z: float = 1.96) -> Optional[List[float]]:
    """Wilson score interval — 100 samples is small, so report the interval."""
    if n <= 0:
        return None
    p = ok / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / denom
    return [round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)]
