import datetime as dt

import pytest

from wii.extract.llm import parse_response
from wii.extract.normalizer import (
    clean_extraction,
    dedupe_events,
    drop_sourceless,
    normalize_date,
    order_same_day,
    similar,
)

REF = dt.date(2026, 3, 1)


@pytest.mark.parametrize(
    "text,expected,precision",
    [
        ("2024年3月11日", dt.date(2024, 3, 11), "day"),
        ("2024-03-11", dt.date(2024, 3, 11), "day"),
        ("2024/3/11 20:15", dt.date(2024, 3, 11), "day"),
        ("2月28日", dt.date(2026, 2, 28), "month_day"),
        ("昨日", dt.date(2026, 2, 28), "relative"),
        ("近日", dt.date(2026, 2, 26), "relative"),
        ("2019年", dt.date(2019, 7, 1), "year"),
        ("", None, "none"),
        ("某天", None, "none"),
    ],
)
def test_normalize_date(text, expected, precision):
    date, got_precision = normalize_date(text, REF)
    assert got_precision == precision
    if expected is not None:
        assert date == expected


def test_normalize_date_month_day_rolls_back_a_year():
    date, _ = normalize_date("12月20日", REF)
    assert date == dt.date(2025, 12, 20)


def test_normalize_impossible_date_is_dropped():
    date, precision = normalize_date("2024年2月31日", REF)
    assert date is None and precision == "none"


def test_similar_is_symmetric_and_bounded():
    a = "品牌方宣布终止代言合作"
    b = "品牌方宣布终止全部代言合作"
    assert similar(a, b) == similar(b, a)
    assert 0.5 < similar(a, b) <= 1.0
    assert similar(a, "完全无关的另一个话题内容") < 0.2


def test_dedupe_merges_sources_and_sums_behavior():
    rows = [
        {
            "event_id": "e1",
            "artist_id": "a1",
            "date": "2026-01-05",
            "title": "品牌方宣布终止代言合作",
            "sources": [{"url": "https://x.test/1"}],
            "behavior": {"endorsement_terminated": 1},
            "authority": {"central_media": 1},
            "verticals": ["finance"],
        },
        {
            "event_id": "e2",
            "artist_id": "a1",
            "date": "2026-01-05",
            "title": "品牌方宣布终止全部代言合作",
            "sources": [{"url": "https://x.test/2"}],
            "behavior": {"endorsement_terminated": 1},
            "authority": {"central_media": 1},
            "verticals": ["society"],
        },
    ]
    merged = dedupe_events(rows)
    assert len(merged) == 1
    assert len(merged[0]["sources"]) == 2
    # Two outlets reporting one termination is one termination...
    assert merged[0]["behavior"]["endorsement_terminated"] == 2
    # ...but the same CMA commentary carried twice is still one intervention.
    assert merged[0]["authority"]["central_media"] == 1
    assert set(merged[0]["verticals"]) == {"finance", "society"}


def test_dedupe_keeps_different_events_on_the_same_day():
    rows = [
        {"event_id": "e1", "artist_id": "a1", "date": "2026-01-05",
         "title": "推出新专辑并开启巡演", "sources": [{"url": "https://x.test/1"}]},
        {"event_id": "e2", "artist_id": "a1", "date": "2026-01-05",
         "title": "就网络传闻发布律师声明", "sources": [{"url": "https://x.test/2"}]},
    ]
    assert len(dedupe_events(rows)) == 2


def test_drop_sourceless_is_a_hard_gate():
    rows = [
        {"event_id": "e1", "sources": [{"url": "https://ok.test/1"}]},
        {"event_id": "e2", "sources": []},
        {"event_id": "e3", "sources": [{"url": "not-a-url"}]},
    ]
    kept, dropped = drop_sourceless(rows)
    assert [r["event_id"] for r in kept] == ["e1"]
    assert dropped == 2


def test_order_same_day_prefers_explicit_time_then_source_count():
    rows = [
        {"event_id": "e1", "time": "", "sources": [{"url": "https://x.test/1"}], "date": "2026-02-02"},
        {"event_id": "e2", "time": "14:30", "sources": [{"url": "https://x.test/2"}], "date": "2026-02-02"},
        {"event_id": "e3", "time": "", "date": "2026-02-02",
         "sources": [{"url": "https://x.test/3", "tier": "central_media"},
                     {"url": "https://x.test/4", "tier": "local_media"}]},
    ]
    assert [r["event_id"] for r in order_same_day(rows)] == ["e2", "e3", "e1"]


def test_clean_extraction_reports_what_it_did():
    raw = [
        {"date_text": "2026年1月5日", "title": "终止代言合作", "sources": [{"url": "https://x.test/1"}]},
        {"date_text": "2026年1月5日", "title": "终止全部代言合作", "sources": [{"url": "https://x.test/2"}]},
        {"date_text": "近日", "title": "发布声明", "sources": []},
        {"date_text": "2019年", "title": "出道", "sources": [{"url": "https://x.test/3"}]},
    ]
    out = clean_extraction(raw, REF)
    report = out["report"]
    assert report["output"] == 2
    assert report["dropped_no_source"] == 1
    assert report["merged_duplicates"] == 1
    assert report["coarse_dates"] == 1


def test_parse_response_handles_fences_and_wrappers():
    assert parse_response('```json\n[{"a":1}]\n```') == [{"a": 1}]
    assert parse_response('{"events":[{"a":1}]}') == [{"a": 1}]
    assert parse_response("前面的解释\n[{\"a\":1}]\n后面的解释") == [{"a": 1}]
    assert parse_response("完全不是 JSON") == []
    assert parse_response("") == []
