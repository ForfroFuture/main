"""Normalise raw Bilibili payloads into tidy analysis tables."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import pandas as pd

from . import config
from .bilibili import Issue, IssuePayload, VideoDetail, utc_now_iso
from .categories import category_for
from .tagger import TagResult

CN_TZ = ZoneInfo("Asia/Shanghai")

VIDEO_COLUMNS = [
    "issue_number",
    "issue_name",
    "issue_subject",
    "week_start",
    "week_end",
    "rank",
    "bvid",
    "aid",
    "title",
    "description",
    "category_parent",
    "category_name",
    "category_path",
    "category_tid",
    "category_tid_v2",
    "uploader",
    "uploader_mid",
    "duration_sec",
    "pubdate",
    "pubdate_iso",
    "views",
    "danmaku",
    "replies",
    "likes",
    "coins",
    "favorites",
    "shares",
    "engagement_rate",
    "rcmd_reason",
    "cover_url",
    "video_url",
    "bilibili_tags",
    "tags",
    "tag_count",
    "tag_source",
    "tag_model",
    "tag_latency_ms",
    "tag_attempts",
    "tag_error",
    "content_hash",
    "fetched_at",
    "appearance_count",
    "issue_numbers",
]


def _first(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _to_int(value: Any) -> int:
    if value is None or value == "":
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().replace(",", "")
    multiplier = 1
    if text.endswith("亿"):
        multiplier = 100_000_000
        text = text[:-1]
    elif text.endswith("万"):
        multiplier = 10_000
        text = text[:-1]
    try:
        return int(float(text) * multiplier)
    except ValueError:
        return 0


def _parse_card_views(text: str) -> int:
    match = re.search(r"([\d.]+)\s*([万亿]?)", text or "")
    if not match:
        return 0
    number = float(match.group(1))
    multiplier = 10_000 if match.group(2) == "万" else 100_000_000 if match.group(2) == "亿" else 1
    return int(number * multiplier)


def _parse_duration(value: Any) -> int:
    if value is None or value == "":
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    parts = str(value).strip().split(":")
    try:
        numbers = [int(float(part)) for part in parts]
    except ValueError:
        return 0
    if len(numbers) == 2:
        return numbers[0] * 60 + numbers[1]
    if len(numbers) == 3:
        return numbers[0] * 3600 + numbers[1] * 60 + numbers[2]
    return numbers[0] if numbers else 0


def _clean_text(value: Any, limit: int = 2000) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    if text in {"-", "—", "无"}:
        return ""
    return re.sub(r"\s{2,}", " ", text)[:limit]


def _iso_timestamp(value: Any) -> str:
    try:
        return datetime.fromtimestamp(int(value), tz=CN_TZ).isoformat(timespec="seconds")
    except (TypeError, ValueError, OSError):
        return ""


def _owner(card: dict[str, Any], view: dict[str, Any]) -> tuple[str, int]:
    owner = view.get("owner") or card.get("owner") or {}
    name = _first(owner.get("name") if isinstance(owner, dict) else None,
                  card.get("right_desc_1"),
                  card.get("author"))
    mid = _first(owner.get("mid") if isinstance(owner, dict) else None,
                 card.get("author_id"),
                 card.get("mid"))
    return _clean_text(name, 80), _to_int(mid)


def _stats(card: dict[str, Any], view: dict[str, Any]) -> dict[str, int]:
    stat = view.get("stat") or card.get("stat") or {}
    views = _to_int(stat.get("view")) or _parse_card_views(str(card.get("right_desc_2") or ""))
    return {
        "views": views,
        "danmaku": _to_int(stat.get("danmaku")),
        "replies": _to_int(stat.get("reply")),
        "likes": _to_int(stat.get("like")),
        "coins": _to_int(stat.get("coin")),
        "favorites": _to_int(stat.get("favorite")),
        "shares": _to_int(stat.get("share")),
    }


def _engagement_rate(stats: dict[str, int]) -> float:
    views = stats.get("views") or 0
    if not views:
        return 0.0
    interactions = (
        stats.get("likes", 0)
        + stats.get("coins", 0)
        + stats.get("favorites", 0)
        + stats.get("shares", 0)
    )
    return round(interactions / views, 6)


def normalise_issue(
    issue: Issue,
    payload: IssuePayload,
    *,
    video_count: int,
    fetched_at: str | None = None,
) -> dict[str, Any]:
    """Create the one-row-per-issue record."""
    raw_config = payload.config or {}
    return {
        "issue_number": issue.number,
        "issue_name": issue.name,
        "issue_subject": issue.subject,
        "week_start": issue.start_date or "",
        "week_end": issue.end_date or "",
        "video_count": int(video_count),
        "api_source": payload.source,
        "label": raw_config.get("label") or "",
        "share_title": raw_config.get("share_title") or "",
        "share_subtitle": raw_config.get("share_subtitle") or "",
        "fetched_at": fetched_at or utc_now_iso(),
    }


def normalise_video(
    *,
    issue: Issue,
    card: dict[str, Any],
    detail: VideoDetail | None,
    rank: int,
    tag_result: TagResult | None,
    fetched_at: str | None = None,
) -> dict[str, Any]:
    """Merge a weekly card, a per-video detail response and AI tags."""
    view = (detail.view if detail and detail.view else {}) or {}
    bvid = str(_first(view.get("bvid"), card.get("bvid"), "") or "")
    aid = _to_int(_first(view.get("aid"), card.get("aid"), card.get("param")))
    title = _clean_text(_first(view.get("title"), card.get("title")), 300)
    desc = _clean_text(_first(view.get("desc"), card.get("desc")), 2000)
    dynamic = _clean_text(view.get("dynamic"), 1000)
    if not desc and dynamic:
        desc = dynamic
    owner, owner_mid = _owner(card, view)
    stat = _stats(card, view)
    category = category_for(
        view.get("tid_v2") or card.get("tid_v2"),
        view.get("tid") or card.get("tid"),
        view.get("tname_v2") or card.get("tname_v2"),
        view.get("tname") or card.get("tname"),
    )
    bilibili_tags = list(detail.tags if detail else [])
    ai_tags = list(tag_result.tags if tag_result else [])
    duration = _to_int(_first(view.get("duration"), _parse_duration(card.get("cover_right_text_1"))))
    pubdate = _to_int(_first(view.get("pubdate"), card.get("pubdate")))
    fetched = fetched_at or utc_now_iso()
    return {
        "issue_number": issue.number,
        "issue_name": issue.name,
        "issue_subject": issue.subject,
        "week_start": issue.start_date or "",
        "week_end": issue.end_date or "",
        "rank": rank,
        "bvid": bvid,
        "aid": aid,
        "title": title,
        "description": desc,
        "category_parent": category["parent"],
        "category_name": category["name"],
        "category_path": category["path"],
        "category_tid": _to_int(_first(view.get("tid"), card.get("tid"))),
        "category_tid_v2": _to_int(_first(view.get("tid_v2"), card.get("tid_v2"))),
        "uploader": owner,
        "uploader_mid": owner_mid,
        "duration_sec": duration,
        "pubdate": pubdate,
        "pubdate_iso": _iso_timestamp(pubdate),
        "views": stat["views"],
        "danmaku": stat["danmaku"],
        "replies": stat["replies"],
        "likes": stat["likes"],
        "coins": stat["coins"],
        "favorites": stat["favorites"],
        "shares": stat["shares"],
        "engagement_rate": _engagement_rate(stat),
        "rcmd_reason": _clean_text(card.get("rcmd_reason") or view.get("rcmd_reason"), 300),
        "cover_url": str(_first(view.get("pic"), card.get("cover"), "") or "").replace(
            "http://", "https://"
        ),
        "video_url": f"https://www.bilibili.com/video/{bvid}" if bvid else "",
        "bilibili_tags": "|".join(bilibili_tags),
        "existing_tags": bilibili_tags,
        "tags": "|".join(ai_tags),
        "tag_count": len(ai_tags),
        "tag_source": tag_result.source if tag_result else "none",
        "tag_model": tag_result.model if tag_result else "",
        "tag_latency_ms": tag_result.latency_ms if tag_result else 0,
        "tag_attempts": tag_result.attempts if tag_result else 0,
        "tag_error": (tag_result.error if tag_result else None) or "",
        "content_hash": "",
        "fetched_at": fetched,
        "appearance_count": 1,
        "issue_numbers": str(issue.number),
    }


def build_frames(records: Iterable[dict[str, Any]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return unique videos and per-issue appearances."""
    rows = list(records)
    if not rows:
        raise ValueError("没有可清洗的视频记录。")
    appearances = pd.DataFrame(rows)
    for column in VIDEO_COLUMNS:
        if column not in appearances.columns:
            appearances[column] = ""
    appearances = appearances[VIDEO_COLUMNS].copy()
    appearances = appearances[appearances["bvid"].astype(str).str.len() > 0]
    appearances = appearances.drop_duplicates(subset=["issue_number", "bvid"], keep="first")
    appearances = appearances.sort_values(
        ["issue_number", "rank"], ascending=[False, True]
    ).reset_index(drop=True)

    grouped = (
        appearances.groupby("bvid", as_index=False)
        .agg(
            appearance_count=("issue_number", "size"),
            issue_numbers=("issue_number", lambda values: "|".join(str(v) for v in sorted(set(values), reverse=True))),
        )
    )
    latest = (
        appearances.sort_values(["issue_number", "rank"], ascending=[False, True])
        .drop_duplicates(subset=["bvid"], keep="first")
        .drop(columns=["appearance_count", "issue_numbers"])
    )
    videos = latest.merge(grouped, on="bvid", how="left")
    videos["appearance_count"] = videos["appearance_count"].fillna(1).astype(int)
    videos["issue_numbers"] = videos["issue_numbers"].fillna("")
    videos = videos[VIDEO_COLUMNS].sort_values(
        ["issue_number", "rank"], ascending=[False, True]
    ).reset_index(drop=True)
    return videos, appearances


