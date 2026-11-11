"""LLM-based event extraction.

Why an LLM instead of a classical NER pipeline: the things we need are
"who did what, when, according to whom" — relations, not entities. A
well-prompted model gets date + actor + action + source in one pass, and its
failure mode (inventing a date) is caught by the "no source URL, no row" gate
downstream.

The provider is not hard-coded: it speaks the OpenAI-compatible
`/chat/completions` shape, so OpenAI, DeepSeek, Qwen, Moonshot, vLLM, Ollama
and friends all work by changing two environment variables:

    WII_LLM_BASE_URL   e.g. https://api.deepseek.com/v1
    WII_LLM_API_KEY    your key
    WII_LLM_MODEL      e.g. deepseek-chat

With no key set, `--dry-run` prints the exact prompts instead of calling out.
The repo is fully runnable that way, which also means CI never needs a secret.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Sequence

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"

SYSTEM_PROMPT = """你是一个事实抽取器，不是评论员。

任务：从给定文本中抽取「已发生的事件」，输出结构化 JSON 数组。

硬性规则：
1. 只抽取文本中明确陈述的事实。文本没写的，一律 null，禁止推测、补充、联想。
2. 每一条事件必须带至少一个来源链接（原文 URL）。没有链接的内容不要输出。
3. 不评价人物品格，不使用「劣迹」「德不配位」这类定性词；只描述发生了什么。
4. 涉及未经证实的指控时，event_type 用 "allegation"，并在 title 中保留「被指」「疑似」等原文限定词，不得改写为既成事实。
5. 时间尽量精确：能到日就到日（YYYY-MM-DD）；只有年月就写该月（YYYY-MM，date_precision 标 month）；只有年份就写 YYYY（date_precision 标 year）；写成「近日」原样保留在 date_text，date_precision 标 relative。
6. 同一天的多件事要拆成多条，不要合并。

输出字段：
  artist_id        string  给定值，原样回填
  date_text        string  原文里的时间表述，原样摘录
  date_precision   "day" | "month" | "year" | "relative"
  title            string  ≤ 30 字，只陈述事实
  event_type       "endorsement_terminated" | "endorsement_added" | "production_cancelled"
                          | "institutional_response" | "policy_followup" | "award"
                          | "release" | "legal" | "allegation" | "statement" | "other"
  verticals        string[]  从 entertainment/culture/sports/tech/society/legal/finance/politics 里选
  sources          [{"url": "...", "publisher": "...", "tier": "central_media|local_media|industry_association|regulator|outlet"}]
  behavior         object   可选，键取自 endorsement_terminated / endorsement_added /
                            production_cancelled / institutional_response / policy_followup /
                            box_office_delta_pct / sales_delta_pct / market_move_pct
  authority        object   可选，键取自 central_media / local_media / industry_association / regulator，值为次数

只输出 JSON 数组，不要 markdown 代码块，不要解释。没有可抽取的事件就输出 []。"""

USER_TEMPLATE = """artist_id: {artist_id}
艺人：{artist_name}
参考日期（用于解析「近日」「昨日」等相对时间）：{reference_date}

待抽取文本（每段前面是它的来源 URL）：
{documents}"""


def build_prompt(
    artist_id: str, artist_name: str, reference_date: str, documents: Sequence[Dict[str, str]]
) -> List[Dict[str, str]]:
    docs = "\n\n".join(
        f"--- 来源: {d.get('url', 'UNKNOWN')} | 发布方: {d.get('publisher', '')}\n{d.get('text', '')}"
        for d in documents
    )
    user = USER_TEMPLATE.format(
        artist_id=artist_id,
        artist_name=artist_name,
        reference_date=reference_date,
        documents=docs or "（空）",
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def _chat(messages: List[Dict[str, str]], *, model: str, base_url: str, api_key: str, timeout: int) -> str:
    payload = json.dumps(
        {"model": model, "messages": messages, "temperature": 0.0, "response_format": {"type": "json_object"}},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - explicit https base_url
        body = json.loads(resp.read().decode("utf-8"))
    return body["choices"][0]["message"]["content"]


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def parse_response(text: str) -> List[Dict[str, Any]]:
    """Tolerant JSON extraction: fences, prose around the array, `{"events": [...]}`."""
    if not text:
        return []
    raw = text.strip()
    m = _FENCE.search(raw)
    if m:
        raw = m.group(1).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start = min((raw.find("["), raw.find("{")) , key=lambda i: i if i >= 0 else 10**9)
        if start == 10**9:
            return []
        try:
            data, _ = json.JSONDecoder().raw_decode(raw[start:])
        except json.JSONDecodeError:
            return []
    if isinstance(data, dict):
        data = data.get("events") or data.get("data") or []
    if not isinstance(data, list):
        return []
    return [d for d in data if isinstance(d, dict)]


def extract_events(
    artist_id: str,
    artist_name: str,
    reference_date: str,
    documents: Sequence[Dict[str, str]],
    *,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: int = 90,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Run one extraction call. Returns {"events": [...], "usage": {...}}."""
    model = model or os.environ.get("WII_LLM_MODEL", DEFAULT_MODEL)
    base_url = base_url or os.environ.get("WII_LLM_BASE_URL", DEFAULT_BASE_URL)
    api_key = api_key or os.environ.get("WII_LLM_API_KEY", "")
    messages = build_prompt(artist_id, artist_name, reference_date, documents)

    if dry_run or not api_key:
        return {
            "events": [],
            "usage": {
                "mode": "dry_run",
                "reason": "no WII_LLM_API_KEY set" if not api_key else "dry_run requested",
                "model": model,
                "base_url": base_url,
                "n_documents": len(documents),
            },
            "prompt_preview": messages[1]["content"][:2000],
        }

    try:
        content = _chat(messages, model=model, base_url=base_url, api_key=api_key, timeout=timeout)
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, TimeoutError) as exc:
        return {
            "events": [],
            "usage": {"mode": "error", "error": f"{type(exc).__name__}: {exc}"},
        }

    events = parse_response(content)
    for ev in events:
        ev.setdefault("artist_id", artist_id)
    return {"events": events, "usage": {"mode": "llm", "model": model, "n_events": len(events)}}
