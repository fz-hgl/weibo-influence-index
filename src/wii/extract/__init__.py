"""Extraction layer: text -> structured, dated, sourced event rows."""

from .llm import build_prompt, extract_events, parse_response  # noqa: F401
from .normalizer import (  # noqa: F401
    clean_extraction,
    dedupe_events,
    drop_sourceless,
    normalize_date,
    order_same_day,
    similar,
)
