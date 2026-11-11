"""Lexicon sentiment scorer: deterministic, offline, auditable.

The scorer is deliberately dumb and explainable. For every mention it returns

    value       in [-1, 1]   the polarity
    confidence  in [0, 1]    an informativeness heuristic, NOT a probability
    hits        list         every term that fired, with negation / degree applied
    irony       str | None   which irony marker fired, if any

Two design rules:

1. **No hidden state.** Same text → same score, on any machine, forever.
2. **Every point is attributable.** If a mention scores -0.7, `hits` shows the
   three words that produced it. A scorer you cannot audit is a scorer you
   cannot defend.

Known weaknesses are documented in METHODOLOGY.md §2.3: irony is a rule list,
not a classifier; implicit sarcasm without a marker is missed; word-sense
ambiguity (绝, 强) is resolved by longest-match only.
"""

from __future__ import annotations

import math
import unicodedata
from dataclasses import dataclass, field, replace
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .. import config
from ..schema import Cohort
from . import lexicon as L

# ---------------------------------------------------------------------------
# Term index, built once. Longest first so 不错 beats 不 + 错.
# ---------------------------------------------------------------------------
def _build_index() -> List[Tuple[str, float]]:
    terms: Dict[str, float] = {}
    for table in (L.POSITIVE, L.NEGATIVE, L.NEGATIVE_IDIOMS, L.EMOJI):
        for term, value in table.items():
            terms.setdefault(term, value)
    for term in L.NEUTRAL_TERMS:
        terms.setdefault(term, 0.0)
    return sorted(terms.items(), key=lambda kv: (-len(kv[0]), kv[0]))


TERMS = _build_index()
_DEGREES = sorted(
    list(L.DEGREE_UP.items()) + list(L.DEGREE_DOWN.items()),
    key=lambda kv: -len(kv[0]),
)
_IRONY = sorted(L.IRONY_MARKERS, key=len, reverse=True)
_NEGATORS = sorted(L.NEGATORS, key=len, reverse=True)

NEGATION_DAMPING = 0.75      # 不好 → weaker than 好
NEGATED_NEGATIVE_DAMPING = 0.5  # 不难看 is lukewarm, not enthusiastic
IRONY_DAMPING = 0.85
SATURATION = 0.9


@dataclass
class SentimentScore:
    value: float
    confidence: float
    hits: List[Dict[str, Any]] = field(default_factory=list)
    irony: Optional[str] = None
    text_length: int = 0

    @property
    def label(self) -> str:
        if self.value > config.VALENCE_NEUTRAL_BAND:
            return "positive"
        if self.value < -config.VALENCE_NEUTRAL_BAND:
            return "negative"
        return "neutral"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": round(self.value, 4),
            "confidence": round(self.confidence, 3),
            "label": self.label,
            "irony": self.irony,
            "hits": self.hits,
            "lexicon_version": L.LEXICON_VERSION,
        }


def normalize_text(text: str) -> str:
    """NFKC (full-width → half-width), lower-cased, whitespace collapsed."""
    return " ".join(unicodedata.normalize("NFKC", text).lower().split())


def _find_hits(text: str) -> List[Tuple[int, str, float]]:
    covered = [False] * len(text)
    found: List[Tuple[int, str, float]] = []
    for term, polarity in TERMS:
        start = 0
        while True:
            idx = text.find(term, start)
            if idx < 0:
                break
            end = idx + len(term)
            if not any(covered[idx:end]):
                for k in range(idx, end):
                    covered[k] = True
                found.append((idx, term, polarity))
            start = idx + 1
    found.sort()
    return found


def _negated(text: str, idx: int) -> bool:
    """Is there an odd number of negators in the few characters before idx?

    Scope is 5 characters, which covers 并没有 / 一点也不 but not a negator in
    the previous clause. Double negation is not modelled, and connective forms
    such as 不过 / 不仅 are blanked out first so they cannot flip a term.
    """
    window = text[max(0, idx - 5): idx]
    for phrase in L.NEGATOR_EXCEPTIONS:
        if phrase in window:
            window = window.replace(phrase, "\u3000" * len(phrase))
    count = 0
    pos = 0
    while pos < len(window):
        hit = next((n for n in _NEGATORS if window.startswith(n, pos)), None)
        if hit:
            count += 1
            pos += len(hit)
        else:
            pos += 1
    return count % 2 == 1


def _degree(text: str, idx: int) -> Tuple[float, Optional[str]]:
    """Multiplier from the closest degree adverb, preferring the longest match."""
    window = text[max(0, idx - 6): idx]
    best: Tuple[float, Optional[str]] = (1.0, None)
    best_len = 0
    for word, multiplier in _DEGREES:
        at = window.rfind(word)
        if at < 0:
            continue
        # The adverb must sit adjacent to the term (allow one filler char).
        gap = len(window) - (at + len(word))
        if gap > 1:
            continue
        if len(word) > best_len:
            best, best_len = (multiplier, word), len(word)
    return best


def _irony_marker(text: str) -> Optional[str]:
    scrubbed = text
    for phrase in L.IRONY_EXEMPTIONS:
        scrubbed = scrubbed.replace(phrase, "\u3000" * len(phrase))
    for marker in _IRONY:
        if marker in scrubbed:
            return marker
    return None


