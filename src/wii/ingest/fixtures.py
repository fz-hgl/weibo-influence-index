"""Synthetic demo cohort — the thing that makes this repo runnable in 5 seconds.

Everyone in `data/demo` is fictional. That is not a compromise, it is the
default: scoring named living people is the one feature this project refuses to
demo. The generator carries a **latent influence value** per artist that the
scorer never sees, so `wii validate` can ask the honest question — can the
pipeline recover a truth it has not seen? — instead of grading its own homework.

How the latent is built, and what that does and does not prove:

* For the four continuous factors the roster declares a target level in [0, 1]
  and the generator emits observations around it.
* For behaviour change and authority intervention the latent uses the actual
  weighted sum of the hand-written event payloads, because for those two the
  payload *is* the ground truth.
* Therefore the demo validates **implementation and noise robustness**, not the
  theory. If the six-factor theory is wrong, this suite will happily pass.
  That limitation is stated in METHODOLOGY.md too, because a benchmark that
  oversells itself is worse than no benchmark.

Deliberate imperfections, kept on purpose:

* mention volume is noisy, so rank recovery lands around 0.9, not 1.0;
* 15-30% of mentions are flagged spam with a sentiment skew, so the spam filter
  has something to do;
* detection of "still fermenting" uses a 25% of peak threshold, so an artist
  with a tiny window can lose days to Poisson noise.

Regenerating is deterministic: same seed -> byte-identical files.
"""

from __future__ import annotations

import datetime as _dt
import json
import random
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .. import config
from .weights import account_weight

WINDOW_START = _dt.date(2025, 12, 1)
WINDOW_DAYS = 90
SEED = 20260301

