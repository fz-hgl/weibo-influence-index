"""A small, auditable Chinese sentiment lexicon.

This is a *baseline*, not a model. It exists so that the repository can go from
raw `mentions.jsonl` (text only) to a polarity number without shipping a
dependency or an API key — and so that every number it produces can be traced
to a handful of words a human can read.

Design choices worth knowing before you trust a score:

* **Longer units win.** "不错" is matched as a unit before "不" + "错" can be
  read as a negation, because terms are tried longest-first.
* **Negation is a flipped sign, damped to 0.75.** "不好看" is negative, but
  weaker than "难看". Double negation is not modelled (rare, and usually
  rhetorical).
* **Degree adverbs multiply.** 非常 ×1.6, 有点 ×0.6.
* **Irony is a rule list, not a classifier.** 呵呵 / 真有你的 / 好一个 flip a
  positive reading negative. It has known false positives (genuine praise can
  use the same words), which is exactly why every mention carries an `irony`
  flag and the CLI can turn the rule off with `--no-irony`.
* **Domain words are included on purpose.** 塌房 / 翻车 / 割韭菜 / 洗白 carry
  more signal in entertainment chatter than any general-purpose word list.

If you need better accuracy on real data, fine-tune a model and keep this
module as the offline comparison baseline (see `wii sentiment --compare`).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Terms. Value is the *literal* polarity in [-1, 1], before negation/degree.
# Keep single-character entries rare: they are the main source of false hits.
# ---------------------------------------------------------------------------
POSITIVE = {
    # 作品 / 表现
    "好看": 0.75, "好听": 0.7, "好哭": 0.55, "好笑": 0.45, "真好": 0.7,
    "好": 0.4, "精彩": 0.85, "惊艳": 0.9,
    "绝美": 0.85, "在线": 0.55, "进步": 0.6, "用心": 0.75, "诚意": 0.6,
    "质感": 0.55, "封神": 0.9, "名场面": 0.7, "演技": 0.45,
    # 评价
    "优秀": 0.85, "不错": 0.7, "满意": 0.7, "完美": 0.9, "喜欢": 0.8,
    "爱了": 0.8, "支持": 0.7, "认可": 0.65, "佩服": 0.7, "敬佩": 0.8,
    "致敬": 0.8, "respect": 0.7, "点赞": 0.7, "好评": 0.8, "值得": 0.6,
    "厉害": 0.7, "牛": 0.6, "棒": 0.75, "赞": 0.65, "给力": 0.8,
    "顶": 0.6, "稳": 0.5, "绝": 0.55, "强": 0.55,
    # 人品 / 情感
    "善良": 0.85, "真诚": 0.8, "温柔": 0.75, "体面": 0.6, "担当": 0.75,
    "敬业": 0.8, "专业": 0.6, "有才": 0.75, "争气": 0.7, "榜样": 0.8,
    "感动": 0.7, "温暖": 0.7, "治愈": 0.8, "欣慰": 0.7, "骄傲": 0.6,
    "祝福": 0.7, "恭喜": 0.8, "期待": 0.55, "心疼": -0.3, "走好": 0.3,
    "还可以": 0.45, "还行": 0.4, "过得去": 0.4,
    # 出圈 / 商业
    "出圈": 0.7, "圈粉": 0.75, "爆红": 0.5, "翻红": 0.55, "大卖": 0.7,
    "黑马": 0.65, "逆袭": 0.6, "回春": 0.5, "破纪录": 0.8,
    # 网络正向口头语
    "笑死": 0.3, "哈哈": 0.35, "哈哈哈": 0.4, "好耶": 0.7, "awsl": 0.6,
    "泪目": 0.45, "磕到了": 0.7,
}

NEGATIVE = {
    # 作品 / 表现
    "难看": -0.8, "难听": -0.8, "烂片": -0.9, "烂尾": -0.8, "尴尬": -0.6,
    "拉胯": -0.8, "敷衍": -0.75, "划水": -0.7, "摆烂": -0.8, "注水": -0.7,
    "出戏": -0.6, "油腻": -0.75, "做作": -0.7, "尬": -0.6,
    # 评价
    "差": -0.6, "烂": -0.9, "讨厌": -0.8, "恶心": -0.9, "反感": -0.8,
    "失望": -0.8, "无语": -0.7, "离谱": -0.8, "过分": -0.7, "可笑": -0.7,
    "荒谬": -0.8, "退钱": -0.7,
    # 事件 / 争议
    "塌房": -1.0, "翻车": -0.9, "人设崩塌": -1.0, "封杀": -0.8, "抵制": -0.9,
    "退圈": -0.6, "脱粉": -0.7, "黑热搜": -0.75, "买热搜": -0.75,
    "控评": -0.65, "水军": -0.7, "洗白": -0.75, "炒作": -0.75, "蹭": -0.6,
    "割韭菜": -0.85, "恰烂钱": -0.85, "圈钱": -0.8, "德不配位": -0.85,
    "造谣": -0.8, "造假": -0.9, "偷税": -1.0, "逃税": -1.0, "漏税": -0.9,
    "出轨": -0.9, "家暴": -1.0, "性侵": -1.0, "吸毒": -1.0, "嫖娼": -1.0,
    "违法": -0.9, "违规": -0.7, "处罚": -0.6, "罚款": -0.55, "通报": -0.45,
    "起诉": -0.55, "败诉": -0.7, "道歉": -0.35, "塌": -0.65, "崩": -0.6,
    # 情绪 / 负面事件
    "难过": -0.7, "悲痛": -0.8, "哀悼": -0.55, "惋惜": -0.45, "遗憾": -0.4,
    "去世": -0.6, "逝世": -0.6, "离世": -0.6, "病逝": -0.6, "安息": -0.3,
    "愤怒": -0.8, "气死": -0.8, "破防": -0.5, "emo": -0.5,
    # 网络负向口头语
    "呵呵": -0.5, "笑不出来": -0.6, "就这": -0.6, "无感": -0.35,
    "麻了": -0.55, "服了": -0.5, "醉了": -0.55,
}

# Multi-character idioms that would otherwise be torn apart by shorter terms.
NEGATIVE_IDIOMS = {
    "阴阳怪气": -0.75, "睁眼说瞎话": -0.85, "一言难尽": -0.6,
    "毁三观": -0.85, "没眼看": -0.7, "看不下去": -0.7,
}

# Emoji / kaomoji. Small on purpose: only the unambiguous ones.
EMOJI = {
    "❤": 0.6, "❤️": 0.6, "😍": 0.7, "😘": 0.6, "👍": 0.6, "🎉": 0.7,
    "😂": 0.3, "😭": -0.5, "😡": -0.8, "🤮": -0.9, "👎": -0.6,
    "🙄": -0.5, "💔": -0.7, "🌚": -0.3,
}

# Words that must *claim* their characters without carrying polarity, so a
# shorter positive term inside them (好 in 好像) cannot fire. Protective only.
NEUTRAL_TERMS = (
    "好像", "好久", "好处", "好奇", "只好", "刚好", "好在", "好比",
    "同学", "爱好", "好玩", "好些", "不足", "无数", "未来",
)

# Negators. Order matters only for readability; matching takes the longest.
NEGATORS = (
    "并不", "并没", "没有", "从未", "绝不", "毫不", "毫无", "谈不上", "算不上",
    "不至于", "不再", "不太", "不怎么", "不够", "不", "没", "无", "未", "别",
)

# Forms that *contain* a negator character but do not negate. Without this,
# "不过还算不错" would negate 不错 because of the 不 in 不过.
NEGATOR_EXCEPTIONS = (
    "不过", "不但", "不仅", "不光", "不少", "不久", "不同", "不管", "不论",
    "不得不", "不由得", "不停", "不断", "不知不觉", "忍不住", "恨不得",
    # 非常 is a degree adverb, not 非 + 常.
    "非常",
)

# Degree adverbs, applied when they sit within a few characters of the term.
DEGREE_UP = {
    "极其": 1.8, "极度": 1.8, "非常": 1.6, "超级": 1.6, "特别": 1.5,
    "十分": 1.5, "完全": 1.4, "彻底": 1.4, "太": 1.4, "超": 1.35,
    "巨": 1.4, "真的很": 1.4, "真的": 1.25, "很": 1.25, "贼": 1.35,
    "最": 1.4, "更": 1.15, "全网": 1.25, "一片": 1.15,
}
DEGREE_DOWN = {
    "有一点": 0.55, "有点": 0.6, "稍微": 0.55, "略": 0.55,
    "比较": 0.8, "还算": 0.7, "勉强": 0.6, "些许": 0.5, "不太": 0.7,
}

# Irony markers. These are the phrases that, in Chinese entertainment chatter,
# usually signal the opposite of the literal reading.
IRONY_MARKERS = (
    "呵呵", "真有你的", "好一个", "可真是", "不愧是", "就这",
    "笑死", "谢谢啊", "真行", "可以啊", "行吧", "牛啊", "高，实在是高",
    "绝了", "服了", "厉害了", "666",
)

# Phrases that contain an irony marker but are not ironic. Checked first.
IRONY_EXEMPTIONS = (
    "厉害了我的国", "厉害了，我的国", "笑死我了", "笑死我",
)

LEXICON_VERSION = "1.0"