def score_text(text: str, *, use_irony: bool = True) -> SentimentScore:
    raw = normalize_text(text or "")
    if not raw:
        return SentimentScore(0.0, 0.0, [], None, 0)

    total = 0.0
    hits: List[Dict[str, Any]] = []
    negated_count = 0

    for idx, term, polarity in _find_hits(raw):
        if polarity == 0.0:  # protective neutral term: claims chars, adds nothing
            continue
        negated = _negated(raw, idx)
        multiplier, adverb = _degree(raw, idx)
        sign_flip = 1.0
        if negated:
            # "不好看" is negative, but "不难看" is merely not-bad. Negating a
            # negative produces a weak positive, never an enthusiastic one.
            sign_flip = -NEGATION_DAMPING if polarity > 0 else -1.0
            if polarity < 0:
                multiplier *= NEGATED_NEGATIVE_DAMPING
        contribution = polarity * multiplier * sign_flip
        total += contribution
        if negated:
            negated_count += 1
        hits.append(
            {
                "term": term,
                "polarity": polarity,
                "negated": negated,
                "degree": round(multiplier, 2),
                "adverb": adverb,
                "contribution": round(contribution, 3),
            }
        )

    irony = _irony_marker(raw) if use_irony else None
    if irony:
        if total > 0.05:
            total = -total * IRONY_DAMPING
        elif total > -0.05:
            total = -0.3  # a bare 呵呵 is dismissive, not neutral
        else:
            total *= 1.0 + (1.0 - IRONY_DAMPING)  # sarcasm sharpens an attack

    value = math.tanh(SATURATION * total)
    confidence = min(1.0, 0.3 + 0.15 * len(hits)) if hits else 0.0
    if irony:
        confidence *= 0.8
    return SentimentScore(
        value=round(value, 4),
        confidence=round(confidence, 3),
        hits=hits,
        irony=irony,
        text_length=len(raw),
    )


# ---------------------------------------------------------------------------
# Table-level helpers
# ---------------------------------------------------------------------------
def score_rows(
    rows: Iterable[Dict[str, Any]],
    *,
    text_key: str = "text",
    use_irony: bool = True,
) -> List[Dict[str, Any]]:
    """Return copies of mention rows with `sentiment` replaced and detail added.

    The original value is preserved under `sentiment_original` so a later audit
    can compare two scorers without re-reading the raw export.
    """
    out: List[Dict[str, Any]] = []
    for row in rows:
        new = dict(row)
        score = score_text(str(row.get(text_key) or ""), use_irony=use_irony)
        new.setdefault("sentiment_original", row.get("sentiment"))
        new["sentiment"] = round(score.value, 4)
        new["sentiment_detail"] = score.to_dict()
        new["sentiment_source"] = f"lexicon-{L.LEXICON_VERSION}"
        out.append(new)
    return out


def rescore_cohort(cohort: Cohort, *, use_irony: bool = True) -> Cohort:
    """Same cohort, with every mention's sentiment recomputed from its text."""
    mentions = [
        replace(m, sentiment=round(score_text(m.text, use_irony=use_irony).value, 4))
        for m in cohort.mentions
    ]
    return Cohort(
        artists=cohort.artists,
        events=cohort.events,
        mentions=mentions,
        metrics=cohort.metrics,
        window_start=cohort.window_start,
        window_end=cohort.window_end,
    )


def summarize(rows: Sequence[Dict[str, Any]], *, neutral_band: Optional[float] = None) -> Dict[str, Any]:
    band = config.VALENCE_NEUTRAL_BAND if neutral_band is None else neutral_band
    n = len(rows)
    if n == 0:
        return {"n": 0, "mean": 0.0, "share_positive": 0.0, "share_neutral": 0.0,
                "share_negative": 0.0, "irony_rate": 0.0, "mean_confidence": 0.0,
                "low_confidence_share": 0.0, "top_terms": []}

    def w(row: Dict[str, Any]) -> float:
        return float(row.get("weight") or 1.0)

    total_w = sum(w(r) for r in rows)
    mean = sum(float(r.get("sentiment") or 0.0) * w(r) for r in rows) / total_w if total_w else 0.0
    pos = sum(w(r) for r in rows if float(r.get("sentiment") or 0.0) > band) / total_w
    neg = sum(w(r) for r in rows if float(r.get("sentiment") or 0.0) < -band) / total_w
    details = [r.get("sentiment_detail") or {} for r in rows]
    irony = sum(1 for d in details if d.get("irony"))
    confs = [float(d.get("confidence") or 0.0) for d in details]
    counts: Dict[str, int] = {}
    for d in details:
        for hit in d.get("hits") or []:
            counts[hit["term"]] = counts.get(hit["term"], 0) + 1
    top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:12]
    return {
        "n": n,
        "mean": round(mean, 4),
        "share_positive": round(pos, 4),
        "share_neutral": round(max(0.0, 1.0 - pos - neg), 4),
        "share_negative": round(neg, 4),
        "irony_rate": round(irony / n, 4),
        "mean_confidence": round(sum(confs) / n, 3),
        "low_confidence_share": round(sum(1 for c in confs if c < 0.5) / n, 4),
        "top_terms": [{"term": t, "count": c} for t, c in top],
    }


def agreement(pairs: Sequence[Tuple[float, float]]) -> Dict[str, Any]:
    """Compare two scorers on the same mentions: MAE + sign agreement."""
    n = len(pairs)
    if n == 0:
        return {"n": 0}
    mae = sum(abs(a - b) for a, b in pairs) / n
    same_sign = sum(
        1 for a, b in pairs
        if (a > 0 and b > 0) or (a < 0 and b < 0) or (abs(a) <= 0.15 and abs(b) <= 0.15)
    )
    both_strong = [(a, b) for a, b in pairs if abs(a) > 0.15 and abs(b) > 0.15]
    polar_agree = sum(1 for a, b in both_strong if (a > 0) == (b > 0))
    return {
        "n": n,
        "mae": round(mae, 4),
        "sign_agreement": round(same_sign / n, 4),
        "clear_polarity_agreement": round(polar_agree / len(both_strong), 4) if both_strong else None,
        "note": "只衡量两套打分的相对一致性，不判断谁更接近真相。",
    }
