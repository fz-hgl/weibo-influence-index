"""Cleaning rules that sit between "LLM said something" and "a table row".

Three jobs, in order:

1. Date normalisation. Baidu Baike gives "2019 年"; news gives "近日" / "昨日";
   a hot search gives an exact timestamp. All of them have to become one ISO
   date, or the timeline is fiction.

2. Deduplication. The same incident is reported by 40 outlets; you want one
   event with 40 sources, not 40 events.

3. Same-day ordering. "3 月 11 日" can hold four different things. Ordering is
   done by (explicitness of time, number of independent sources, publisher
   tier) and the rule is written down here rather than improvised per record.
"""

from __future__ import annotations

import datetime as _dt
import re
import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

TIER_ORDER = {"regulator": 4, "central_media": 3, "industry_association": 2, "local_media": 1}

_RE_FULL_DATE = re.compile(r"(\d{4})\s*[-/年.]\s*(\d{1,2})\s*[-/月.]\s*(\d{1,2})\s*日?")
_RE_MONTH_DAY = re.compile(r"(?<!\d)(\d{1,2})\s*月\s*(\d{1,2})\s*日")
_RE_YEAR_ONLY = re.compile(r"(?<!\d)((?:19|20)\d{2})\s*年(?!\s*\d{1,2}\s*月)")
_RE_TIME = re.compile(r"(?<!\d)(\d{1,2}):(\d{2})")

RELATIVE_DAYS = {
    "今天": 0,
    "今日": 0,
    "当天": 0,
    "昨天": 1,
    "昨日": 1,
    "前天": 2,
    "前日": 2,
}


def normalize_date(text: str, reference: _dt.date) -> Tuple[Optional[_dt.date], str]:
    """Best-effort normalisation. Returns (date, precision).

    precision is one of: day | month_day | year | relative | none.
    A `year`-precision date is *not* silently upgraded to January 1st — the
    caller decides, and the report marks those dots as approximate.
    """
    if not text:
        return None, "none"
    s = unicodedata.normalize("NFKC", str(text)).strip()

    m = _RE_FULL_DATE.search(s)
    if m:
        y, mo, d = (int(g) for g in m.groups())
        try:
            return _dt.date(y, mo, d), "day"
        except ValueError:
            return None, "none"

    m = _RE_MONTH_DAY.search(s)
    if m:
        mo, d = int(m.group(1)), int(m.group(2))
        for year in (reference.year, reference.year - 1):
            try:
                candidate = _dt.date(year, mo, d)
            except ValueError:
                continue
            if candidate <= reference:
                return candidate, "month_day"

    for word, days in RELATIVE_DAYS.items():
        if word in s:
            return reference - _dt.timedelta(days=days), "relative"

    if re.search(r"(近|前)\s*几?日|近日|日前|最近", s):
        # "近日" is officially vague. We map it to reference-3d and mark it,
        # instead of pretending we know.
        return reference - _dt.timedelta(days=3), "relative"

    m = _RE_YEAR_ONLY.search(s)
    if m:
        return _dt.date(int(m.group(1)), 7, 1), "year"

    return None, "none"


def has_explicit_time(text: str) -> bool:
    return bool(_RE_TIME.search(text or ""))


def _norm_title(title: str) -> str:
    s = unicodedata.normalize("NFKC", title or "").lower()
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "", s)
    return s


def _bigrams(s: str) -> set:
    return {s[i : i + 2] for i in range(len(s) - 1)} if len(s) > 1 else {s}


def similar(a: str, b: str) -> float:
    """Character-bigram similarity. Crude, deterministic, no dependencies.

    Jaccard alone punishes short titles: "终止代言合作" vs "终止全部代言合作"
    scores 0.50 even though they are obviously the same incident, because the
    denominator grows with every extra character. So we take the larger of
    Jaccard and containment (|A∩B| / min(|A|,|B|)), which handles "one title is
    a superset of the other" — the usual shape of a re-headline.
    """
    ba, bb = _bigrams(_norm_title(a)), _bigrams(_norm_title(b))
    if not ba or not bb:
        return 0.0
    inter = len(ba & bb)
    jaccard = inter / len(ba | bb)
    containment = inter / min(len(ba), len(bb))
    return max(jaccard, containment)


