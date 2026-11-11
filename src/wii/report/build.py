"""Self-contained HTML report.

One file, no external requests. Open it from disk, mail it, attach it to a
course submission, or publish it to GitHub Pages — it renders the same either
way.

Design rules followed here, because they are the difference between a report
and a leaderboard:

* the disclaimer is above the fold, not in the footer;
* every star is expandable down to raw counters and source URLs;
* the sentiment axis is drawn as its own axis with its own colour scale, never
  folded into the star number;
* the report prints the data fingerprint, so a screenshot can be traced back
  to an exact byte sequence.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, Optional

from .. import config
from . import svg as S


CSS = """
:root{
  --ink:#1f2328; --muted:#6b7280; --line:#e5e7eb; --paper:#ffffff;
  --bg:#f6f7f9; --accent:#2f4858; --warn:#b23a48; --ok:#2f6f4f;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font-family:'Segoe UI','Microsoft YaHei',-apple-system,BlinkMacSystemFont,Arial,sans-serif;
  font-size:15px;line-height:1.65;-webkit-font-smoothing:antialiased}
.wrap{max-width:1060px;margin:0 auto;padding:40px 24px 72px}
header h1{font-size:30px;line-height:1.25;margin:0 0 6px;letter-spacing:-.3px}
header .sub{color:var(--muted);font-size:14px;margin:0 0 18px}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:22px}
.chip{background:#fff;border:1px solid var(--line);border-radius:999px;padding:4px 12px;
  font-size:12.5px;color:var(--muted)}
.chip b{color:var(--ink);font-weight:600}
.card{background:var(--paper);border:1px solid var(--line);border-radius:12px;
  padding:22px 24px;margin:0 0 20px}