def build_tags_frame(videos: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for record in videos.to_dict("records"):
        seen: set[str] = set()
        tags = [tag for tag in str(record.get("tags") or "").split("|") if tag]
        for index, tag in enumerate(tags, start=1):
            if tag in seen:
                continue
            seen.add(tag)
            rows.append(
                {
                    "issue_number": record.get("issue_number"),
                    "issue_name": record.get("issue_name"),
                    "bvid": record.get("bvid"),
                    "title": record.get("title"),
                    "category_parent": record.get("category_parent"),
                    "category_name": record.get("category_name"),
                    "tag": tag,
                    "rank_in_video": index,
                    "tag_source": record.get("tag_source"),
                    "tag_model": record.get("tag_model"),
                }
            )
    return pd.DataFrame(rows)


def build_issues_frame(
    issue_rows: Iterable[dict[str, Any]],
    issue_appearances: pd.DataFrame,
) -> pd.DataFrame:
    rows = list(issue_rows)
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    if not issue_appearances.empty:
        counts = (
            issue_appearances.groupby("issue_number", as_index=False)
            .agg(
                actual_video_count=("bvid", "nunique"),
                total_views=("views", "sum"),
                median_views=("views", "median"),
                top_category=("category_parent", lambda x: x.mode().iloc[0] if len(x.mode()) else ""),
            )
        )
        frame = frame.merge(counts, on="issue_number", how="left")
    frame = frame.sort_values("issue_number", ascending=False).reset_index(drop=True)
    return frame


def save_processed(
    videos: pd.DataFrame,
    appearances: pd.DataFrame,
    issues: pd.DataFrame,
    tags: pd.DataFrame,
    meta: dict[str, Any],
    processed_dir: Path | None = None,
) -> dict[str, str]:
    """Persist tidy CSVs and a JSON manifest; create the directory if needed."""
    target = Path(processed_dir or config.PROCESSED_DIR)
    os.makedirs(target, exist_ok=True)
    paths = {
        "videos": target / "videos.csv",
        "appearances": target / "appearances.csv",
        "issues": target / "issues.csv",
        "tags": target / "video_tags.csv",
        "meta": target / "dataset_meta.json",
    }
    videos.to_csv(paths["videos"], index=False, encoding="utf-8-sig")
    appearances.to_csv(paths["appearances"], index=False, encoding="utf-8-sig")
    issues.to_csv(paths["issues"], index=False, encoding="utf-8-sig")
    tags.to_csv(paths["tags"], index=False, encoding="utf-8-sig")
    paths["meta"].write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {key: str(value) for key, value in paths.items()}


def load_processed(processed_dir: Path | None = None) -> dict[str, Any] | None:
    """Load the tidy dataset, or return None when it has not been built."""
    target = Path(processed_dir or config.PROCESSED_DIR)
    meta_path = target / "dataset_meta.json"
    videos_path = target / "videos.csv"
    if not meta_path.exists() or not videos_path.exists():
        return None
    videos = pd.read_csv(videos_path, encoding="utf-8-sig", dtype={"bvid": str})
    appearances_path = target / "appearances.csv"
    issues_path = target / "issues.csv"
    tags_path = target / "video_tags.csv"
    appearances = (
        pd.read_csv(appearances_path, encoding="utf-8-sig", dtype={"bvid": str})
        if appearances_path.exists()
        else pd.DataFrame()
    )
    issues = (
        pd.read_csv(issues_path, encoding="utf-8-sig")
        if issues_path.exists()
        else pd.DataFrame()
    )
    tags = (
        pd.read_csv(tags_path, encoding="utf-8-sig")
        if tags_path.exists()
        else pd.DataFrame()
    )
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    return {
        "videos": videos,
        "appearances": appearances,
        "issues": issues,
        "tags": tags,
        "meta": meta,
    }
