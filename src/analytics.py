"""Analysis tables, quality evaluation and headline findings."""

from __future__ import annotations

import math
from collections import Counter
from typing import Any, Iterable

import pandas as pd

from . import config

# User-defined Bilibili interaction weights for the default ranking.
RANK_WEIGHTS = {
    "views": 0.10,
    "likes": 0.30,
    "coins": 1.00,
    "favorites": 0.50,
    "replies": 0.75,
    "danmaku": 0.40,
    "shares": 1.50,
}
RANK_LABELS = {
    "weighted": "综合加权",
    "views": "播放",
    "likes": "点赞",
    "coins": "投币",
    "favorites": "收藏",
    "replies": "评论",
    "danmaku": "弹幕",
    "shares": "转发",
}


def add_weighted_score(videos: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with the weighted interaction score used by the ranking."""
    frame = videos.copy()
    score = pd.Series(0.0, index=frame.index)
    for column, weight in RANK_WEIGHTS.items():
        values = frame[column] if column in frame.columns else pd.Series(0.0, index=frame.index)
        score += pd.to_numeric(values, errors="coerce").fillna(0) * weight
    frame["weighted_score"] = score
    return frame


def ranking_table(videos: pd.DataFrame, metric: str = "weighted") -> pd.DataFrame:
    """Rank videos by the default weighted score or one selected metric."""
    frame = add_weighted_score(videos)
    if metric not in RANK_LABELS:
        metric = "weighted"
    value_column = "weighted_score" if metric == "weighted" else metric
    frame[value_column] = pd.to_numeric(frame[value_column], errors="coerce").fillna(0)
    frame = frame.sort_values(
        [value_column, "views"], ascending=[False, False]
    ).reset_index(drop=True)
    frame["rank"] = range(1, len(frame) + 1)
    frame["rank_metric"] = RANK_LABELS[metric]
    frame["rank_value"] = frame[value_column]
    return frame


def _tag_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return []
    return [item for item in str(value).split("|") if item.strip()]


def _mode_or_empty(values: Iterable[Any]) -> str:
    series = pd.Series([value for value in values if value not in (None, "")])
    if series.empty:
        return ""
    mode = series.mode()
    return str(mode.iloc[0]) if not mode.empty else ""


def tag_frequency(videos: pd.DataFrame) -> pd.DataFrame:
    """Frequency and performance per AI tag (one video counted once per tag)."""
    if videos.empty:
        return pd.DataFrame(
            columns=[
                "tag",
                "video_count",
                "share_pct",
                "total_views",
                "avg_views",
                "median_views",
                "avg_engagement_rate",
                "category_count",
                "top_category",
                "example_title",
                "example_bvid",
            ]
        )
    records: list[dict[str, Any]] = []
    total_videos = len(videos)
    for video in videos.to_dict("records"):
        for tag in _tag_list(video.get("tags")):
            records.append(
                {
                    "tag": tag,
                    "views": int(video.get("views") or 0),
                    "engagement_rate": float(video.get("engagement_rate") or 0),
                    "category_parent": video.get("category_parent") or "其他",
                    "title": video.get("title") or "",
                    "bvid": video.get("bvid") or "",
                }
            )
    if not records:
        return pd.DataFrame()
    exploded = pd.DataFrame(records)
    rows: list[dict[str, Any]] = []
    for tag, group in exploded.groupby("tag", sort=False):
        category_counts = group["category_parent"].value_counts()
        best = group.sort_values("views", ascending=False).iloc[0]
        rows.append(
            {
                "tag": tag,
                "video_count": int(len(group)),
                "share_pct": round(len(group) / total_videos * 100, 2),
                "total_views": int(group["views"].sum()),
                "avg_views": int(group["views"].mean()),
                "median_views": int(group["views"].median()),
                "avg_engagement_rate": round(float(group["engagement_rate"].mean()) * 100, 3),
                "category_count": int(group["category_parent"].nunique()),
                "top_category": str(category_counts.index[0]),
                "example_title": str(best["title"]),
                "example_bvid": str(best["bvid"]),
            }
        )
    return (
        pd.DataFrame(rows)
        .sort_values(["video_count", "total_views"], ascending=[False, False])
        .reset_index(drop=True)
    )


def category_stats(videos: pd.DataFrame, level: str = "parent") -> pd.DataFrame:
    """Aggregate video and engagement metrics by parent or subcategory."""
    column = "category_parent" if level == "parent" else "category_path"
    if videos.empty or column not in videos.columns:
        return pd.DataFrame()
    total_videos = len(videos)
    rows: list[dict[str, Any]] = []
    for name, group in videos.groupby(column, dropna=False):
        best = group.sort_values("views", ascending=False).iloc[0]
        tag_counter: Counter[str] = Counter()
        for value in group["tags"]:
            tag_counter.update(_tag_list(value))
        top_tag = tag_counter.most_common(1)[0][0] if tag_counter else ""
        rows.append(
            {
                "category": str(name or "其他"),
                "video_count": int(len(group)),
                "share_pct": round(len(group) / total_videos * 100, 2),
                "total_views": int(pd.to_numeric(group["views"], errors="coerce").fillna(0).sum()),
                "median_views": int(pd.to_numeric(group["views"], errors="coerce").fillna(0).median()),
                "avg_views": int(pd.to_numeric(group["views"], errors="coerce").fillna(0).mean()),
                "avg_engagement_rate": round(
                    float(pd.to_numeric(group["engagement_rate"], errors="coerce").fillna(0).mean()) * 100,
                    3,
                ),
                "top_tag": top_tag,
                "top_video": str(best.get("title") or ""),
                "top_video_bvid": str(best.get("bvid") or ""),
            }
        )
    return (
        pd.DataFrame(rows)
        .sort_values(["video_count", "total_views"], ascending=[False, False])
        .reset_index(drop=True)
    )


def issue_stats(issues: pd.DataFrame, appearances: pd.DataFrame) -> pd.DataFrame:
    """Weekly evolution, using the per-issue appearance table."""
    if appearances.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for number, group in appearances.groupby("issue_number", sort=False):
        issue_name = str(group["issue_name"].iloc[0])
        subject = str(group["issue_subject"].iloc[0]) if "issue_subject" in group else ""
        tag_counter: Counter[str] = Counter()
        for value in group["tags"]:
            tag_counter.update(_tag_list(value))
        rows.append(
            {
                "issue_number": int(number),
                "issue_name": issue_name,
                "issue_subject": subject,
                "week_start": str(group["week_start"].iloc[0]) if "week_start" in group else "",
                "week_end": str(group["week_end"].iloc[0]) if "week_end" in group else "",
                "video_count": int(group["bvid"].nunique()),
                "total_views": int(pd.to_numeric(group["views"], errors="coerce").fillna(0).sum()),
                "median_views": int(pd.to_numeric(group["views"], errors="coerce").fillna(0).median()),
                "avg_engagement_rate": round(
                    float(pd.to_numeric(group["engagement_rate"], errors="coerce").fillna(0).mean()) * 100,
                    3,
                ),
                "top_category": _mode_or_empty(group["category_parent"]),
                "top_tag": tag_counter.most_common(1)[0][0] if tag_counter else "",
            }
        )
    return pd.DataFrame(rows).sort_values("issue_number", ascending=True).reset_index(drop=True)


def build_quality_evaluation(
    videos: pd.DataFrame,
    appearances: pd.DataFrame,
    issues: pd.DataFrame,
    meta: dict[str, Any],
) -> dict[str, Any]:
    """Quantitative checks for tagging, coverage and data completeness."""
    if videos.empty:
        return {}
    tag_counts = pd.to_numeric(videos["tag_count"], errors="coerce").fillna(0).astype(int)
    total = len(videos)
    compliant = int((tag_counts >= 1).sum())
    all_tags: list[str] = []
    duplicate_videos = 0
    tag_chars: list[int] = []
    for value in videos["tags"]:
        tags = _tag_list(value)
        all_tags.extend(tags)
        if len(tags) != len(set(tags)):
            duplicate_videos += 1
        tag_chars.extend(len(tag) for tag in tags)
    counts = Counter(all_tags)
    total_assignments = len(all_tags)
    top10 = sum(count for _, count in counts.most_common(10))
    sources = videos["tag_source"].fillna("none").value_counts().to_dict()
    ai_count = int(sources.get("ai", 0))
    fallback_count = int(sources.get("fallback", 0))
    ai_latency = pd.to_numeric(
        videos.loc[videos["tag_source"] == "ai", "tag_latency_ms"], errors="coerce"
    ).dropna()
    known_category = int((videos["category_parent"] != "其他").sum())
    invalid_bvid = int((~videos["bvid"].astype(str).str.match(r"^BV[0-9A-Za-z]+$")).sum())
    tag_error = int((videos["tag_error"].fillna("").astype(str).str.len() > 0).sum())
    desc_empty = int((videos["description"].fillna("").astype(str).str.len() == 0).sum())
    fetch = meta.get("fetch_report") or {}
    video_ok = int(fetch.get("video_ok", 0))
    video_total = int(fetch.get("video_total", len(appearances)))
    issue_sources = (
        issues["api_source"].fillna("").value_counts().to_dict() if not issues.empty else {}
    )
    return {
        "generated_at": meta.get("generated_at"),
        "scope": {
            "issues": int(videos["issue_number"].nunique()),
            "unique_videos": total,
            "appearances": int(len(appearances)),
            "duplicate_appearances": int(len(appearances) - total),
        },
        "tagging": {
            "tag_assignments": total_assignments,
            "unique_tags": len(counts),
            "avg_tags_per_video": round(total_assignments / total, 2),
            "min_tags": int(tag_counts.min()),
            "max_tags": int(tag_counts.max()),
            "compliant_videos": compliant,
            "compliance_rate_pct": round(compliant / total * 100, 2),
            "tag_coverage_pct": round(compliant / total * 100, 2),
            "videos_with_all_range": compliant,
            "ai_tags": ai_count,
            "fallback_tags": fallback_count,
            "ai_success_rate_pct": round(ai_count / total * 100, 2) if total else 0,
            "duplicate_within_video_videos": duplicate_videos,
            "tag_error_videos": tag_error,
            "avg_tag_chars": round(sum(tag_chars) / len(tag_chars), 2) if tag_chars else 0,
            "vocabulary_ratio_pct": round(len(counts) / total_assignments * 100, 2)
            if total_assignments
            else 0,
            "top10_concentration_pct": round(top10 / total_assignments * 100, 2)
            if total_assignments
            else 0,
            "median_latency_ms": int(ai_latency.median()) if not ai_latency.empty else 0,
            "p95_latency_ms": int(ai_latency.quantile(0.95)) if not ai_latency.empty else 0,
            "source_counts": sources,
            "model": meta.get("tag_model"),
            "prompt_version": meta.get("tag_prompt_version"),
        },
        "coverage": {
            "known_category_videos": known_category,
            "known_category_pct": round(known_category / total * 100, 2),
            "unknown_category_videos": total - known_category,
            "description_empty_pct": round(desc_empty / total * 100, 2),
            "invalid_bvid": invalid_bvid,
            "video_detail_success_pct": round(video_ok / video_total * 100, 2)
            if video_total
            else 0,
            "issue_api_sources": issue_sources,
        },
        "performance": {
            "median_views": int(pd.to_numeric(videos["views"], errors="coerce").fillna(0).median()),
            "mean_views": int(pd.to_numeric(videos["views"], errors="coerce").fillna(0).mean()),
            "median_engagement_rate_pct": round(
                float(pd.to_numeric(videos["engagement_rate"], errors="coerce").fillna(0).median()) * 100,
                3,
            ),
            "total_views": int(pd.to_numeric(videos["views"], errors="coerce").fillna(0).sum()),
        },
        "api": fetch,
    }


def headline_findings(
    videos: pd.DataFrame,
    tag_freq: pd.DataFrame,
    parent_stats: pd.DataFrame,
) -> list[str]:
    """Short, human-readable findings shared by the app and report."""
    findings: list[str] = []
    if not parent_stats.empty:
        top = parent_stats.iloc[0]
        findings.append(
            f"{top['category']} 是最大分区，占 {top['share_pct']:.1f}%"
            f"（{int(top['video_count'])} 条视频）。"
        )
        eligible = parent_stats[parent_stats["video_count"] >= 3]
        if not eligible.empty:
            best = eligible.sort_values("avg_engagement_rate", ascending=False).iloc[0]
            findings.append(
                f"{best['category']} 的平均互动率最高，为 {best['avg_engagement_rate']:.2f}%。"
            )
    if not tag_freq.empty:
        top_tags = "、".join(tag_freq.head(5)["tag"].astype(str).tolist())
        findings.append(f"出现最多的标签：{top_tags}。")
        if len(tag_freq) > 0:
            first = tag_freq.iloc[0]
            findings.append(
                f"“{first['tag']}”覆盖 {int(first['video_count'])} 条视频"
                f"（{first['share_pct']:.1f}%）。"
            )
    if not videos.empty:
        findings.append(
            f"本期样本中位播放量 {int(pd.to_numeric(videos['views'], errors='coerce').median()):,}，"
            f"中位互动率 {float(pd.to_numeric(videos['engagement_rate'], errors='coerce').median()) * 100:.2f}%。"
        )
    return findings