ROSTER: List[Dict[str, Any]] = [
    {
        "artist_id": "a01",
        "name": "林知远",
        "category": "actor",
        "valence": -0.58,
        "intensity": 0.90,
        "reach": 0.95,
        "duration": 0.88,
        "mix": {"entertainment": 0.70, "finance": 0.16, "society": 0.14},
        "note": "塌房型：触达极大、极性极负，代言与监管层面都有行为改变",
        "events": [
            {
                "day": 34,
                "title": "品牌方宣布终止与当事人全部代言合作",
                "event_type": "endorsement_terminated",
                "verticals": ["finance", "society"],
                "behavior": {"endorsement_terminated": 3, "institutional_response": 1},
                "authority": {"central_media": 1},
                "tier": "central_media",
            },
            {
                "day": 41,
                "title": "主演剧集宣布暂停宣传排播",
                "event_type": "production_cancelled",
                "verticals": ["entertainment"],
                "behavior": {"production_cancelled": 2},
                "authority": {"industry_association": 1},
                "tier": "industry_association",
            },
        ],
    },
    {
        "artist_id": "a02",
        "name": "苏晚棠",
        "category": "actor",
        "valence": 0.52,
        "intensity": 0.75,
        "reach": 0.90,
        "duration": 0.72,
        "mix": {"entertainment": 0.82, "culture": 0.12, "sports": 0.06},
        "note": "正向出圈型：票房与商业数据拉升，但几乎没有权威介入",
        "events": [
            {
                "day": 22,
                "title": "主演影片累计票房进入年度前十",
                "event_type": "release",
                "verticals": ["entertainment", "culture"],
                "behavior": {"box_office_delta_pct": 38.0, "sales_delta_pct": 12.0},
                "authority": {},
                "tier": "outlet",
            },
            {
                "day": 57,
                "title": "受邀参与公益阅读推广活动",
                "event_type": "award",
                "verticals": ["culture"],
                "behavior": {"institutional_response": 1},
                "authority": {"local_media": 2},
                "tier": "local_media",
            },
        ],
    },
    {
        "artist_id": "a03",
        "name": "陈默",
        "category": "actor",
        "valence": 0.46,
        "intensity": 0.72,
        "reach": 0.55,
        "duration": 0.95,
        "mix": {"entertainment": 0.62, "society": 0.24, "culture": 0.14},
        "note": "逝世型：触达中等但央媒集体发声、发酵极长，用来测权威因子",
        "events": [
            {
                "day": 48,
                "title": "家属发布讣告，业内人士集体悼念",
                "event_type": "statement",
                "verticals": ["entertainment", "culture"],
                "behavior": {"institutional_response": 1},
                "authority": {"central_media": 3, "industry_association": 2},
                "tier": "central_media",
            },
            {
                "day": 52,
                "title": "行业协会发文倡议保护老一辈文艺工作者权益",
                "event_type": "policy_followup",
                "verticals": ["society", "culture"],
                "behavior": {"policy_followup": 1},
                "authority": {"industry_association": 1, "local_media": 2},
                "tier": "industry_association",
            },
        ],
    },
    {
        "artist_id": "a04",
        "name": "温言",
        "category": "idol",
        "valence": -0.42,
        "intensity": 0.88,
        "reach": 0.99,
        "duration": 0.52,
        "mix": {"entertainment": 0.90, "society": 0.10},
        "note": "粉黑大战型：流量最大但几乎不外溢，水军比例最高",
        "events": [
            {
                "day": 12,
                "title": "粉丝群体与另一艺人粉丝发生大规模互撕",
                "event_type": "allegation",
                "verticals": ["entertainment"],
                "behavior": {},
                "authority": {},
                "tier": "outlet",
            },
            {
                "day": 30,
                "title": "工作室就被指数据造假发布声明",
                "event_type": "statement",
                "verticals": ["entertainment"],
                "behavior": {"institutional_response": 1},
                "authority": {"industry_association": 1, "local_media": 1},
                "tier": "local_media",
            },
        ],
    },
    {
        "artist_id": "a05",
        "name": "江以宁",
        "category": "host",
        "valence": -0.28,
        "intensity": 0.60,
        "reach": 0.62,
        "duration": 0.50,
        "mix": {"entertainment": 0.78, "society": 0.22},
        "note": "争议型：有行业协会表态，但未到监管处罚",
        "events": [
            {
                "day": 39,
                "title": "节目录制现场争议片段引发讨论",
                "event_type": "allegation",
                "verticals": ["entertainment", "society"],
                "behavior": {"institutional_response": 1, "sales_delta_pct": 5.0},
                "authority": {"industry_association": 1},
                "tier": "industry_association",
            }
        ],
    },
    {
        "artist_id": "a06",
        "name": "顾南川",
        "category": "singer",
        "valence": 0.22,
        "intensity": 0.45,
        "reach": 0.52,
        "duration": 0.45,
        "mix": {"entertainment": 0.86, "culture": 0.10, "sports": 0.04},
        "note": "稳定型：巡演与销量，无外溢",
        "events": [
            {
                "day": 26,
                "title": "巡演开票当日售罄",
                "event_type": "release",
                "verticals": ["entertainment"],
                "behavior": {"sales_delta_pct": 22.0},
                "authority": {"local_media": 1},
                "tier": "local_media",
            }
        ],
    },
    {
        "artist_id": "a07",
        "name": "沈亦舟",
        "category": "director",
        "valence": 0.34,
        "intensity": 0.55,
        "reach": 0.40,
        "duration": 0.74,
        "mix": {"entertainment": 0.62, "culture": 0.26, "society": 0.12},
        "note": "行业规范型：热度不高但推动了协会层面的规则，用来测「热度≠影响」",
        "events": [
            {
                "day": 44,
                "title": "在行业论坛提出剧组工时规范建议",
                "event_type": "policy_followup",
                "verticals": ["culture", "society"],
                "behavior": {"policy_followup": 1, "institutional_response": 2},
                "authority": {"industry_association": 2},
                "tier": "industry_association",
            }
        ],
    },
    {
        "artist_id": "a08",
        "name": "韩雪松",
        "category": "public_figure",
        "valence": 0.44,
        "intensity": 0.50,
        "reach": 0.40,
        "duration": 0.78,
        "mix": {"entertainment": 0.45, "tech": 0.30, "society": 0.25},
        "note": "科普出圈型：低流量、高技术垂类外溢",
        "events": [
            {
                "day": 35,
                "title": "科普纪录片上线并进入教育推荐片单",
                "event_type": "release",
                "verticals": ["tech", "society"],
                "behavior": {"institutional_response": 2},
                "authority": {"central_media": 1, "local_media": 1},
                "tier": "central_media",
            }
        ],
    },
    {
        "artist_id": "a09",
        "name": "白鹿鸣",
        "category": "actor",
        "valence": 0.26,
        "intensity": 0.48,
        "reach": 0.45,
        "duration": 0.32,
        "mix": {"entertainment": 0.95, "culture": 0.05},
        "note": "上升期：单点小爆，衰减快",
        "events": [
            {
                "day": 18,
                "title": "新剧角色片段在短视频平台二次传播",
                "event_type": "release",
                "verticals": ["entertainment"],
                "behavior": {"sales_delta_pct": 8.0},
                "authority": {},
                "tier": "outlet",
            }
        ],
    },
    {
        "artist_id": "a10",
        "name": "许知微",
        "category": "actor",
        "valence": 0.02,
        "intensity": 0.30,
        "reach": 0.20,
        "duration": 0.26,
        "mix": {"entertainment": 0.97, "culture": 0.03},
        "note": "低强度对照组：用来压住整张表的底部",
        "events": [
            {
                "day": 61,
                "title": "参加品牌线下活动",
                "event_type": "other",
                "verticals": ["entertainment"],
                "behavior": {},
                "authority": {},
                "tier": "outlet",
            }
        ],
    },
]

