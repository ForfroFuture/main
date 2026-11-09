"""Deterministic, playful per-video insight copy (no external model calls)."""

from __future__ import annotations

import hashlib
import html
from typing import Any

import pandas as pd

from . import analytics


def _fmt_int(value: Any) -> str:
    try:
        return f"{int(float(value)):,}"
    except (TypeError, ValueError):
        return "0"


def _tag_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [item for item in str(value or "").split("|") if item.strip()]


def _pick(options: list[str], seed: str) -> str:
    if not options:
        return ""
    index = int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8], 16) % len(options)
    return options[index]


def video_insight(
    video: pd.Series,
    videos: pd.DataFrame,
    tag_freq: pd.DataFrame,
    parent_stats: pd.DataFrame,
) -> str:
    """Build a data-grounded, lightly humorous summary with a forecast."""
    if videos.empty:
        return "样本为空，暂时没法讲出有数据支撑的故事。"
    record = video.to_dict()
    category = str(record.get("category_parent") or "其他")
    tags = _tag_list(record.get("tags"))
    views = float(record.get("views") or 0)
    engagement = float(record.get("engagement_rate") or 0) * 100
    overall_median = float(pd.to_numeric(videos["views"], errors="coerce").median() or 0)
    category_rows = videos[videos["category_parent"].astype(str) == category]
    category_median = (
        float(pd.to_numeric(category_rows["views"], errors="coerce").median())
        if not category_rows.empty
        else overall_median
    )
    overall_engagement = (
        float(pd.to_numeric(videos["engagement_rate"], errors="coerce").median()) * 100
    )
    category_stats = parent_stats[parent_stats["category"].astype(str) == category]
    category_share = (
        float(category_stats.iloc[0]["share_pct"]) if not category_stats.empty else 0.0
    )
    view_ratio = views / category_median if category_median else 0
    engage_ratio = engagement / overall_engagement if overall_engagement else 0

    if engage_ratio >= 1.35:
        why = (
            f"互动率 {engagement:.2f}%，约全站中位的 {engage_ratio:.1f} 倍。"
            "观众不是点开就撤，而是顺手把赞、币、藏都按了一遍，手速多少有点失控。"
        )
    elif view_ratio >= 1.35:
        why = (
            f"播放量 {_fmt_int(views)}，约为 {category} 分区中位的 {view_ratio:.1f} 倍。"
            "题材和分发至少有一个踩中了按钮，观众是被推荐页一车一车送来的。"
        )
    else:
        why = (
            f"播放量 {_fmt_int(views)}，互动率 {engagement:.2f}%，不算数据怪物，"
            "更像是稳定发挥的耐力型选手。"
        )

    tag_text = "、".join(tags[:3]) if tags else "没有明显标签组合"
    category_candidates = tag_freq[tag_freq["top_category"].astype(str) == category] if not tag_freq.empty else pd.DataFrame()
    if not category_candidates.empty:
        candidates = [
            str(value)
            for value in category_candidates["tag"].tolist()
            if value not in tags
        ][:6]
    else:
        candidates = []
    if not candidates and not tag_freq.empty:
        candidates = [
            str(value) for value in tag_freq["tag"].tolist() if value not in tags
        ][:6]
    partner = candidates[0] if candidates else "同分区的新题材"
    partner2 = candidates[1] if len(candidates) > 1 else "跨分区二创"
    month_theme = candidates[2] if len(candidates) > 2 else category
    tone = _pick(
        [
            "这条视频的火法有点像电梯里突然有人开始跳舞：尴尬三秒，然后所有人都在看。",
            "数据告诉我们它被看见了，内容告诉我们它为什么值得被看见，评论区负责把两者拧成一股绳。",
            "如果说推荐页是广场，这条视频大概是在广场中央支了个摊，路过的人很难装没看见。",
            "它的流量不是天上掉下来的，更像是一套标签、分区和观众情绪刚好对齐后的连锁反应。",
        ],
        str(record.get("bvid") or record.get("title") or "insight"),
    )
    scope = f"{category}分区当前占样本 {category_share:.1f}%" if category_share else "当前分区"
    return (
        f"**先看数据侧写**：{_fmt_int(views)} 播放、{_fmt_int(record.get('likes'))} 点赞、"
        f"{_fmt_int(record.get('coins'))} 投币、{_fmt_int(record.get('favorites'))} 收藏、"
        f"{_fmt_int(record.get('replies'))} 评论、{_fmt_int(record.get('danmaku'))} 弹幕。"
        f"标签组合是「{tag_text}」，落在「{scope}」。\n\n"
        f"**为什么这周火了（人话版）**：{why} {tone}\n\n"
        f"**下一周 / 下个月看什么**：从同分区的高频标签看，"
        f"下一周可以留意「{partner}」和「{partner2}」的组合；下个月若「{month_theme}」"
        f"继续与「{category}」内容共振，可能会长成更稳定的题材带。"
        "预测只是从当前样本里推出来的观察，不是平台流量保证书。"
    )