def dedupe_events(events: Sequence[Dict[str, Any]], threshold: float = 0.62) -> List[Dict[str, Any]]:
    """Merge events that describe the same incident.

    Same artist + same date + title similarity above `threshold` -> merge,
    union the sources, keep the earliest event_id. Behaviour/authority deltas
    are summed because two different outlets reporting the same termination is
    one termination, but two *different* actions on the same day are two
    actions; the title check is what separates the cases.
    """
    kept: List[Dict[str, Any]] = []
    for ev in events:
        merged = False
        for existing in kept:
            if existing.get("artist_id") != ev.get("artist_id") or existing.get("date") != ev.get("date"):
                continue
            if similar(existing["title"], ev["title"]) < threshold:
                continue
            seen = {s.get("url") for s in existing.get("sources", [])}
            for src in ev.get("sources", []):
                if src.get("url") not in seen:
                    existing.setdefault("sources", []).append(src)
                    seen.add(src.get("url"))
            for k, v in (ev.get("behavior") or {}).items():
                existing.setdefault("behavior", {})[k] = existing["behavior"].get(k, 0) + v
            for k, v in (ev.get("authority") or {}).items():
                # Authority interventions are deduped by tier: two outlets
                # carrying the same CMA commentary is one intervention.
                existing.setdefault("authority", {})[k] = max(
                    existing["authority"].get(k, 0), v
                )
            for v in ev.get("verticals", []):
                if v not in existing.setdefault("verticals", []):
                    existing["verticals"].append(v)
            merged = True
            break
        if not merged:
            kept.append(dict(ev))
    return kept


def ordering_key(ev: Dict[str, Any]) -> Tuple:
    sources = ev.get("sources") or []
    best_tier = max(
        (TIER_ORDER.get((s.get("tier") or "outlet"), 0) for s in sources), default=0
    )
    return (
        0 if has_explicit_time(str(ev.get("time") or "")) else 1,
        -len(sources),
        -best_tier,
        ev.get("event_id", ""),
    )


def order_same_day(events: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deterministic ordering so two runs on the same data agree.

    The tie-break chain is: explicit clock time > more independent sources >
    higher publisher tier > event_id. Written down here so a reviewer can
    reproduce the timeline exactly.
    """
    return sorted(events, key=ordering_key)


def drop_sourceless(events: Iterable[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    """The hard gate: no source URL, no row. Counts what it threw away."""
    kept, dropped = [], 0
    for ev in events:
        sources = [
            s
            for s in (ev.get("sources") or [])
            if isinstance(s, dict)
            and str(s.get("url", "")).startswith(("http://", "https://"))
        ]
        if not sources:
            dropped += 1
            continue
        ev = dict(ev)
        ev["sources"] = sources
        kept.append(ev)
    return kept, dropped


def clean_extraction(events: Sequence[Dict[str, Any]], reference: _dt.date) -> Dict[str, Any]:
    """Full cleaning pass; returns the rows plus a report of what changed."""
    rows: List[Dict[str, Any]] = []
    unresolved = 0
    for ev in events:
        ev = dict(ev)
        date, precision = normalize_date(str(ev.get("date_text") or ev.get("date") or ""), reference)
        if date is None:
            unresolved += 1
            continue
        ev["date"] = date.isoformat()
        ev["date_precision"] = precision
        rows.append(ev)

    rows, dropped = drop_sourceless(rows)
    # Count coarseness on the rows that actually survive: the report should
    # describe the table, not the rubbish that was thrown away.
    coarse = sum(1 for ev in rows if ev.get("date_precision") in ("year", "relative"))
    before = len(rows)
    rows = dedupe_events(rows)
    rows = order_same_day(rows)
    return {
        "events": rows,
        "report": {
            "input": len(events),
            "unresolved_dates": unresolved,
            "coarse_dates": coarse,
            "dropped_no_source": dropped,
            "merged_duplicates": before - len(rows),
            "output": len(rows),
        },
    }
