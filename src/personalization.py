"""Personalised ranking and narrative on top of the weekly dataset."""

from __future__ import annotations

import json
from typing import Any, Iterable

import pandas as pd

from . import analytics


def _tags(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [item for item in str(value or "").split("|") if item.strip()]


def recommend(
    videos: pd.DataFrame,
    *,
    categories: Iterable[str] = (),
    tags: Iterable[str] = (),
    top_n: int = 10,
) -> pd.DataFrame:
    """Blend weighted heat, category affinity, tag affinity and engagement."""
    if videos.empty:
        return pd.DataFrame()
    frame = analytics.add_weighted_score(videos)
    category_set = {str(item) for item in categories if item}
    tag_set = {str(item) for item in tags if item}
    frame["heat_pct"] = frame["weighted_score"].rank(pct=True) * 100
    frame["engagement_pct"] = pd.to_numeric(
        frame["engagement_rate"], errors="coerce"
    ).fillna(0).rank(pct=True) * 100

    def category_match(row: pd.Series) -> bool:
        return str(row.get("category_parent")) in category_set

    def tag_matches(row: pd.Series) -> list[str]:
        return [tag for tag in _tags(row.get("tags")) if tag in tag_set]

    frame["category_match"] = frame.apply(category_match, axis=1)
    frame["matched_tags"] = frame.apply(tag_matches, axis=1)
    frame["matched_tag_count"] = frame["matched_tags"].map(len)
    category_score = frame["category_match"].astype(float) * 100
    tag_score = frame["matched_tag_count"].clip(upper=2) / 2 * 100
    frame["affinity_score"] = (
        frame["heat_pct"] * 0.50
        + category_score * 0.25
        + tag_score * 0.15
        + frame["engagement_pct"] * 0.10
    ).round(1)

    def reasons(row: pd.Series) -> str:
        parts: list[str] = []
        if row["category_match"]:
            parts.append(f"命中偏好分区「{row['category_parent']}」")
        matched = row["matched_tags"]
        if matched:
            parts.append("匹配标签 " + "、".join(matched[:3]))
        parts.append(f"综合热度前 {max(1, round(100 - row['heat_pct']))}%")
        return "；".join(parts)

    frame["recommend_reason"] = frame.apply(reasons, axis=1)
    return (
        frame.sort_values(["affinity_score", "weighted_score"], ascending=[False, False])
        .head(top_n)
        .reset_index(drop=True)
    )


def build_summary(
    videos: pd.DataFrame,
    recommendations: pd.DataFrame,
    *,
    categories: Iterable[str] = (),
    tags: Iterable[str] = (),
) -> list[str]:
    """Generate a compact, data-backed personalised summary."""
    if videos.empty:
        return []
    category_set = {str(item) for item in categories if item}
    tag_set = {str(item) for item in tags if item}
    subset = videos[
        videos["category_parent"].astype(str).isin(category_set)
    ] if category_set else videos
    lines: list[str] = []
    if category_set:
        if subset.empty:
            lines.append("偏好分区在当前筛选条件下没有视频，请调整分区筛选或偏好。")
        else:
            lines.append(
                f"你的偏好分区覆盖 {len(subset)} 条视频（{len(subset) / len(videos) * 100:.1f}%），"
                f"其中位播放量 {int(pd.to_numeric(subset['views'], errors='coerce').median()):,}。"
            )
    if tag_set:
        matched = videos[
            videos["tags"].fillna("").astype(str).map(
                lambda value: bool(set(_tags(value)) & tag_set)
            )
        ]
        lines.append(
            f"在 {len(tag_set)} 个偏好标签中，样本里有 {len(matched)} 条视频至少命中 1 个。"
        )
    if not recommendations.empty:
        top = recommendations.iloc[0]
        lines.append(
            f"最匹配的是 {str(top['title'])[:40]}，"
            f"偏好得分 {top['affinity_score']:.1f}，"
            f"原因为：{top['recommend_reason']}。"
        )
        lines.append(
            "推荐列表按“加权热度 50% + 分区匹配 25% + 标签匹配 15% + 互动率 10%”排序。"
        )
    return lines


def save_profile(
    *,
    categories: list[str],
    tags: list[str],
    recommendations: pd.DataFrame,
    summary: list[str],
    path,
) -> None:
    """Persist the current personalised view for reproducibility."""
    payload = {
        "categories": categories,
        "tags": tags,
        "summary": summary,
        "recommendations": recommendations[
            [
                "bvid", "title", "category_path", "uploader", "video_url",
                "affinity_score", "recommend_reason",
            ]
        ].to_dict("records")
        if not recommendations.empty
        else [],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
