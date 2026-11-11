import datetime as dt

import pytest

from wii import config
from wii.schema import Artist, Cohort, Mention, PlatformMetric, VerifiedEvent
from wii.score import factors as F


def _mention(aid, day, sentiment, weight=1.0, spam=False, vertical="entertainment"):
    return Mention(
        mention_id=f"{aid}-{day}-{sentiment}-{spam}",
        artist_id=aid,
        date=dt.date(2026, 1, 1) + dt.timedelta(days=day),
        platform="weibo",
        sentiment=sentiment,
        vertical=vertical,
        weight=weight,
        is_spam=spam,
    )


def test_half_life_recovers_a_known_decay():
    series = [100.0 * (0.5 ** (d / 3.0)) for d in range(20)]
    hl, diag = F.decay_half_life(series)
    assert hl == pytest.approx(3.0, rel=0.02)
    assert diag["fit_points"] >= 3


def test_half_life_without_decay_is_censored():
    series = [10.0] * 12
    hl, diag = F.decay_half_life(series)
    assert hl == config.CAPS["half_life_days"]
    assert "censored" in diag["note"]


def test_half_life_needs_enough_points():
    hl, diag = F.decay_half_life([1, 9, 2])
    assert hl == 0.0
    assert diag["fit_points"] < 3


def test_clean_mentions_exclude_spam():
    cohort = Cohort(
        artists=[Artist("a1", "测试甲")],
        events=[],
        mentions=[
            _mention("a1", 0, 0.1, weight=1.0),
            _mention("a1", 0, -0.9, weight=50.0, spam=True),
        ],
        metrics=[],
    )
    value, diag = F.raw_intensity(cohort, "a1")
    assert diag["n_mentions"] == 1
    assert value == pytest.approx(0.1)


def test_intensity_ignores_sign():
    cohort = Cohort(
        artists=[Artist("a1", "x")],
        events=[],
        mentions=[_mention("a1", 0, -0.8), _mention("a1", 0, 0.8)],
        metrics=[],
    )
    value, _ = F.raw_intensity(cohort, "a1")
    assert value == pytest.approx(0.8)


def test_valence_keeps_sign_and_reports_spam_ratio():
    cohort = Cohort(
        artists=[Artist("a1", "x")],
        events=[],
        mentions=[_mention("a1", 0, -0.6), _mention("a1", 0, -0.6),
                  _mention("a1", 0, -1.0, spam=True)],
        metrics=[],
    )
    mean, sd, diag = F.valence(cohort, "a1")
    assert mean == pytest.approx(-0.6)
    assert diag["spam_ratio"] == pytest.approx(1 / 3, rel=1e-3)
    assert diag["label"] == "偏负面"


def test_reach_is_log_scaled_and_monotone():
    def build(reads):
        return Cohort(
            artists=[Artist("a1", "x")],
            events=[],
            mentions=[],
            metrics=[PlatformMetric("a1", dt.date(2026, 1, 1), "weibo", reads, reads // 20, 2)],
        )

    small, _ = F.raw_reach(build(10_000), "a1")
    big, diag = F.raw_reach(build(10_000_000), "a1")
    assert big > small
    # A thousand-fold increase in reads must not be a thousand-fold factor.
    assert big / small < 3.0
    assert diag["population_proxy_share"] > 0


def test_reach_counts_platform_breadth():
    one = Cohort(
        artists=[Artist("a1", "x")], events=[], mentions=[],
        metrics=[PlatformMetric("a1", dt.date(2026, 1, 1), "weibo", 1000, 10, 0)],
    )
    two = Cohort(
        artists=[Artist("a1", "x")], events=[], mentions=[],
        metrics=[PlatformMetric("a1", dt.date(2026, 1, 1), "weibo", 1000, 10, 0),
                 PlatformMetric("a1", dt.date(2026, 1, 1), "douyin", 0, 10, 0)],
    )
    assert F.raw_reach(two, "a1")[0] > F.raw_reach(one, "a1")[0]


def test_spillover_only_counts_non_entertainment():
    base = Cohort(
        artists=[Artist("a1", "x")], events=[],
        mentions=[_mention("a1", i, 0.1) for i in range(10)], metrics=[],
    )
    assert F.raw_spillover(base, "a1")[0] == 0.0

    spilled = Cohort(
        artists=[Artist("a1", "x")], events=[],
        mentions=[_mention("a1", i, 0.1) for i in range(9)]
        + [_mention("a1", 9, 0.1, vertical="finance")],
        metrics=[],
    )
    value, diag = F.raw_spillover(spilled, "a1")
    assert value > 0
    assert "finance" in diag["verticals_reached"]


def test_behavior_and_authority_are_capped():
    ev = VerifiedEvent(
        event_id="e1", artist_id="a1", date=dt.date(2026, 1, 1), title="t",
        event_type="endorsement_terminated", verticals=["finance"],
        sources=[], behavior={"endorsement_terminated": 99},
        authority={"regulator": 99},
    )
    cohort = Cohort(artists=[Artist("a1", "x")], events=[ev],
                    mentions=[_mention("a1", 0, 0.1)], metrics=[])
    assert F.raw_behavior(cohort, "a1")[0] == 1.0
    assert F.raw_authority(cohort, "a1")[0] == 1.0


def test_duration_grows_with_longer_ferment():
    short = Cohort(
        artists=[Artist("a1", "x")], events=[],
        mentions=[_mention("a1", 0, 0.1) for _ in range(10)], metrics=[],
    )
    long = Cohort(
        artists=[Artist("a1", "x")], events=[],
        mentions=[_mention("a1", 0, 0.1) for _ in range(10)]
        + [_mention("a1", 5, 0.1) for _ in range(6)]
        + [_mention("a1", 12, 0.1) for _ in range(3)],
        metrics=[],
    )
    assert F.raw_duration(long, "a1")[0] > F.raw_duration(short, "a1")[0]


def test_daily_volume_is_sorted_and_filtered():
    cohort = Cohort(
        artists=[Artist("a1", "x")], events=[],
        mentions=[_mention("a1", 2, 0.1), _mention("a1", 0, 0.1), _mention("a1", 0, 0.1, spam=True)],
        metrics=[],
    )
    volume = F.daily_volume(cohort.mentions_of("a1"))
    assert list(volume) == ["2026-01-01", "2026-01-03"]
    assert volume["2026-01-01"] == 1
