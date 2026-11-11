import pytest

from wii import config
from wii.score import explain as explain_mod
from wii.score.index import compute_index, stars_from_magnitude


def test_star_mapping_endpoints():
    assert stars_from_magnitude(0.0) == 1.0
    assert stars_from_magnitude(1.0) == 10.0
    assert stars_from_magnitude(0.5) == 5.5


def test_star_mapping_clamps_out_of_range():
    assert stars_from_magnitude(-3.0) == 1.0
    assert stars_from_magnitude(9.0) == 10.0


def test_weights_must_cover_all_factors():
    with pytest.raises(ValueError):
        config.validate_weights({"reach": 1.0})


def test_weights_are_renormalised():
    w = config.validate_weights({"reach": 2, "duration": 2, "intensity": 2,
                                 "spillover": 2, "behavior": 2, "authority": 2})
    assert sum(w.values()) == pytest.approx(1.0)
    assert w["reach"] == pytest.approx(1 / 6)


def test_negative_weight_rejected():
    with pytest.raises(ValueError):
        config.validate_weights({**config.DEFAULT_WEIGHTS, "reach": -0.5})


@pytest.mark.parametrize("method", ["percentile", "zscore"])
def test_index_is_internally_consistent(demo_cohort, method):
    result = compute_index(demo_cohort, normalization=method)
    for a in result.artists:
        # contributions must add up to the magnitude
        assert sum(a.contribution.values()) == pytest.approx(a.magnitude, abs=1e-9)
        # and the star value must be exactly the documented affine map
        assert a.stars == pytest.approx(1 + 9 * a.magnitude, abs=0.05)
        assert 1.0 <= a.stars <= 10.0
        # every factor has a normalised value in [0, 1]
        assert all(0.0 <= v <= 1.0 for v in a.normalized.values())
        # valence is a signed mean, not an absolute one
        assert -1.0 <= a.valence <= 1.0


def test_ranking_sorted_desc(demo_cohort):
    result = compute_index(demo_cohort)
    stars = [a.stars for a in result.ranked()]
    assert stars == sorted(stars, reverse=True)


def test_explain_arithmetic_matches_score(demo_cohort):
    result = compute_index(demo_cohort)
    for a in result.artists:
        exp = explain_mod.explain_artist(a, result.weights)
        assert exp["stars"] == a.stars
        # displayed stars are rounded to 1 decimal, so the recomputation may
        # differ from the printed value by up to half a rounding step
        assert exp["arithmetic"]["check"] == pytest.approx(a.stars, abs=0.05)
        assert sum(r["contribution"] for r in exp["factors"]) == pytest.approx(a.magnitude, abs=1e-3)
        assert len(exp["factors"]) == len(config.FACTORS)


def test_explain_text_renders(demo_cohort):
    result = compute_index(demo_cohort)
    text = explain_mod.render_text(explain_mod.explain_artist(result.ranked()[0], result.weights))
    assert "星" in text and "权重" in text


def test_weight_override_changes_result(demo_cohort):
    base = compute_index(demo_cohort)
    reach_heavy = compute_index(
        demo_cohort,
        weights={**config.DEFAULT_WEIGHTS, "reach": 0.6, "duration": 0.08,
                 "intensity": 0.08, "spillover": 0.08, "behavior": 0.08, "authority": 0.08},
    )
    base_rank = [a.artist_id for a in base.ranked()]
    alt_rank = [a.artist_id for a in reach_heavy.ranked()]
    assert base_rank != alt_rank, "weights are supposed to be load-bearing"


def test_index_requires_mentions_or_metrics():
    from wii.schema import Artist, Cohort

    with pytest.raises(ValueError):
        compute_index(Cohort(artists=[Artist("a1", "x")], events=[], mentions=[], metrics=[]))