PLATFORMS = [("weibo", 0.72), ("douyin", 0.14), ("xiaohongshu", 0.08), ("bilibili", 0.06)]

# Demo texts are templates chosen by the mention's *latent* sentiment bucket,
# so `wii sentiment` has something to read and its output can be compared with
# the generator's intent. They are obviously synthetic on purpose: a demo that
# looks like real posts invites people to treat it as real data.
TEXT_TEMPLATES = {
    "strong_negative": [
        "合成示例：这次真的太让人失望了，彻底塌房，抵制（{n}）。",
        "合成示例：难看又难看，恶心到我了，果断脱粉（{n}）。",
        "合成示例：离谱到极点，造假还控评，真是笑话（{n}）。",
    ],
    "mild_negative": [
        "合成示例：有点失望，感觉有点敷衍，不太行（{n}）。",
        "合成示例：一般般吧，节奏拖沓，有点尴尬（{n}）。",
        "合成示例：谈不上难看，但也确实没什么亮点（{n}）。",
    ],
    "neutral": [
        "合成示例：路过看看，暂时没什么感觉（{n}）。",
        "合成示例：等官方通报，先不站队（{n}）。",
        "合成示例：吃瓜中，信息还不完整（{n}）。",
    ],
    "mild_positive": [
        "合成示例：还不错，演技在线，期待下一部（{n}）。",
        "合成示例：有点惊喜，整体挺用心的（{n}）。",
        "合成示例：算是合格，比预想的好一些（{n}）。",
    ],
    "strong_positive": [
        "合成示例：太好看了，真的惊艳，非常喜欢（{n}）。",
        "合成示例：精彩到哭，值得二刷，强烈推荐（{n}）。",
        "合成示例：优秀又真诚，这波必须支持（{n}）。",
    ],
}


def _sentiment_bucket(sentiment: float) -> str:
    if sentiment <= -0.55:
        return "strong_negative"
    if sentiment < -0.12:
        return "mild_negative"
    if sentiment <= 0.12:
        return "neutral"
    if sentiment < 0.55:
        return "mild_positive"
    return "strong_positive"


def _synthetic_text(sentiment: float, seq: int) -> str:
    variants = TEXT_TEMPLATES[_sentiment_bucket(sentiment)]
    return variants[seq % len(variants)].format(n=seq)


def _pick(rng: random.Random, pairs: List[Tuple[str, float]]) -> str:
    r = rng.random()
    acc = 0.0
    for value, weight in pairs:
        acc += weight
        if r <= acc:
            return value
    return pairs[-1][0]


def intended_spillover(mix: Dict[str, float]) -> float:
    """The spillover value the declared vertical mix *should* produce.

    Mirrors `factors.raw_spillover` on the noise-free mix, so the latent truth
    and the measured factor are computed the same way at different stages.
    """
    raw = sum(
        config.VERTICAL_WEIGHTS[v] * share
        for v, share in mix.items()
        if v != "entertainment" and config.VERTICAL_WEIGHTS.get(v, 0) > 0
    )
    return min(1.0, raw / config.SPILLOVER_NORMALIZER)


