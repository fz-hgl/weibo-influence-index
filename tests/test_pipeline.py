import json

import pytest

from wii.ingest import fixtures
from wii.report.build import build_html
from wii.score.index import compute_index
from wii.store import fingerprint, load_cohort
from wii.validate import backtest


def _run(demo_dir):
    cohort, tables = load_cohort(demo_dir)
    result = compute_index(
        cohort,
        fingerprint=fingerprint(demo_dir),
        tables_used=tables,
        cohort_label="test",
        generated_at="2026-03-01T00:00:00+00:00",
    )
    return cohort, result


def test_demo_generation_is_deterministic(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    fixtures.generate(a)
    fixtures.generate(b)
    assert fingerprint(a) == fingerprint(b)
    for name in ("artists.jsonl", "events_verified.jsonl", "mentions.jsonl", "platform_metrics.jsonl"):
        assert (a / name).read_bytes() == (b / name).read_bytes()


def test_demo_is_entirely_synthetic(demo_dir):
    artists = [json.loads(line) for line in (demo_dir / "artists.jsonl").read_text("utf-8").splitlines() if line]
    assert all(a["fictional"] for a in artists)
    events = [json.loads(line) for line in (demo_dir / "events_verified.jsonl").read_text("utf-8").splitlines() if line]
    assert all(e["synthetic"] for e in events)
    for e in events:
        assert all(s["url"].startswith("https://example.org/") for s in e["sources"])


def test_backtest_passes_on_demo(demo_dir):
    _, result = _run(demo_dir)
    expectations = backtest.load_expectations(demo_dir / "expectations.json")
    report = backtest.run_backtest(result, expectations)
    failures = [c for c in report.checks if not c.passed]
    assert not failures, backtest.render_text(report)
    assert report.spearman is not None and report.spearman >= 0.8


def test_spearman_sanity():
    assert backtest.spearman([1, 2, 3, 4], [1, 2, 3, 4]) == pytest.approx(1.0)
    assert backtest.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    assert backtest.kendall_tau([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)


def test_report_is_self_contained(demo_dir, tmp_path):
    _, result = _run(demo_dir)
    path = build_html(result, tmp_path / "report.html")
    html = path.read_text("utf-8")
    assert result.data_fingerprint in html
    assert "已核实事件" in html
    # no external asset loading of any kind
    assert "<script" not in html.lower()
    assert "<link" not in html.lower()
    assert "@import" not in html
    # every artist appears
    for a in result.artists:
        assert a.name in html


def test_report_anonymize_hides_names(demo_dir, tmp_path):
    _, result = _run(demo_dir)
    path = build_html(result, tmp_path / "anon.html", anonymize=True)
    html = path.read_text("utf-8")
    assert "林知远" not in html
    assert "艺人 A" in html


def test_report_embeds_validation(demo_dir, tmp_path):
    _, result = _run(demo_dir)
    expectations = backtest.load_expectations(demo_dir / "expectations.json")
    payload = backtest.run_backtest(result, expectations).to_dict()
    path = build_html(result, tmp_path / "v.html", validation=payload)
    html = path.read_text("utf-8")
    assert "Spearman" in html
    assert payload["checks"][0]["name"] in html
