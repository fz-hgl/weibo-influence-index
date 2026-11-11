"""Offline sentiment scoring (lexicon + negation + degree + irony rules).

Import surface:

    from wii.sentiment import score_text, score_rows, rescore_cohort

Everything here is deterministic and dependency-free. It is a *baseline*: on
real data, compare it against your model with `wii sentiment --compare` rather
than assuming either is right.
"""

from __future__ import annotations

from .lexicon import LEXICON_VERSION
from .scorer import (
    SentimentScore,
    agreement,
    rescore_cohort,
    score_rows,
    score_text,
    summarize,
)

__all__ = [
    "LEXICON_VERSION",
    "SentimentScore",
    "agreement",
    "rescore_cohort",
    "score_rows",
    "score_text",
    "summarize",
]
