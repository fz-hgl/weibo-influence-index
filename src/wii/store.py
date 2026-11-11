"""Loading, saving and fingerprinting the four data tables.

Files (all UTF-8, one JSON object per line):

    artists.jsonl           roster
    events_verified.jsonl   facts with sources
    mentions.jsonl          attention + tone
    platform_metrics.jsonl  raw counters

A dataset directory is *self-describing*: `build` reads whatever of these
files exist and tells you which ones were used.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .schema import Artist, Cohort, Mention, PlatformMetric, SchemaError, VerifiedEvent

ARTISTS = "artists.jsonl"
EVENTS = "events_verified.jsonl"
MENTIONS = "mentions.jsonl"
METRICS = "platform_metrics.jsonl"

TABLE_FILES = (ARTISTS, EVENTS, MENTIONS, METRICS)


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SchemaError(f"{path.name}:{lineno}: invalid JSON ({exc})") from exc
    return records


def write_jsonl(path: Path, records: Iterable[Dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True))
            fh.write("\n")
            count += 1
    return count


def load_artists(path: Path) -> List[Artist]:
    return [Artist.from_dict(d) for d in read_jsonl(path)]


def load_events(path: Path) -> List[VerifiedEvent]:
    return [VerifiedEvent.from_dict(d) for d in read_jsonl(path)]


def load_mentions(path: Path) -> List[Mention]:
    return [Mention.from_dict(d) for d in read_jsonl(path)]


def load_metrics(path: Path) -> List[PlatformMetric]:
    return [PlatformMetric.from_dict(d) for d in read_jsonl(path)]


def load_cohort(data_dir: Path, *, require: Tuple[str, ...] = ()) -> Tuple[Cohort, List[str]]:
    """Load every table present in `data_dir`.

    Returns the cohort plus the list of tables actually used, so the report can
    state its own provenance instead of guessing.
    """
    data_dir = Path(data_dir)
    if not data_dir.is_dir():
        raise SchemaError(f"data directory not found: {data_dir}")

    used: List[str] = []
    artists: List[Artist] = []
    events: List[VerifiedEvent] = []
    mentions: List[Mention] = []
    metrics: List[PlatformMetric] = []

    if (data_dir / ARTISTS).is_file():
        artists = load_artists(data_dir / ARTISTS)
        used.append(ARTISTS)
    if (data_dir / EVENTS).is_file():
        events = load_events(data_dir / EVENTS)
        used.append(EVENTS)
    if (data_dir / MENTIONS).is_file():
        mentions = load_mentions(data_dir / MENTIONS)
        used.append(MENTIONS)
    if (data_dir / METRICS).is_file():
        metrics = load_metrics(data_dir / METRICS)
        used.append(METRICS)

    missing = [t for t in require if t not in used]
    if missing:
        raise SchemaError(f"dataset {data_dir} is missing required table(s): {missing}")

    # Derive the window from the data itself when the roster does not say.
    dates = [m.date for m in mentions] + [e.date for e in events] + [m.date for m in metrics]
    window_start = min(dates) if dates else None
    window_end = max(dates) if dates else None

    known = {a.artist_id for a in artists}
    orphans = sorted(
        {r.artist_id for r in [*events, *mentions, *metrics] if r.artist_id not in known}
    )
    if orphans:
        raise SchemaError(
            f"records reference artist_id(s) not in {ARTISTS}: {orphans}. "
            "Add them to the roster or fix the ids."
        )

    cohort = Cohort(
        artists=artists,
        events=events,
        mentions=mentions,
        metrics=metrics,
        window_start=window_start,
        window_end=window_end,
    )
    return cohort, used


def fingerprint(data_dir: Path) -> str:
    """SHA-256 over the data tables, so a star value can be traced to bytes."""
    data_dir = Path(data_dir)
    digest = hashlib.sha256()
    for name in TABLE_FILES:
        path = data_dir / name
        if not path.is_file():
            continue
        digest.update(name.encode("utf-8"))
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                digest.update(chunk)
    return digest.hexdigest()


def utc_now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def dump_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=False)
        fh.write("\n")


def resolve_data_dir(*candidates: str) -> Path:
    """First existing candidate wins; used to keep CLI defaults friendly."""
    env = os.environ.get("WII_DATA_DIR")
    if env:
        return Path(env)
    for c in candidates:
        p = Path(c)
        if p.is_dir():
            return p
    return Path(candidates[0])


def window_label(start: Optional[_dt.date], end: Optional[_dt.date]) -> str:
    if not start or not end:
        return "未知窗口"
    return f"{start.isoformat()} ~ {end.isoformat()}"
