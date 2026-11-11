import pytest

from wii.score.normalize import (
    normal_cdf,
    normalize,
    percentile_ranks,
    zscore_ranks,
)


def test_percentile_spans_zero_to_one():
    ranks = percentile_ranks([5.0, 1.0, 9.0, 3.0])
    assert min(ranks) == 0.0
    assert max(ranks) == 1.0
    assert ranks[2] == pytest.approx(1.0)  # value 9 is the max
    assert ranks[1] == pytest.approx(0.0)  # value 1 is the min


def test_percentile_ties_get_average_rank():
    ranks = percentile_ranks([1.0, 1.0, 1.0])
    assert ranks == pytest.approx([0.5, 0.5, 0.5])


def test_percentile_single_value_is_neutral():
    assert percentile_ranks([42.0]) == [0.5]


def test_percentile_is_order_preserving():
    values = [0.1, 7.0, 3.0, 100.0]
    ranks = percentile_ranks(values)
    assert ranks[3] > ranks[1] > ranks[2] > ranks[0]


def test_zscore_monotone_and_bounded():
    ranks = zscore_ranks([1.0, 2.0, 3.0, 4.0])
    assert all(0.0 < r < 1.0 for r in ranks)
    assert ranks == sorted(ranks)
    # symmetric input must map symmetrically around 0.5
    assert ranks[0] + ranks[3] == pytest.approx(1.0)
    assert ranks[1] + ranks[2] == pytest.approx(1.0)


def test_zscore_constant_series_is_neutral():
    assert zscore_ranks([5.0, 5.0, 5.0]) == [0.5, 0.5, 0.5]


def test_normal_cdf_known_values():
    assert normal_cdf(0.0) == pytest.approx(0.5)
    assert normal_cdf(1.96) == pytest.approx(0.975, abs=1e-3)


def test_normalize_dispatch_rejects_unknown():
    with pytest.raises(ValueError):
        normalize([1, 2], "magic")


def test_normalize_empty():
    assert normalize([], "percentile") == []
