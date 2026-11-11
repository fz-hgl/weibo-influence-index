import pytest

from wii.score.stats import (
    bootstrap_mean_ci,
    percentile,
    weighted_mean,
    weighted_sd,
)


def test_weighted_mean_respects_weights():
    assert weighted_mean([(1.0, 1.0), (0.0, 3.0)]) == pytest.approx(0.25)


def test_weighted_mean_of_empty_is_zero():
    assert weighted_mean([]) == 0.0


def test_weighted_sd_is_zero_for_constant_series():
    assert weighted_sd([(0.5, 1.0), (0.5, 2.0), (0.5, 3.0)]) == 0.0


def test_percentile_interpolates():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert percentile(values, 0.0) == 1.0
    assert percentile(values, 0.5) == 3.0
    assert percentile(values, 1.0) == 5.0
    assert percentile(values, 0.25) == pytest.approx(2.0)


def test_bootstrap_is_reproducible_from_key():
    pairs = [(0.2 + 0.01 * i, 1.0 + 0.1 * i) for i in range(80)]
    first = bootstrap_mean_ci(pairs, key="a01", iterations=200)
    second = bootstrap_mean_ci(pairs, key="a01", iterations=200)
    assert first[:2] == second[:2]
    assert first[2]["seed"] == second[2]["seed"]


def test_bootstrap_interval_brackets_the_mean():
    pairs = [(0.5 if i % 4 else -0.5, 1.0) for i in range(120)]
    lo, hi, diag = bootstrap_mean_ci(pairs, key="a02", iterations=300)
    mean = weighted_mean(pairs)
    assert lo is not None and hi is not None
    assert lo <= mean <= hi
    assert diag["iterations"] == 300


def test_bootstrap_refuses_tiny_samples():
    pairs = [(0.1, 1.0)] * 5
    lo, hi, diag = bootstrap_mean_ci(pairs, key="a03")
    assert lo is None and hi is None
    assert diag["iterations"] == 0
    assert "样本" in diag["note"]
