import datetime as dt

import pytest

from wii.schema import Cohort, Mention
from wii.sentiment import (
    LEXICON_VERSION,
    agreement,
    rescore_cohort,
    score_rows,
    score_text,
    summarize,
)


@pytest.mark.parametrize(
    "text",
    [
        "这部戏真的很好看，演技在线",
        "太优秀了，非常喜欢，强烈推荐",
        "还不错，比预想的好一些",
    ],
)
def test_positive_text_scores_positive(text):
    assert score_text(text).value > 0.3


@pytest.mark.parametrize(
    "text",
    [
        "太难看了，彻底失望",
        "塌房了，代言全撤，抵制",
        "造假还控评，真是笑话",
    ],
)
def test_negative_text_scores_negative(text):
    assert score_text(text).value < -0.5


def test_negation_flips_and_damps():
    plain = score_text("好看").value
    negated = score_text("不好看").value
    double = score_text("不难看").value
    assert negated < 0 < plain
    assert 0 < double < plain, "negating a negative is lukewarm praise, not enthusiasm"


def test_positive_degree_adverb_amplifies():
    assert score_text("非常好看").value > score_text("好看").value


def test_irony_marker_flips_positive_to_negative():
    literal = score_text("呵呵，演技真好", use_irony=False)
    ironic = score_text("呵呵，演技真好")
    assert literal.value > 0
    assert ironic.value < -0.3
    assert ironic.irony == "呵呵"


def test_irony_can_be_disabled():
    plain = score_text("这波操作我服了", use_irony=False)
    ironic = score_text("这波操作我服了")
    assert ironic.value < plain.value


def test_protective_neutral_term_does_not_fire_positive():
    assert score_text("好像").value == 0.0
    assert score_text("好像").hits == []


def test_empty_text_is_zero_with_zero_confidence():
    score = score_text("")
    assert score.value == 0.0
    assert score.confidence == 0.0
    assert score.hits == []


def test_scores_are_deterministic_and_bounded():
    text = "有点失望，不过还算不错，整体及格"
    a, b = score_text(text), score_text(text)
    assert a.value == b.value
    assert -1.0 <= a.value <= 1.0
    assert 0.0 <= a.confidence <= 1.0


def test_hits_are_attributable():
    score = score_text("太难看了")
    assert score.hits
    hit = score.hits[0]
    assert hit["term"] == "难看"
    assert hit["degree"] == pytest.approx(1.4)
    assert hit["contribution"] < 0


def test_score_rows_keeps_original_and_tags_source():
    rows = [{"mention_id": "m1", "sentiment": 0.9, "text": "太难看了"}]
    out = score_rows(rows)
    assert out[0]["sentiment"] < 0
    assert out[0]["sentiment_original"] == 0.9
    assert out[0]["sentiment_source"] == f"lexicon-{LEXICON_VERSION}"
    assert out[0]["sentiment_detail"]["value"] == out[0]["sentiment"]


def test_summarize_shares_sum_to_one():
    rows = score_rows(
        [
            {"mention_id": "m1", "text": "太好看了", "weight": 1.0},
            {"mention_id": "m2", "text": "太难看了", "weight": 2.0},
            {"mention_id": "m3", "text": "路过看看", "weight": 1.0},
        ]
    )
    summary = summarize(rows)
    total = summary["share_positive"] + summary["share_neutral"] + summary["share_negative"]
    assert total == pytest.approx(1.0, abs=1e-6)
    assert summary["n"] == 3


def test_agreement_is_one_for_identical_scorers():
    payload = agreement([(0.8, 0.8), (-0.4, -0.4), (0.0, 0.0)])
    assert payload["mae"] == 0.0
    assert payload["sign_agreement"] == 1.0


def test_rescore_cohort_recomputes_without_mutating_input():
    cohort = Cohort(
        artists=[],
        events=[],
        mentions=[
            Mention(
                mention_id="m1",
                artist_id="a1",
                date=dt.date(2026, 1, 1),
                platform="weibo",
                sentiment=0.9,
                text="太难看了，彻底失望",
            )
        ],
        metrics=[],
    )
    rescored = rescore_cohort(cohort)
    assert rescored.mentions[0].sentiment < 0
    assert cohort.mentions[0].sentiment == 0.9
