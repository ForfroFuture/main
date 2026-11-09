"""UP-focused monthly attendance analysis for weekly must-watch videos."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterable

import pandas as pd

from . import config
from .bilibili import BilibiliClient, Issue, utc_now_iso
from .preprocess import CN_TZ


def _clean_name(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _card_uploader(card: dict[str, Any]) -> str:
    owner = card.get("owner")
    if isinstance(owner, dict) and owner.get("name"):
        return _clean_name(owner.get("name"))
    return _clean_name(
        card.get("right_desc_1")
        or card.get("author")
        or card.get("uploader")
        or ""
    )


def _payload_videos(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    videos = data.get("list")
    return videos if isinstance(videos, list) else []


def _read_cached_issue(number: int) -> dict[str, Any] | None:
    path = config.RAW_ISSUES_DIR / str(number) / "series_one.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if _payload_videos(payload) else None


def _save_issue(number: int, payload: dict[str, Any], source: str) -> None:
    directory = config.RAW_ISSUES_DIR / str(number)
    os.makedirs(directory, exist_ok=True)
    (directory / "series_one.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (directory / "series_one.meta.json").write_text(
        json.dumps(
            {
                "issue_number": number,
                "source": source,
                "fetched_at": utc_now_iso(),
                "purpose": "up-trend",
                "video_cards": len(_payload_videos(payload)),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def upcoming_months(start: date, end: date) -> list[str]:
    periods = pd.period_range(start=start, end=end, freq="M")
    return [str(period) for period in periods]


def month_for_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10]).strftime("%Y-%m")
    except ValueError:
        return None


@dataclass
class UpTrendResult:
    up_name: str
    start: date
    end: date
    months: pd.DataFrame
    appearances: pd.DataFrame
    issues_scanned: int
    issues_failed: list[dict[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    generated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "up_name": self.up_name,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "months": self.months.to_dict("records"),
            "appearances": self.appearances.to_dict("records"),
            "issues_scanned": self.issues_scanned,
            "issues_failed": self.issues_failed,
            "warnings": self.warnings,
            "generated_at": self.generated_at,
        }


def build_up_trend(
    client: BilibiliClient,
    issues: Iterable[Issue],
    up_name: str,
    start: date,
    end: date,
    *,
    max_issues: int = 60,
    use_cache: bool = True,
    progress: Callable[[int, int, str], None] | None = None,
) -> UpTrendResult:
    """Fetch/cached weekly issue cards and count one UP's monthly appearances."""
    up_name = _clean_name(up_name)
    if start > end:
        start, end = end, start
    selected = [
        issue
        for issue in issues
        if issue.start_date
        and issue.end_date
        and issue.start_date <= end.isoformat()
        and issue.end_date >= start.isoformat()
    ]
    selected = sorted(selected, key=lambda issue: issue.number)
    warnings: list[str] = []
    if len(selected) > max_issues:
        warnings.append(
            f"时间范围包含 {len(selected)} 期，按最近 {max_issues} 期统计。"
        )
        selected = selected[-max_issues:]

    appearance_rows: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    if progress:
        progress(0, len(selected), "准备读取每周必看期数…")

    for index, issue in enumerate(selected, start=1):
        payload = _read_cached_issue(issue.number) if use_cache else None
        if payload is None:
            try:
                fetched = client.fetch_issue(issue.number)
                payload = fetched.raw
                _save_issue(issue.number, payload, fetched.source)
            except Exception as exc:  # noqa: BLE001
                failures.append({"issue": str(issue.number), "error": str(exc)})
                if progress:
                    progress(index, len(selected), f"第{issue.number}期读取失败，已跳过")
                continue
        for rank, card in enumerate(_payload_videos(payload), start=1):
            if _card_uploader(card) != up_name:
                continue
            bvid = str(card.get("bvid") or "").strip()
            appearance_rows.append(
                {
                    "issue_number": issue.number,
                    "week_start": issue.start_date,
                    "week_end": issue.end_date,
                    "month": month_for_date(issue.end_date) or "",
                    "rank": rank,
                    "bvid": bvid,
                    "title": str(card.get("title") or ""),
                    "video_url": f"https://www.bilibili.com/video/{bvid}" if bvid else "",
                    "cover_url": str(card.get("cover") or "").replace("http://", "https://"),
                    "rcmd_reason": str(card.get("rcmd_reason") or ""),
                }
            )
        if progress:
            progress(
                index,
                len(selected),
                f"已扫描第{issue.number}期 · 命中 {len(appearance_rows)} 条",
            )

    appearances = pd.DataFrame(appearance_rows)
    month_keys = upcoming_months(start, end)
    counts = (
        appearances["month"].value_counts().to_dict()
        if not appearances.empty
        else {}
    )
    months = pd.DataFrame(
        {
            "month": month_keys,
            "count": [int(counts.get(month, 0)) for month in month_keys],
        }
    )
    result = UpTrendResult(
        up_name=up_name,
        start=start,
        end=end,
        months=months,
        appearances=appearances,
        issues_scanned=len(selected) - len(failures),
        issues_failed=failures,
        warnings=warnings,
    )
    _save_result(result)
    return result


def _save_result(result: UpTrendResult) -> None:
    safe = re.sub(r'[<>:"/\\|?*]+', "_", result.up_name)[:60] or "up"
    directory = config.PROCESSED_DIR / "up_trends"
    os.makedirs(directory, exist_ok=True)
    result.months.to_csv(directory / f"{safe}_months.csv", index=False, encoding="utf-8-sig")
    if not result.appearances.empty:
        result.appearances.to_csv(
            directory / f"{safe}_appearances.csv", index=False, encoding="utf-8-sig"
        )
    (directory / f"{safe}.json").write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_up_trend(up_name: str) -> UpTrendResult | None:
    """Load a previously saved UP trend without refetching history."""
    safe = re.sub(r'[<>:"/\\|?*]+', "_", _clean_name(up_name))[:60] or "up"
    path = config.PROCESSED_DIR / "up_trends" / f"{safe}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    months = pd.DataFrame(data.get("months") or [])
    appearances = pd.DataFrame(data.get("appearances") or [])
    try:
        start = date.fromisoformat(data["start"])
        end = date.fromisoformat(data["end"])
    except (KeyError, ValueError):
        return None
    return UpTrendResult(
        up_name=str(data.get("up_name") or up_name),
        start=start,
        end=end,
        months=months,
        appearances=appearances,
        issues_scanned=int(data.get("issues_scanned") or 0),
        issues_failed=list(data.get("issues_failed") or []),
        warnings=list(data.get("warnings") or []),
        generated_at=str(data.get("generated_at") or ""),
    )
