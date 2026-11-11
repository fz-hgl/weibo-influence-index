"""Command line interface.

    wii demo      --out data/demo          生成合成演示数据（确定性、可复跑）
    wii build     --data data/demo         算指数 + 出报告
    wii validate  --data data/demo         回测、常识断言与权重稳定性
    wii explain   --data data/demo --artist a01
    wii sensitivity --data data/demo       权重扰动下的排名稳定性
    wii sentiment --data data/demo         用内置词典法给提及文本打情感分
    wii audit-sample / audit-score         人工抽检准确率
    wii prompt    --artist-id a01          打印抽取用的 prompt（不需要 API key）

Every command is read-only except `demo` (writes data) and `build`/`sentiment`/
`audit-*` (writes under --out). Nothing touches the network without
WII_LLM_API_KEY.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

from . import config, sentiment
from .extract import audit
from .ingest import fixtures
from .report import build_html
from .score import explain as explain_mod
from .score.index import compute_index
from .store import (
    dump_json,
    fingerprint,
    load_cohort,
    read_jsonl,
    resolve_data_dir,
    utc_now_iso,
    window_label,
    write_jsonl,
)
from .validate import backtest

DEFAULT_DATA = "data/demo"
DEFAULT_OUT = "build"


def _ensure_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):  # pragma: no cover
            pass


def _parse_weight_overrides(pairs: Optional[List[str]]) -> Dict[str, float]:
    weights = dict(config.DEFAULT_WEIGHTS)
    for item in pairs or []:
        if "=" not in item:
            raise SystemExit(f"--w expects factor=value, got {item!r}")
        key, value = item.split("=", 1)
        key = key.strip()
        if key not in config.FACTORS:
            raise SystemExit(f"unknown factor {key!r}; choose from {config.FACTORS}")
        weights[key] = float(value)
    return config.validate_weights(weights)


def _load(data_dir: Path):
    cohort, tables = load_cohort(data_dir, require=("artists.jsonl",))
    return cohort, tables


def _compute(data_dir: Path, args):
    cohort, tables = _load(data_dir)
    weights = _parse_weight_overrides(getattr(args, "w", None))
    sentiment_mode = getattr(args, "sentiment", "none")
    rescored = sentiment_mode == "lexicon"
    if rescored:
        cohort = sentiment.rescore_cohort(cohort, use_irony=not getattr(args, "no_irony", False))
    result = compute_index(
        cohort,
        weights=weights,
        normalization=args.normalization,
        cohort_label=f"{len(cohort.artists)} 位艺人 · {window_label(cohort.window_start, cohort.window_end)}",
        fingerprint=fingerprint(data_dir),
        tables_used=tables,
        generated_at=utc_now_iso(),
    )
    if rescored:
        result.notes.append(
            "情感极性由内置词典法（lexicon "
            f"{sentiment.LEXICON_VERSION}）从文本质地重算，未使用文件里的 sentiment 字段。"
        )
    return cohort, result


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------
def cmd_demo(args) -> int:
    out = Path(args.out)
    stats = fixtures.generate(out, seed=args.seed)
    print(f"已生成合成数据 → {out}")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print("\n注意：全部人物与来源均为合成（fictional=true / example.org），不对应任何真实自然人。")
    return 0


def cmd_build(args) -> int:
    data_dir = Path(args.data)
    cohort, result = _compute(data_dir, args)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    validation_payload = None
    expectations_path = data_dir / "expectations.json"
    if expectations_path.is_file():
        expectations = backtest.load_expectations(expectations_path)
        report = backtest.run_backtest(result, expectations, cohort=cohort)
        validation_payload = report.to_dict()
        dump_json(out_dir / "validation.json", validation_payload)

    dump_json(out_dir / "index.json", result.to_dict())
    report_path = build_html(
        result,
        out_dir / "report.html",
        validation=validation_payload,
        anonymize=args.anonymize,
        data_note="" if not args.anonymize else "报告已匿名化输出。",
    )

    print(f"cohort : {len(cohort.artists)} 位 · 窗口 {window_label(cohort.window_start, cohort.window_end)}")
    print(f"归一化 : {result.normalization}")
    print(f"指纹   : {result.data_fingerprint[:16]}…")
    print("")
    for a in result.ranked():
        bar = "█" * max(1, int(round(a.stars)))
        print(f"  {a.stars:>4.1f} ★ {bar:<10} {a.name:<6} 极性 {a.valence:+.2f} {a.valence_diag.get('label','')}")
    print("")
    print(f"报告   : {report_path}")
    print(f"数据   : {out_dir / 'index.json'}")
    if validation_payload:
        status = "PASS" if validation_payload["passed"] else "FAIL"
        print(f"校验   : {status}（详见 {out_dir / 'validation.json'}）")
    return 0


def cmd_validate(args) -> int:
    data_dir = Path(args.data)
    cohort, result = _compute(data_dir, args)
    path = Path(args.expectations) if args.expectations else data_dir / "expectations.json"
    if not path.is_file():
        print(f"找不到期望文件 {path}：没有基准就无法校验，别自己给自己打分。", file=sys.stderr)
        return 2
    report = backtest.run_backtest(result, backtest.load_expectations(path), cohort=cohort)
    print(backtest.render_text(report))
    if args.json:
        dump_json(Path(args.json), report.to_dict())
    return 0 if report.passed else 1


def cmd_explain(args) -> int:
    data_dir = Path(args.data)
    _, result = _compute(data_dir, args)
    payload = explain_mod.explain_index(result, args.artist)
    if args.json:
        dump_json(Path(args.json), payload)
        print(f"已写入 {args.json}")
    elif args.artist:
        print(explain_mod.render_text(payload))
    else:
        for item in payload["artists"]:
            print(explain_mod.render_text(item))
            print("")
    return 0


def cmd_sensitivity(args) -> int:
    data_dir = Path(args.data)
    cohort, _ = _load(data_dir)
    rows = backtest.weight_sensitivity(
        cohort,
        _parse_weight_overrides(getattr(args, "w", None)),
        normalization=args.normalization,
    )
    print("权重扰动 ±5% 时的排名与星级稳定性")
    print("=" * 46)
    for r in rows:
        flag = "稳定" if r["stable"] else "敏感 ← 这个因子的测量还不可靠"
        print(
            f"  {r['label_zh']:<8} 最大位移 {r['max_rank_shift']} 名"
            f" / {r['max_star_shift']:.2f} ★   {flag}"
        )
    if args.json:
        dump_json(Path(args.json), {"rows": rows})
    return 0


def cmd_sentiment(args) -> int:
    src = Path(args.input) if args.input else Path(args.data) / "mentions.jsonl"
    if not src.is_file():
        print(f"找不到提及表：{src}", file=sys.stderr)
        return 2
    rows = read_jsonl(src)
    scored = sentiment.score_rows(rows, use_irony=not args.no_irony)
    summary = sentiment.summarize(scored)
    empty = sum(1 for r in rows if not str(r.get("text") or "").strip())

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(out, scored)

    mean = summary["mean"]
    label = (
        "偏正面" if mean > config.VALENCE_NEUTRAL_BAND
        else "偏负面" if mean < -config.VALENCE_NEUTRAL_BAND
        else "中性 / 撕裂"
    )
    print(f"情感打分（lexicon {sentiment.LEXICON_VERSION}，反讽规则{'开' if not args.no_irony else '关'}）")
    print("=" * 52)
    print(f"  来源      {src}")
    print(f"  提及      {summary['n']:,} 条" + (f"（其中 {empty:,} 条无文本，按中性计）" if empty else ""))
    print(f"  加权均值  {mean:+.3f}  {label}")
    print(
        f"  分布      正 {summary['share_positive'] * 100:.0f}% / "
        f"中性 {summary['share_neutral'] * 100:.0f}% / 负 {summary['share_negative'] * 100:.0f}%"
    )
    print(f"  反讽      {summary['irony_rate'] * 100:.1f}% 命中规则（规则不是分类器，会错）")
    print(
        f"  置信      均值 {summary['mean_confidence']:.2f}，"
        f"低于 0.5 的占 {summary['low_confidence_share'] * 100:.1f}%"
    )
    if summary["top_terms"]:
        top = "  ".join(f"{t['term']}×{t['count']}" for t in summary["top_terms"][:8])
        print(f"  高频词    {top}")
    print(f"  输出      {out}")

    payload: Dict[str, object] = {"summary": summary, "source": str(src), "output": str(out)}
    if args.compare:
        pairs = [
            (float(r["sentiment_original"]), float(r["sentiment"]))
            for r in scored
            if r.get("sentiment_original") is not None
        ]
        cmp = sentiment.agreement(pairs)
        payload["agreement"] = cmp
        print("")
        print("与文件里原有 sentiment 的一致性（不判断谁更接近真相）")
        if cmp.get("n"):
            print(
                f"  MAE {cmp['mae']:.3f}　同号率 {cmp['sign_agreement'] * 100:.1f}%　"
                f"明确极性一致率 {(cmp['clear_polarity_agreement'] or 0) * 100:.1f}%"
            )
    if args.json:
        dump_json(Path(args.json), payload)
    return 0


def cmd_audit_sample(args) -> int:
    data_dir = Path(args.data)
    events = [
        json.loads(line)
        for line in (data_dir / "events_verified.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    rows = audit.sample_for_review(events, n=args.n, seed=args.seed)
    out = Path(args.out)
    audit.write_review_csv(out, rows)
    print(f"已抽取 {len(rows)} 条 → {out}")
    print("请填写 verdict 列（ok / bad_date / bad_title / no_source / fabricated），然后：")
    print(f"  wii audit-score --csv {out}")
    return 0


def cmd_audit_score(args) -> int:
    rows = audit.read_review_csv(Path(args.csv))
    payload = audit.score_review(rows)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.json:
        dump_json(Path(args.json), payload)
    return 0 if payload.get("accuracy", 0) >= 0.9 or payload.get("labelled", 0) == 0 else 1


def cmd_prompt(args) -> int:
    from .extract.llm import build_prompt

    docs = [
        {
            "url": "https://example.org/news/1",
            "publisher": "示例媒体",
            "text": "（把这里换成你抓到的正文段落；本命令不发网络请求，只打印 prompt。）",
        }
    ]
    messages = build_prompt(args.artist_id, args.artist_name or args.artist_id, args.reference_date, docs)
    for m in messages:
        print(f"--- {m['role']} ---")
        print(m["content"])
        print("")
    return 0


def cmd_weights(args) -> int:
    print(json.dumps({"weights": config.WEIGHTS, "factors": config.FACTORS,
                      "normalization": config.DEFAULT_NORMALIZATION,
                      "caps": config.CAPS}, ensure_ascii=False, indent=2))
    return 0


# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="wii",
        description="微博舆论影响力指数：六因子、可复算、可解释的相对指数。",
    )
    p.add_argument("--version", action="version", version=f"wii {config.INDEX_VERSION}")
    sub = p.add_subparsers(dest="command", required=True)

    def add_common(sp, with_data=True):
        if with_data:
            sp.add_argument("--data", default=DEFAULT_DATA, help=f"数据目录（默认 {DEFAULT_DATA}）")
        sp.add_argument(
            "--normalization",
            default=config.DEFAULT_NORMALIZATION,
            choices=list(config.NORMALIZATION_METHODS),
        )
        sp.add_argument("--w", action="append", metavar="factor=value", help="覆盖权重，可重复")
        sp.add_argument(
            "--sentiment",
            default="none",
            choices=("none", "lexicon"),
            help="lexicon = 用内置词典法从文本重算极性（不信任文件里的 sentiment）",
        )
        sp.add_argument("--no-irony", action="store_true", help="关闭反讽规则")

    d = sub.add_parser("demo", help="生成确定性合成演示数据")
    d.add_argument("--out", default=DEFAULT_DATA)
    d.add_argument("--seed", type=int, default=fixtures.SEED)
    d.set_defaults(func=cmd_demo)

    b = sub.add_parser("build", help="计算指数并生成 HTML 报告")
    add_common(b)
    b.add_argument("--out", default=DEFAULT_OUT)
    b.add_argument("--anonymize", action="store_true", help="报告中隐去艺人姓名")
    b.set_defaults(func=cmd_build)

    v = sub.add_parser("validate", help="回测与常识断言")
    add_common(v)
    v.add_argument("--expectations", default=None)
    v.add_argument("--json", default=None)
    v.set_defaults(func=cmd_validate)

    e = sub.add_parser("explain", help="打印某人星级的完整算法拆解")
    add_common(e)
    e.add_argument("--artist", default=None, help="artist_id；不给则输出全部")
    e.add_argument("--json", default=None)
    e.set_defaults(func=cmd_explain)

    s = sub.add_parser("sensitivity", help="权重扰动下的排名稳定性")
    s.add_argument("--data", default=DEFAULT_DATA)
    s.add_argument("--normalization", default=config.DEFAULT_NORMALIZATION,
                   choices=list(config.NORMALIZATION_METHODS))
    s.add_argument("--w", action="append", metavar="factor=value")
    s.add_argument("--json", default=None)
    s.set_defaults(func=cmd_sensitivity)

    se = sub.add_parser("sentiment", help="用内置词典法给提及文本打情感分（离线）")
    se.add_argument("--data", default=DEFAULT_DATA, help=f"数据目录（默认 {DEFAULT_DATA}）")
    se.add_argument("--input", default=None, help="直接指定 mentions.jsonl 路径")
    se.add_argument("--out", default="build/mentions.scored.jsonl")
    se.add_argument("--no-irony", action="store_true", help="关闭反讽规则")
    se.add_argument("--compare", action="store_true", help="与文件里原有 sentiment 比较")
    se.add_argument("--json", default=None)
    se.set_defaults(func=cmd_sentiment)

    a1 = sub.add_parser("audit-sample", help="抽取待人工核查的事件样本")
    a1.add_argument("--data", default=DEFAULT_DATA)
    a1.add_argument("--n", type=int, default=100)
    a1.add_argument("--seed", type=int, default=7)
    a1.add_argument("--out", default="build/review.csv")
    a1.set_defaults(func=cmd_audit_sample)

    a2 = sub.add_parser("audit-score", help="根据人工标注计算抽取准确率")
    a2.add_argument("--csv", required=True)
    a2.add_argument("--json", default=None)
    a2.set_defaults(func=cmd_audit_score)

    pr = sub.add_parser("prompt", help="打印事件抽取 prompt（离线，不调用模型）")
    pr.add_argument("--artist-id", default="a01")
    pr.add_argument("--artist-name", default=None)
    pr.add_argument("--reference-date", default="2026-03-01")
    pr.set_defaults(func=cmd_prompt)

    wt = sub.add_parser("weights", help="打印当前权重与封顶配置")
    wt.set_defaults(func=cmd_weights)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    _ensure_utf8()
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "data", None):
        args.data = str(resolve_data_dir(args.data))
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
