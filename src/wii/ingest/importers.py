"""Importers for data you are allowed to have.

This repository deliberately ships **no crawler**.

Not because it would be hard, but because a crawler that mass-collects posts
about named living individuals, combined with a public negative score, is the
exact combination that gets a project of this kind shut down (民法典 1024/1034,
个人信息保护法, and platform ToS). The interesting engineering is downstream of
collection; the collection itself should come from somewhere with a contract.

So the input surface is two boring, auditable formats:

  1. `platform_metrics.csv`
     What a licensed social-listening vendor (清博 / 微热点 / 蝉妈妈 …) or the
     platform's own creator dashboard gives you. Aggregate counters only —
     no personal data.

  2. `mentions.jsonl` in the "bridge" format
     Output of *your own* collector, which you run under whatever arrangement
     you have. We only define the field mapping; we do not ship the collector.

Both are plain text, diffable, and reviewable. If someone challenges a star
value, the answer is a CSV row, not "the crawler said so".
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .weights import account_weight

METRICS_COLUMNS = ("artist_id", "date", "platform", "reads", "discussions", "hotsearch_entries")


def import_metrics_csv(path: Path, platform_default: str = "weibo") -> List[Dict[str, Any]]:
    """Read vendor/dashboard counters. Missing columns default to 0."""
    rows: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = {"artist_id", "date"} - set(reader.fieldnames or [])
        if missing:
            raise ValueError(
                f"{path.name} is missing required column(s) {sorted(missing)}; "
                f"expected at least {METRICS_COLUMNS}"
            )
        for raw in reader:
            rows.append(
                {
                    "artist_id": raw["artist_id"].strip(),
                    "date": raw["date"].strip()[:10],
                    "platform": (raw.get("platform") or platform_default).strip(),
                    "reads": int(float(raw.get("reads") or 0)),
                    "discussions": int(float(raw.get("discussions") or 0)),
                    "hotsearch_entries": int(float(raw.get("hotsearch_entries") or 0)),
                }
            )
    return rows


@dataclass
class BridgeFieldMap:
    """Where each field lives in *your* collector's output."""

    artist_id: str = "artist_id"
    date: str = "created_at"
    platform: str = "platform"
    text: str = "text"
    sentiment: str = "sentiment"
    vertical: str = "vertical"
    followers: str = "followers"
    verified: str = "verified"
    account_age_days: str = "account_age_days"
    activity: str = "activity"
    is_spam: str = "is_spam"
    mention_id: str = "id"


def load_bridge_mentions(
    path: Path,
    mapping: Optional[BridgeFieldMap] = None,
    *,
    default_sentiment: float = 0.0,
) -> List[Dict[str, Any]]:
    """Normalise an external collector's JSONL into our mention table.

    Account weight is recomputed here rather than trusted from upstream, so the
    spam-filtering weights stay inside this repo's audit surface.
    """
    mapping = mapping or BridgeFieldMap()
    out: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path.name}:{lineno}: invalid JSON ({exc})") from exc

            def get(key: str, default: Any = None) -> Any:
                col = getattr(mapping, key)
                return raw.get(col, default)

            sentiment = get("sentiment")
            sentiment = default_sentiment if sentiment is None else float(sentiment)
            sentiment = max(-1.0, min(1.0, sentiment))

            weight = account_weight(
                followers=int(get("followers") or 0),
                verified=bool(get("verified") or False),
                account_age_days=int(get("account_age_days") or 365),
                activity=float(get("activity") or 0.5),
            )
            out.append(
                {
                    "mention_id": str(get("mention_id") or f"{path.stem}-{lineno}"),
                    "artist_id": str(get("artist_id")),
                    "date": str(get("date"))[:10],
                    "platform": str(get("platform") or "weibo"),
                    "sentiment": round(sentiment, 4),
                    "vertical": str(get("vertical") or "entertainment"),
                    "weight": weight,
                    "is_spam": bool(get("is_spam") or False),
                    "text": str(get("text") or ""),
                }
            )
    return out


def stream_filter(records: Iterable[Dict[str, Any]], predicate) -> List[Dict[str, Any]]:
    return [r for r in records if predicate(r)]