def generate(out_dir: Path, *, seed: int = SEED) -> Dict[str, Any]:
    from .. import config as cfg
    from ..score import factors as F
    from ..store import load_cohort, write_jsonl

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    dates = [WINDOW_START + _dt.timedelta(days=i) for i in range(WINDOW_DAYS)]

    artists_rows: List[Dict[str, Any]] = []
    events_rows: List[Dict[str, Any]] = []
    mention_rows: List[Dict[str, Any]] = []
    metric_rows: List[Dict[str, Any]] = []
    traits: Dict[str, Dict[str, float]] = {}

    mention_seq = 0
    for spec in ROSTER:
        aid = spec["artist_id"]
        artists_rows.append(
            {
                "artist_id": aid,
                "name": spec["name"],
                "category": spec["category"],
                "fictional": True,
                "note": spec["note"],
            }
        )

        reach_t = spec["reach"]
        dur_t = spec["duration"]
        int_t = spec["intensity"]
        valence = spec["valence"]
        mix_pairs = sorted(spec["mix"].items(), key=lambda kv: -kv[1])
        spikes = spec["events"]

        # Signed direction that makes E[sentiment] == valence while the mean
        # absolute value tracks the intensity trait.
        direction = max(-1.0, min(1.0, valence / int_t if int_t else 0.0))
        p_positive = (1.0 + direction) / 2.0

        base = 0.15 + 1.5 * reach_t
        profile = [base] * WINDOW_DAYS
        for ev in spikes:
            amp = (4.0 + 24.0 * reach_t) * (0.75 + 0.5 * rng.random())
            half_life = 1.2 + 5.0 * dur_t
            for d in range(WINDOW_DAYS - ev["day"]):
                profile[ev["day"] + d] += amp * (0.5 ** (d / half_life))

        spam_base = 0.05 + 0.28 * reach_t * (0.5 + rng.random())
        spike_days = {ev["day"] for ev in spikes}

        for day_idx, date in enumerate(dates):
            expected = profile[day_idx] * (0.85 + 0.3 * rng.random())
            count = max(0, int(round(expected + rng.gauss(0, 0.30))))
            near_spike = any(0 <= day_idx - d <= 6 for d in spike_days)

            day_reads = 0
            day_disc = 0
            for _ in range(count):
                mention_seq += 1
                abs_s = min(1.0, max(0.03, rng.gauss(int_t, 0.13)))
                sentiment = abs_s if rng.random() < p_positive else -abs_s
                is_spam = rng.random() < spam_base
                if is_spam:
                    # Spam pushes the tone toward the artist's dominant
                    # direction and away from the middle: that is what 控评
                    # and 水军 actually do to a distribution.
                    sign = 1.0 if p_positive >= 0.5 else -1.0
                    sentiment = sign * min(1.0, abs_s * 1.3 + abs(rng.gauss(0, 0.08)))

                vertical = _pick(rng, mix_pairs)
                platform = _pick(rng, PLATFORMS)
                followers = int(10 ** rng.gauss(2.3, 1.5))
                verified = rng.random() < 0.05
                age = int(abs(rng.gauss(900, 700)))
                activity = max(0.05, min(1.0, rng.gauss(0.55, 0.25)))
                mention_rows.append(
                    {
                        "mention_id": f"m{mention_seq:06d}",
                        "artist_id": aid,
                        "date": date.isoformat(),
                        "platform": platform,
                        "sentiment": round(max(-1.0, min(1.0, sentiment)), 4),
                        "vertical": vertical,
                        "weight": account_weight(followers, verified, age, activity),
                        "is_spam": is_spam,
                        "text": _synthetic_text(sentiment, mention_seq),
                    }
                )
                per_mention = 20_000 * (10 ** (1.5 * reach_t)) * (2.4 if near_spike else 1.0)
                day_reads += int(per_mention * (0.6 + 0.8 * rng.random()))
                day_disc += int(6 * (2.0 if near_spike else 1.0) * (0.7 + 0.6 * rng.random()))

            hot = 0
            if day_idx in spike_days or (day_idx - 1) in spike_days:
                hot = max(0, int(round(3.0 * reach_t + rng.gauss(0, 0.6))))

            if day_reads or day_disc or hot:
                metric_rows.append(
                    {
                        "artist_id": aid,
                        "date": date.isoformat(),
                        "platform": "weibo",
                        "reads": day_reads,
                        "discussions": day_disc,
                        "hotsearch_entries": hot,
                    }
                )
                if reach_t >= 0.45:
                    metric_rows.append(
                        {
                            "artist_id": aid,
                            "date": date.isoformat(),
                            "platform": "douyin",
                            "reads": int(day_reads * 0.30),
                            "discussions": int(day_disc * 0.35),
                            "hotsearch_entries": 0,
                        }
                    )

        for i, ev in enumerate(spikes):
            date = dates[min(WINDOW_DAYS - 1, ev["day"])]
            events_rows.append(
                {
                    "event_id": f"{aid}-e{i + 1:02d}",
                    "artist_id": aid,
                    "date": date.isoformat(),
                    "title": ev["title"],
                    "event_type": ev["event_type"],
                    "verticals": ev["verticals"],
                    "sources": [
                        {
                            "url": f"https://example.org/synthetic/{aid}/e{i + 1:02d}",
                            "publisher": "示例来源（合成，非真实报道）",
                            "published_at": date.isoformat(),
                            "tier": ev["tier"],
                        }
                    ],
                    "behavior": ev["behavior"],
                    "authority": ev["authority"],
                    "note": "synthetic demo event; no real person or outlet is represented",
                    "synthetic": True,
                }
            )

        traits[aid] = {
            "reach": reach_t,
            "duration": dur_t,
            "intensity": int_t,
            "spillover": intended_spillover(spec["mix"]),
        }

    write_jsonl(out_dir / "artists.jsonl", sorted(artists_rows, key=lambda r: r["artist_id"]))
    write_jsonl(out_dir / "events_verified.jsonl", sorted(events_rows, key=lambda r: r["event_id"]))
    write_jsonl(
        out_dir / "mentions.jsonl",
        sorted(mention_rows, key=lambda r: (r["artist_id"], r["date"], r["mention_id"])),
    )
    write_jsonl(
        out_dir / "platform_metrics.jsonl",
        sorted(metric_rows, key=lambda r: (r["artist_id"], r["date"], r["platform"])),
    )

    # Latent truth: the weighted sum of target levels. Behaviour and authority
    # are taken from the *generated* event payloads, run through the same
    # functions the scorer uses, because for those two the payload is the truth.
    cohort, _ = load_cohort(out_dir)
    weights = cfg.DEFAULT_WEIGHTS
    latent: Dict[str, float] = {}
    for spec in ROSTER:
        aid = spec["artist_id"]
        beh_raw, _ = F.raw_behavior(cohort, aid)
        auth_raw, _ = F.raw_authority(cohort, aid)
        latent[aid] = round(
            weights["reach"] * traits[aid]["reach"]
            + weights["duration"] * traits[aid]["duration"]
            + weights["intensity"] * traits[aid]["intensity"]
            + weights["spillover"] * traits[aid]["spillover"]
            + weights["behavior"] * beh_raw
            + weights["authority"] * auth_raw,
            6,
        )

    expectations = {
        "note": (
            "latent 是生成器写入的潜在影响力，评分器看不到它：连续因子取生成参数的目标水平，"
            "行为/权威取生成后事件的实际加权和。它检验的是「实现能否从带噪观测还原已知真值」，"
            "不检验六因子理论本身。rules 是用常识写的原型断言。任何一项失败，回去调权重或改因子定义，"
            "不要改这里来凑结论。"
        ),
        "latent": latent,
        "traits": traits,
        "thresholds": {
            "spearman_min": 0.80,
            "kendall_min": 0.60,
            "top_k": 3,
            "top_k_overlap_min": 2,
        },
        "rules": [
            {
                "artist_id": "a01",
                "metric": "stars",
                "op": "ge",
                "value": 7.5,
                "label": "塌房顶流应≥7.5 星（触达+行为改变+监管介入）",
            },
            {
                "artist_id": "a01",
                "metric": "valence",
                "op": "lt",
                "value": -0.3,
                "label": "塌房顶流极性应为明显负值",
            },
            {
                "artist_id": "a03",
                "metric": "percentile.authority",
                "op": "ge",
                "value": 0.8,
                "label": "央媒集体发声者，权威百分位应进前 20%",
            },
            {
                "artist_id": "a03",
                "metric": "valence",
                "op": "gt",
                "value": 0.2,
                "label": "悼念型舆论极性应偏正",
            },
            {
                "artist_id": "a04",
                "metric": "valence",
                "op": "lt",
                "value": -0.1,
                "label": "粉黑大战型舆论应偏负",
            },
            {
                "artist_id": "a07",
                "metric": "percentile.spillover",
                "op": "ge",
                "value": 0.6,
                "label": "推进行业规范者应有明显跨圈层外溢",
            },
            {
                "artist_id": "a10",
                "metric": "stars",
                "op": "le",
                "value": 4.0,
                "label": "低强度对照组应≤4 星",
            },
        ],
    }
    with open(out_dir / "expectations.json", "w", encoding="utf-8", newline="\n") as fh:
        json.dump(expectations, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    return {
        "artists": len(artists_rows),
        "events": len(events_rows),
        "mentions": len(mention_rows),
        "metrics": len(metric_rows),
        "window": f"{dates[0].isoformat()}~{dates[-1].isoformat()}",
        "out_dir": str(out_dir),
    }
