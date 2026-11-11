"""Data model.

The single most important design rule of this project:

    `VerifiedEvent` and `OpinionMention` are two different tables and are
    never merged into one record.

`VerifiedEvent`  = "something happened, and we can point at a source".
`OpinionMention` = "someone said something, and we scored the tone of it".

An artist can have 900k negative mentions and zero verified wrongdoing.
Folding the two together would turn an attention meter into a defamation
machine. Everything downstream (factors, report, API) reads them separately.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class SchemaError(ValueError):
    """Raised when an input record does not match the documented schema."""


# Verticals are a closed vocabulary: an open one would let a data entry typo
# silently create a new spillover category.
KNOWN_VERTICALS = frozenset(
    {
        "entertainment",
        "culture",
        "sports",
        "tech",
        "society",
        "legal",
        "finance",
        "politics",
    }
)


def _require(d: Dict[str, Any], key: str, kind: type, where: str) -> Any:
    if key not in d:
        raise SchemaError(f"{where}: missing required field '{key}'")
    value = d[key]
    if value is None:
        return None
    if kind is float and isinstance(value, int):
        return float(value)
    if not isinstance(value, kind):
        raise SchemaError(
            f"{where}: field '{key}' should be {kind.__name__}, got {type(value).__name__}"
        )
    return value


def _parse_date(value: Any, where: str) -> _dt.date:
    if isinstance(value, _dt.date):
        return value
    if not isinstance(value, str):
        raise SchemaError(f"{where}: date must be an ISO string, got {type(value).__name__}")
    try:
        return _dt.date.fromisoformat(value[:10])
    except ValueError as exc:
        raise SchemaError(f"{where}: bad date '{value}' ({exc})") from exc


# ---------------------------------------------------------------------------
# Table 0: cohort roster
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Artist:
    artist_id: str
    name: str
    category: str = "unknown"
    fictional: bool = False
    note: str = ""

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Artist":
        return cls(
            artist_id=_require(d, "artist_id", str, "artist"),
            name=_require(d, "name", str, "artist"),
            category=d.get("category", "unknown"),
            fictional=bool(d.get("fictional", False)),
            note=d.get("note", ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artist_id": self.artist_id,
            "name": self.name,
            "category": self.category,
            "fictional": self.fictional,
            "note": self.note,
        }


# ---------------------------------------------------------------------------
# Table 1: verified events (facts with sources)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Source:
    url: str
    publisher: str = ""
    published_at: Optional[str] = None
    tier: str = "unknown"  # central_media | local_media | industry_association | regulator | outlet

    @classmethod
    def from_dict(cls, d: Dict[str, Any], where: str) -> "Source":
        url = _require(d, "url", str, where)
        if not (url.startswith("http://") or url.startswith("https://")):
            raise SchemaError(f"{where}: source url must be absolute http(s), got '{url}'")
        return cls(
            url=url,
            publisher=d.get("publisher", ""),
            published_at=d.get("published_at"),
            tier=d.get("tier", "outlet"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "publisher": self.publisher,
            "published_at": self.published_at,
            "tier": self.tier,
        }


@dataclass(frozen=True)
class VerifiedEvent:
    event_id: str
    artist_id: str
    date: _dt.date
    title: str
    event_type: str
    verticals: List[str]
    sources: List[Source]
    behavior: Dict[str, float] = field(default_factory=dict)
    authority: Dict[str, int] = field(default_factory=dict)
    note: str = ""
    synthetic: bool = False

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "VerifiedEvent":
        where = f"event {d.get('event_id', '<?>')}"
        sources_raw = d.get("sources") or []
        if not sources_raw:
            raise SchemaError(
                f"{where}: a verified event needs at least one source. "
                "Events without a source belong in the narrative layer, not here."
            )
        sources = [Source.from_dict(s, where) for s in sources_raw]
        verticals = list(d.get("verticals") or ["entertainment"])
        unknown = [v for v in verticals if v not in KNOWN_VERTICALS]
        if unknown:
            raise SchemaError(
                f"{where}: unknown vertical(s) {unknown}. "
                f"Known: {sorted(KNOWN_VERTICALS)} (see config.VERTICAL_WEIGHTS)"
            )
        return cls(
            event_id=_require(d, "event_id", str, where),
            artist_id=_require(d, "artist_id", str, where),
            date=_parse_date(d.get("date"), where),
            title=_require(d, "title", str, where),
            event_type=d.get("event_type", "unspecified"),
            verticals=verticals,
            sources=sources,
            behavior={k: float(v) for k, v in (d.get("behavior") or {}).items()},
            authority={k: int(v) for k, v in (d.get("authority") or {}).items()},
            note=d.get("note", ""),
            synthetic=bool(d.get("synthetic", False)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "artist_id": self.artist_id,
            "date": self.date.isoformat(),
            "title": self.title,
            "event_type": self.event_type,
            "verticals": list(self.verticals),
            "sources": [s.to_dict() for s in self.sources],
            "behavior": dict(self.behavior),
            "authority": dict(self.authority),
            "note": self.note,
            "synthetic": self.synthetic,
        }


# ---------------------------------------------------------------------------
# Table 2: opinion mentions (attention + tone, not facts)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Mention:
    mention_id: str
    artist_id: str
    date: _dt.date
    platform: str
    sentiment: float           # -1 .. 1, from the scorer
    vertical: str = "entertainment"
    weight: float = 1.0        # account weight, see config.ACCOUNT_WEIGHTS
    is_spam: bool = False
    text: str = ""

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Mention":
        where = f"mention {d.get('mention_id', '<?>')}"
        sentiment = _require(d, "sentiment", float, where)
        if not -1.0 <= sentiment <= 1.0:
            raise SchemaError(f"{where}: sentiment must be within [-1, 1]")
        weight = float(d.get("weight", 1.0))
        if weight <= 0:
            raise SchemaError(f"{where}: weight must be > 0")
        return cls(
            mention_id=_require(d, "mention_id", str, where),
            artist_id=_require(d, "artist_id", str, where),
            date=_parse_date(d.get("date"), where),
            platform=_require(d, "platform", str, where),
            sentiment=sentiment,
            vertical=d.get("vertical", "entertainment"),
            weight=weight,
            is_spam=bool(d.get("is_spam", False)),
            text=d.get("text", ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mention_id": self.mention_id,
            "artist_id": self.artist_id,
            "date": self.date.isoformat(),
            "platform": self.platform,
            "sentiment": round(self.sentiment, 4),
            "vertical": self.vertical,
            "weight": round(self.weight, 4),
            "is_spam": self.is_spam,
            "text": self.text,
        }


# ---------------------------------------------------------------------------
# Table 3: platform metrics (raw counters from the platform, no opinion)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PlatformMetric:
    artist_id: str
    date: _dt.date
    platform: str = "weibo"
    reads: int = 0
    discussions: int = 0
    hotsearch_entries: int = 0

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PlatformMetric":
        where = f"metric {d.get('artist_id', '<?>')}@{d.get('date', '<?>')}"
        return cls(
            artist_id=_require(d, "artist_id", str, where),
            date=_parse_date(d.get("date"), where),
            platform=d.get("platform", "weibo"),
            reads=int(d.get("reads", 0)),
            discussions=int(d.get("discussions", 0)),
            hotsearch_entries=int(d.get("hotsearch_entries", 0)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artist_id": self.artist_id,
            "date": self.date.isoformat(),
            "platform": self.platform,
            "reads": self.reads,
            "discussions": self.discussions,
            "hotsearch_entries": self.hotsearch_entries,
        }


@dataclass
class Cohort:
    """Everything the scorer needs, already separated by table."""

    artists: List[Artist]
    events: List[VerifiedEvent]
    mentions: List[Mention]
    metrics: List[PlatformMetric]
    window_start: Optional[_dt.date] = None
    window_end: Optional[_dt.date] = None

    def events_of(self, artist_id: str) -> List[VerifiedEvent]:
        return [e for e in self.events if e.artist_id == artist_id]

    def mentions_of(self, artist_id: str) -> List[Mention]:
        return [m for m in self.mentions if m.artist_id == artist_id]

    def metrics_of(self, artist_id: str) -> List[PlatformMetric]:
        return [m for m in self.metrics if m.artist_id == artist_id]
