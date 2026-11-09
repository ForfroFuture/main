"""Optional DeepSeek synthesis for the chat panel.

The public DeepSeek website does not expose a documented, unauthenticated
search API. This module uses the configured Anthropic-compatible DeepSeek
endpoint when a key with balance is available; otherwise the caller keeps the
local data-grounded answer.
"""

from __future__ import annotations

import re
from typing import Any

import requests

from . import config

_SYSTEM = (
    "你是B站内容分析搭档。只基于用户提供的本地统计回答，不编造数字；"
    "理解上下文，使用中文，语气像人、可以幽默并加入一两句无意义的吐槽，"
    "但结论必须能落回数据。输出 Markdown。"
)


def _history_text(history: list[dict[str, Any]] | None, limit: int = 8) -> str:
    if not history:
        return "（无历史对话）"
    recent = history[-limit:]
    lines: list[str] = []
    for item in recent:
        role = "用户" if item.get("role") == "user" else "助手"
        content = re.sub(r"\s+", " ", str(item.get("content") or ""))
        lines.append(f"{role}：{content[:700]}")
    return "\n".join(lines)


def enhance_answer(
    query: str,
    local_answer: str,
    history: list[dict[str, Any]] | None = None,
    *,
    model: str | None = None,
) -> str:
    """Return a longer DeepSeek-synthesised answer, or raise on failure."""
    if not config.AI_BASE_URL or not config.AI_AUTH_TOKEN:
        raise RuntimeError("DeepSeek API 未配置")
    prompt = f"""请基于下面的本地数据分析，回答用户问题，并做综合分析。
要求：
1. 不得编造未提供的数字；数字只能来自“本地分析”。
2. 理解上下文，若用户是在追问，要承接上一轮。
3. 语言人性化、幽默、可以长一点；加入一到两句无意义的吐槽。
4. 给出补充观察、为什么值得看、下一周/下个月潜在热点（标注为预测/观察）。
5. 最后列出 3-5 条代表视频的标题和 B 站链接（只能使用本地分析中出现的链接）。
6. 输出 Markdown，不要输出思考过程。

历史对话：
{_history_text(history)}

用户问题：{query}

本地分析：
{local_answer[:6000]}
"""
    response = requests.post(
        config.AI_BASE_URL.rstrip("/") + "/v1/messages",
        headers={
            "x-api-key": config.AI_AUTH_TOKEN,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json; charset=utf-8",
        },
        json={
            "model": model or config.AI_MODEL,
            "max_tokens": 1400,
            "temperature": 0.75,
            "system": _SYSTEM,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=90,
    )
    if response.status_code in {401, 402, 403, 429}:
        raise RuntimeError(f"DeepSeek 暂不可用（HTTP {response.status_code}）")
    response.raise_for_status()
    body = response.json()
    text = "".join(
        str(block.get("text") or "")
        for block in body.get("content") or []
        if isinstance(block, dict) and block.get("type") == "text"
    ).strip()
    if not text:
        raise RuntimeError("DeepSeek 返回空内容")
    return text