.card h2{font-size:17px;margin:0 0 4px;letter-spacing:-.2px}
.card h2 .tag{font-size:12px;font-weight:500;color:var(--muted);margin-left:8px}
.card .lead{color:var(--muted);font-size:13.5px;margin:0 0 18px}
.warn{border-left:4px solid var(--warn);background:#fdf6f6}
.warn h2{color:var(--warn)}
.warn ul{margin:8px 0 0;padding-left:20px;font-size:13.5px}
.warn li{margin:3px 0}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
.tile{border:1px solid var(--line);border-radius:10px;padding:14px 16px;background:#fbfcfd}
.tile .k{font-size:12px;color:var(--muted);letter-spacing:.02em}
.tile .v{font-size:14px;font-weight:600;margin:2px 0 6px}
.tile p{margin:0;font-size:12.5px;color:var(--muted)}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{padding:5px 8px;text-align:left;border-bottom:1px solid var(--line)}
th{font-weight:600;color:var(--muted);font-size:12px;background:#fafbfc}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
table.heat th.row{background:#fff;font-weight:600;color:var(--ink)}
table.heat td{text-align:center;font-variant-numeric:tabular-nums;color:#1a1a1a;border:2px solid #fff}
.chart{display:block;width:100%;height:auto}
details.artist{background:var(--paper);border:1px solid var(--line);border-radius:12px;
  margin:0 0 10px;overflow:hidden}
details.artist>summary{cursor:pointer;padding:13px 20px;display:flex;align-items:center;gap:14px;
  list-style:none;font-size:15px}
details.artist>summary::-webkit-details-marker{display:none}
details.artist>summary:hover{background:#fafbfc}
summary .nm{font-weight:600;min-width:90px}
summary .st{font-variant-numeric:tabular-nums;font-weight:600;min-width:62px}
summary .val{font-size:12.5px;min-width:96px}
summary .meta{color:var(--muted);font-size:12.5px;margin-left:auto;text-align:right}
.body{padding:4px 20px 22px;border-top:1px solid var(--line)}
.body h3{font-size:13px;color:var(--muted);margin:18px 0 8px;font-weight:600;letter-spacing:.03em}
.ev{border-left:2px solid var(--line);padding:6px 0 6px 14px;margin:0 0 10px}
.ev .t{font-weight:600;font-size:13.5px}
.ev .d{font-size:12px;color:var(--muted);margin:2px 0 4px}
.ev a{color:#2f4858;font-size:12px;word-break:break-all}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:11.5px}
footer{color:var(--muted);font-size:12px;margin-top:28px;line-height:1.8}
footer .fp{font-family:ui-monospace,Menlo,Consolas,monospace;word-break:break-all}
.pass{color:var(--ok);font-weight:600}
.fail{color:var(--warn);font-weight:600}
@media (max-width:820px){.grid3{grid-template-columns:1fr}.wrap{padding:24px 14px 48px}}
@media print{body{background:#fff}.card,details.artist{break-inside:avoid}}
"""

DISCLAIMER_ITEMS = [
    "本报告衡量的是<b>公开注意力</b>（attention），不是人物的品德、能力或法律责任。"
    "星级高只说明「被谈论得又多又久」，不说明「好」。",
    "<b>舆论提及 ≠ 事实</b>。负面提及比例高，可能来自大规模谣言。事实请只看「已核实事件」表，"
    "每一条都必须带可点击的原始信源。",
    "星级是<b>相对指数</b>：只在同一 cohort、同一时间窗、同一版本公式内可比。"
    "跨时代、跨平台、跨版本的排名没有意义。",
    "若用于真实在世自然人，需自行评估民法典人格权编、个人信息保护法及平台条款的合规性；"
    "公开发布建议限定学术或内部研究用途，并保留本声明。",
]


def _chips(result) -> str:
    window = (
        f"{result.window_start.isoformat()} ~ {result.window_end.isoformat()}"
        if result.window_start and result.window_end
        else "未知"
    )
    items = [
        ("指数版本", result.index_version),
        ("口径", "相对指数（cohort 内可比）"),
        ("归一化", "分位数" if result.normalization == "percentile" else "Z 分数→正态CDF"),
        ("样例量", f"{len(result.artists)} 位"),
        ("时间窗", window),
        ("数据指纹", result.data_fingerprint[:12] + "…" if result.data_fingerprint else "—"),
    ]
    return "".join(f'<span class="chip">{S.esc(k)} <b>{S.esc(v)}</b></span>' for k, v in items)


def _read_guide() -> str:
    return """
<div class="card">
  <h2>怎么读这张表</h2>
  <p class="lead">三个层次，故意分开画，不许互相冒充。</p>
  <div class="grid3">
    <div class="tile">
      <div class="k">横轴 / 条形长度</div>
      <div class="v">影响幅度（1-10 星）</div>
      <p>六个可测因子加权合成：触达规模、持续时间、情感强度、跨圈层外溢、行为改变、权威介入。</p>
    </div>
    <div class="tile">
      <div class="k">纵轴 / 颜色</div>
      <div class="v">情感极性（-1 ~ +1）</div>
      <p>「影响很大但极负面」和「影响中等但很正面」是两件事。压成一个数字会丢信息，所以极性单独一根轴。</p>
    </div>
    <div class="tile">
      <div class="k">事实层</div>
      <div class="v">已核实事件（带链接）</div>
      <p>只收录公开报道且有明确信源的事件。舆论表与事实表是两张表，永不合并。</p>
    </div>
  </div>
</div>"""


def _weights_table(weights: Dict[str, float]) -> str:
    rows = []
    for f in config.FACTORS:
        meta = config.FACTOR_META[f]
        rows.append(
            f"<tr><td><span style='display:inline-block;width:9px;height:9px;border-radius:2px;"
            f"background:{meta['color']};margin-right:7px'></span>{S.esc(meta['zh'])}</td>"
            f"<td class='num'>{weights[f]:.2f}</td><td>{S.esc(meta['question'])}</td>"
            f"<td>{S.esc(meta['inputs'])}</td></tr>"
        )
    caps = ", ".join(f"{k} ≤ {v:g}" for k, v in config.CAPS.items())
    return f"""
<table>
  <thead><tr><th>因子</th><th class="num">权重</th><th>它回答的问题</th><th>输入</th></tr></thead>
  <tbody>{''.join(rows)}</tbody>
</table>
<p class="lead" style="margin-top:14px">
  公式：<span class="mono">M = Σ w_i · n_i</span>，
  <span class="mono">stars = 1 + 9 × M</span>；封顶：<span class="mono">{S.esc(caps)}</span>。
  权重是参数，不是真理：改权重会改星级，所以权重、版本号与数据指纹一起印在报告上。
</p>"""


def _validation_block(validation: Optional[Dict[str, Any]]) -> str:
    if not validation:
        return ""
    rows = []
    for c in validation.get("checks", []):
        cls = "pass" if c["passed"] else "fail"
        mark = "✓" if c["passed"] else "✗"
        rows.append(
            f"<tr><td class='{cls}'>{mark}</td><td class='mono'>{S.esc(c['name'])}</td>"
            f"<td>{S.esc(c['detail'])}</td></tr>"
        )
    verdict = (
        "<span class='pass'>全部通过</span>"
        if validation.get("passed")
        else "<span class='fail'>存在未通过项</span>"
    )
    return f"""
<div class="card">
  <h2>校验<span class="tag">回测与常识断言</span></h2>
  <p class="lead">排名一致性 Spearman ρ = {validation.get('spearman')}，
  Kendall τ = {validation.get('kendall')}，Top-K 重合 {validation.get('top_k_overlap')}。整体：{verdict}。</p>
  <table><thead><tr><th style="width:34px"></th><th style="width:230px">检查项</th><th>结果</th></tr></thead>
  <tbody>{''.join(rows)}</tbody></table>
  <p class="lead" style="margin-top:12px">规则：任何一项失败，回去调权重或改因子定义，绝不修改期望值来凑结论。</p>
</div>"""


def _artist_block(
    a,
    result,
    weights: Dict[str, float],
    *,
    open_block: bool = False,
) -> str:
    stars = f"{a.stars:.1f}"
    val_color = S.valence_color(a.valence)
    rows = []
    for f in sorted(config.FACTORS, key=lambda x: -a.contribution[x]):
        meta = config.FACTOR_META[f]
        rows.append(
            f"<tr><td><span style='display:inline-block;width:9px;height:9px;border-radius:2px;"
            f"background:{meta['color']};margin-right:7px'></span>{S.esc(meta['zh'])}</td>"
            f"<td class='num'>{weights[f]:.2f}</td>"
            f"<td class='num'>{a.raw[f]:.3f}</td>"
            f"<td class='num'>{a.normalized[f]:.3f}</td>"
            f"<td class='num'>{a.contribution[f]:.3f}</td>"
            f"<td class='num'>{9 * a.contribution[f]:.2f}</td>"
            f"<td class='mono' style='color:#6b7280'>{S.esc(_diag_oneline(f, a.factors_diag.get(f, {})))}</td></tr>"
        )

    evidence = []
    for ev in a.evidence:
        links = " · ".join(
            f'<a href="{S.esc(s["url"])}" rel="noreferrer noopener" target="_blank">{S.esc(s.get("publisher") or s["url"])}</a>'
            for s in ev.get("sources", [])
        )
        flags = []
        if ev.get("synthetic"):
            flags.append("合成示例")
        evidence.append(
            f'<div class="ev"><div class="t">{S.esc(ev["title"])}</div>'
            f'<div class="d">{ev["date"]} · {S.esc(ev["event_type"])} · '
            f'{S.esc("、".join(ev.get("verticals") or []))}'
            + (f' · {" / ".join(flags)}' if flags else "")
            + f'</div><div>{links}</div></div>'
        )
    if not evidence:
        evidence.append('<p class="lead">该窗口内无已核实事件。这不等于「什么都没发生」，只等于「没有可引用的信源」。</p>')

    vd = a.valence_diag
    val_detail = (
        f"样本 {vd.get('n', 0):,} 条（剔除疑似水军 {vd.get('spam_excluded', 0):,} 条，"
        f"占 {vd.get('spam_ratio', 0) * 100:.1f}%）；"
        f"正 {vd.get('share_positive', 0) * 100:.0f}% / 中性 {vd.get('share_neutral', 0) * 100:.0f}% / "
        f"负 {vd.get('share_negative', 0) * 100:.0f}%；极性标准差 {a.valence_sd:.2f}"
    )

    timeline = S.mini_timeline(a.evidence, result.window_start, result.window_end, width=900, height=112)

    return f"""
<details class="artist"{' open' if open_block else ''}>
  <summary>
    <span class="nm">{S.esc(a.name)}</span>
    <span class="st">{stars} ★</span>
    <span class="val" style="color:{val_color}">{a.valence:+.2f} {S.esc(a.valence_diag.get('label') or '')}</span>
    <span class="meta">{len(a.evidence)} 条已核实事件 · 主导因子：
      {S.esc(config.FACTOR_META[max(config.FACTORS, key=lambda f: a.contribution[f])]['zh'])}</span>
  </summary>
  <div class="body">
    <h3>因子分解（为什么是 {stars} 星）</h3>
    <table>
      <thead><tr><th>因子</th><th class="num">权重</th><th class="num">原始量</th>
      <th class="num">归一值</th><th class="num">贡献</th><th class="num">折合星级</th><th>口径</th></tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table>
    <h3>已核实事件时间线</h3>
    {timeline}
    <h3>信源</h3>
    {''.join(evidence)}
    <h3>情感极性（单独一根轴，不进星级）</h3>
    <p class="lead">{S.esc(val_detail)}</p>
  </div>
</details>"""


def _diag_oneline(factor: str, diag: Dict[str, Any]) -> str:
    if factor == "reach":
        return (
            f"阅读 {diag.get('total_reads', 0):,} / 讨论 {diag.get('total_discussions', 0):,} / "
            f"热搜 {diag.get('hotsearch_entries', 0)} / {len(diag.get('platforms', []))} 平台"
        )
    if factor == "duration":
        fit = diag.get("decay_fit") or {}
        return (
            f"有效 {diag.get('active_days', 0)} 天 / 半衰期 {diag.get('half_life_days', 0)} 天"
            f"（拟合点 {fit.get('fit_points', 0)}）"
        )
    if factor == "intensity":
        return f"|s| 加权均值 {diag.get('weighted_mean_abs_sentiment', 0):.3f}"
    if factor == "spillover":
        vs = diag.get("verticals_reached") or []
        return "外溢：" + ("、".join(vs) if vs else "无")
    if factor == "behavior":
        return f"{len(diag.get('items') or [])} 项行为改变"
    if factor == "authority":
        items = diag.get("items") or []
        tiers = sorted({i.get("tier", "") for i in items})
        return f"{len(items)} 次介入" + (f"（{'/'.join(tiers)}）" if tiers else "")
    return ""


def build_html(
    result,
    out_path: Path,
    *,
    validation: Optional[Dict[str, Any]] = None,
    anonymize: bool = False,
    data_note: str = "",
) -> Path:
    ranked = result.ranked()
    if anonymize:
        # Rewrite the name on a copy so every downstream renderer (charts
        # included) anonymises without having to know about the flag.
        ranked = [replace(a, name=f"艺人 {chr(ord('A') + i)}") for i, a in enumerate(ranked)]

    mean_stars = sum(a.stars for a in ranked) / len(ranked)
    controversy = [a for a in ranked if a.valence < -config.VALENCE_NEUTRAL_BAND]
    facts = sum(len(a.evidence) for a in ranked)

    summary_tiles = f"""
  <div class="grid3" style="margin-bottom:4px">
    <div class="tile"><div class="k">平均星级</div><div class="v">{mean_stars:.2f} ★</div>
      <p>cohort 内相对值，跨 cohort 不可比。</p></div>
    <div class="tile"><div class="k">负向艺人</div><div class="v">{len(controversy)} / {len(ranked)}</div>
      <p>极性低于 -{config.VALENCE_NEUTRAL_BAND}；与「是否做错事」无关。</p></div>
    <div class="tile"><div class="k">已核实事件</div><div class="v">{facts} 条</div>
      <p>每条都挂原始链接；没有链接的内容没有进这张表。</p></div>
  </div>"""

    artists_html = "".join(
        _artist_block(a, result, result.weights, open_block=(i == 0))
        for i, a in enumerate(ranked)
    )

    generated = result.generated_at or _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()

    body = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>微博舆论影响力指数 · {S.esc(result.cohort_label)}</title>
<meta name="description" content="A reproducible, auditable public-opinion influence index. Magnitude on the star axis, sentiment polarity on a separate axis.">
<style>{CSS}</style>
</head>
<body>
<div class="wrap">

<header>
  <h1>微博舆论影响力指数<span style="font-size:15px;font-weight:500;color:#6b7280"> · Weibo Attention &amp; Influence Index</span></h1>
  <p class="sub">{S.esc(result.cohort_label)}｜权威介入、行为改变、跨圈层外溢等六因子合成的<b>相对指数</b>，
  每个星级都能点开到原始计数与信源。</p>
  <div class="chips">{_chips(result)}</div>
</header>

<section class="card warn">
  <h2>先看这个</h2>
  <ul>{''.join(f'<li>{item}</li>' for item in DISCLAIMER_ITEMS)}</ul>
</section>

{_read_guide()}

<section class="card">
  <h2>幅度 × 极性<span class="tag">散点：气泡大小 = 触达百分位</span></h2>
  <p class="lead">右上角 = 影响大且评价正面；右下角 = 影响大但评价负面（塌房区）；
  左下角 = 影响小。这两根轴刻意分开，因为它们回答的不是同一个问题。</p>
  {S.scatter(ranked)}
</section>

<section class="card">
  <h2>六因子贡献分解<span class="tag">条形长度 = 合成幅度 M</span></h2>
  <p class="lead">每家艺人的星级都由这些彩色段拼成。鼠标悬停任意色块可看到「权重 × 归一值 = 贡献」。</p>
  {S.stacked_contributions(ranked, result.weights)}
</section>

<section class="card">
  <h2>因子归一值热力表<span class="tag">0 = 全 cohort 最低，1 = 最高</span></h2>
  <p class="lead">这一列一列地看，就能看出每个人的星级是被哪个因子撑起来的。</p>
  {S.heat_table(ranked)}
</section>

<section class="card">
  <h2>总览</h2>
  {summary_tiles}
</section>

{_validation_block(validation)}

<div class="card">
  <h2>逐人拆解<span class="tag">点开看依据</span></h2>
  <p class="lead">每一项都展开到「原始量 → 归一值 → 贡献 → 折合星级」，并附已核实事件与信源链接。</p>
</div>
{artists_html}

<section class="card">
  <h2>方法与口径</h2>
  <p class="lead">完整推导见仓库的 METHODOLOGY.md；这里是复算所需的最小信息集。</p>
  {_weights_table(result.weights)}
</section>

<section class="card">
  <h2>数据来源与已知限制</h2>
  <ul style="font-size:13.5px;padding-left:20px">
    <li>数据表：{S.esc("、".join(result.tables_used) or "—")}。{S.esc(data_note)}</li>
    <li>注意力 ≠ 影响：本指数测的是「被谈论的规模与持久度」，不是「改变了多少人的行为」。
        命名上它叫 attention index，不叫 impact index。</li>
    <li>中文反讽（「呵呵」「真有你的」）会让词典法情感分析系统性出错；本版用账号加权缓解控评，
        但不能消除。极性数字应视为「语调分布」，不是民意调查。</li>
    <li>跨年代不可比：2010 年前没有可比的社交媒体计数，因此本指数只对窗口内的数据成立。</li>
    <li>触达使用平台口径的累计阅读量，是曝光次数代理，不是去重人数，故不提供置信区间。</li>
  </ul>
</section>

<footer>
  <div>生成时间（UTC）：{S.esc(generated)}　·　指数版本 {S.esc(result.index_version)}　·　
    归一化 {S.esc(result.normalization)}</div>
  <div class="fp">数据指纹 SHA-256：{S.esc(result.data_fingerprint or "—")}</div>
  <div>本文件由 weibo-influence-index 自动生成，MIT 许可。指数衡量公开注意力，不构成对任何自然人的评价。</div>
</footer>

</div>
</body>
</html>
"""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(body)
    return out_path
