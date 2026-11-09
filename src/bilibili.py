"""Bilibili weekly must-watch API access with a guarded-endpoint fallback."""

from __future__ import annotations

import json
import random
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable, Iterable

import requests

from . import config


class BilibiliError(RuntimeError):
    """A Bilibili API response that could not be used."""


@dataclass
class Issue:
    number: int
    name: str
    subject: str
    status: int | None
    start_date: str | None
    end_date: str | None
    source: str = "web"

    @property
    def label(self) -> str:
        span = ""
        if self.start_date and self.end_date:
            span = f"{self.start_date[5:]} - {self.end_date[5:]}"
        title = self.subject or self.name
        return f"第{self.number}期 · {span} · {title}" if span else f"第{self.number}期 · {title}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "name": self.name,
            "subject": self.subject,
            "status": self.status,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "source": self.source,
        }


@dataclass
class IssuePayload:
    number: int
    source: str
    raw: dict[str, Any]
    config: dict[str, Any]
    videos: list[dict[str, Any]]


@dataclass
class VideoDetail:
    bvid: str
    source: str
    raw: dict[str, Any] | None
    view: dict[str, Any] | None
    tags: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class VideoFetchReport:
    bvid: str
    ok: bool
    source: str
    error: str | None = None


_DATE_RE = re.compile(
    r"(?P<year>\d{4})\s*第\s*(?P<number>\d+)\s*期\s+"
    r"(?P<sm>\d{2})\.(?P<sd>\d{2})\s*-\s*(?P<em>\d{2})\.(?P<ed>\d{2})"
)
_LOOSE_DATE_RE = re.compile(
    r"第\s*(?P<number>\d+)\s*期\s+"
    r"(?P<sm>\d{2})\.(?P<sd>\d{2})\s*-\s*(?P<em>\d{2})\.(?P<ed>\d{2})"
)


def parse_issue_dates(name: str) -> tuple[str | None, str | None]:
    """Parse the date span embedded in an issue name.

    Handles the year-boundary case where the end month is earlier than the
    start month. Returns ISO date strings, or ``(None, None)`` if unavailable.
    """
    match = _DATE_RE.search(name or "")
    year: int | None = int(match.group("year")) if match else None
    if match is None:
        match = _LOOSE_DATE_RE.search(name or "")
        if match is None:
            return None, None
        year = date.today().year
    if year is None:
        return None, None

    start_month, start_day = int(match.group("sm")), int(match.group("sd"))
    end_month, end_day = int(match.group("em")), int(match.group("ed"))
    try:
        start = date(year, start_month, start_day)
        end = date(year, end_month, end_day)
        if end < start:
            end = date(year + 1, end_month, end_day)
    except ValueError:
        return None, None
    return start.isoformat(), end.isoformat()


class BilibiliClient:
    """Small, retrying client for the two weekly-series endpoints.

    The documented web detail endpoint is often blocked with code ``-352``.
    When that happens the app endpoint is used and the per-video detail
    endpoint fills in category, stats, description and existing Bilibili tags.
    """

    def __init__(
        self,
        *,
        timeout: int = config.REQUEST_TIMEOUT,
        retries: int = config.REQUEST_RETRIES,
        delay: float = config.REQUEST_DELAY,
        logger: Callable[[str], None] | None = None,
    ) -> None:
        self.timeout = timeout
        self.retries = retries
        self.delay = delay
        self.log = logger or (lambda _message: None)
        self.session = requests.Session()
        self._web_one_blocked = False
        self.warnings: list[str] = []

    def _headers(self, *, app: bool = False) -> dict[str, str]:
        if app:
            return {"User-Agent": config.APP_UA, "Referer": config.BILI_REFERER}
        return {
            "User-Agent": config.BROWSER_UA,
            "Referer": config.BILI_REFERER,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

    def _get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        app: bool = False,
        attempts: int | None = None,
    ) -> dict[str, Any]:
        attempts = attempts or self.retries
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                response = self.session.get(
                    url,
                    params=params,
                    headers=self._headers(app=app),
                    timeout=self.timeout,
                )
                if response.status_code in {429, 500, 502, 503, 504}:
                    raise requests.HTTPError(f"HTTP {response.status_code}")
                response.raise_for_status()
                payload = json.loads(response.content.decode("utf-8"))
                if not isinstance(payload, dict):
                    raise BilibiliError("API returned a non-object payload")
                return payload
            except (requests.RequestException, ValueError, BilibiliError) as exc:
                last_error = exc
                if attempt < attempts:
                    backoff = min(0.8 * (2 ** (attempt - 1)), 6.0)
                    time.sleep(backoff + random.uniform(0, 0.5))
            finally:
                # Keep the request cadence below the documented soft ceiling.
                time.sleep(self.delay + random.uniform(0, 0.22))
        raise BilibiliError(f"请求失败：{last_error}") from last_error

    def fetch_series_list(self) -> tuple[str, dict[str, Any]]:
        """Fetch the issue index, preferring the documented web endpoint."""
        try:
            payload = self._get_json(config.WEB_SERIES_LIST_URL)
            if payload.get("code") == 0 and isinstance(payload.get("data"), dict):
                items = payload["data"].get("list") or []
                if items:
                    return "web", payload
            self.warnings.append(
                f"series/list 返回异常（code={payload.get('code')}），改用 app 索引。"
            )
        except Exception as exc:  # noqa: BLE001 - fallback is intentional
            self.warnings.append(f"series/list 请求失败：{exc}；改用 app 索引。")

        payload = self._get_json(config.APP_SERIES_LIST_URL, app=True)
        items = payload.get("data")
        if payload.get("code") == 0 and isinstance(items, list) and items:
            return "app", payload
        raise BilibiliError(
            f"无法获取每周必看期数列表（code={payload.get('code')}, "
            f"message={payload.get('message')}）"
        )

    @staticmethod
    def _parse_issue_items(source: str, payload: dict[str, Any]) -> list[Issue]:
        if source == "web":
            items = payload.get("data", {}).get("list") or []
        else:
            items = payload.get("data") or []
        issues: list[Issue] = []
        for item in items:
            try:
                number = int(item["number"])
            except (KeyError, TypeError, ValueError):
                continue
            name = str(item.get("name") or f"第{number}期")
            start, end = parse_issue_dates(name)
            issues.append(
                Issue(
                    number=number,
                    name=name,
                    subject=str(item.get("subject") or ""),
                    status=item.get("status"),
                    start_date=start,
                    end_date=end,
                    source=source,
                )
            )
        if not issues:
            raise BilibiliError("期数列表为空，无法选择要分析的周。")
        return sorted(issues, key=lambda item: item.number, reverse=True)

    def list_issues(self) -> tuple[list[Issue], str, dict[str, Any]]:
        source, payload = self.fetch_series_list()
        return self._parse_issue_items(source, payload), source, payload

    def fetch_issue(self, number: int) -> IssuePayload:
        """Fetch one issue. Web first, app fallback when risk control blocks it."""
        if not self._web_one_blocked:
            try:
                payload = self._get_json(
                    config.WEB_SERIES_ONE_URL, params={"number": int(number)}
                )
                if payload.get("code") == 0 and isinstance(payload.get("data"), dict):
                    data = payload["data"]
                    if data.get("list"):
                        return IssuePayload(
                            number=int(number),
                            source="web",
                            raw=payload,
                            config=data.get("config") or {},
                            videos=data.get("list") or [],
                        )
                if payload.get("code") == -352:
                    self._web_one_blocked = True
                    self.warnings.append(
                        "series/one 被 B 站风控拦截（-352），本次运行改用 app 详情接口。"
                    )
                else:
                    self.warnings.append(
                        f"series/one 第{number}期返回 code={payload.get('code')}，改用 app。"
                    )
            except Exception as exc:  # noqa: BLE001
                self.warnings.append(
                    f"series/one 第{number}期请求失败：{exc}；改用 app 详情。"
                )

        payload = self._get_json(
            config.APP_SERIES_ONE_URL,
            params={"type": "weekly_selected", "number": int(number)},
            app=True,
        )
        if payload.get("code") != 0 or not isinstance(payload.get("data"), dict):
            raise BilibiliError(
                f"第{number}期详情获取失败（code={payload.get('code')}, "
                f"message={payload.get('message')}）"
            )
        data = payload["data"]
        if not data.get("list"):
            raise BilibiliError(f"第{number}期没有视频数据。")
        return IssuePayload(
            number=int(number),
            source="app",
            raw=payload,
            config=data.get("config") or {},
            videos=data.get("list") or [],
        )

    def fetch_video_detail(self, bvid: str) -> VideoDetail:
        """Fetch category, stats and uploader tags for one video."""
        try:
            payload = self._get_json(
                config.VIEW_DETAIL_URL, params={"bvid": bvid}
            )
            if payload.get("code") == 0 and isinstance(payload.get("data"), dict):
                data = payload["data"]
                view = data.get("View") or data.get("view")
                tags = [
                    str(item.get("tag_name")).strip()
                    for item in (data.get("Tags") or [])
                    if isinstance(item, dict) and item.get("tag_name")
                ]
                if isinstance(view, dict):
                    return VideoDetail(
                        bvid=bvid,
                        source="view/detail",
                        raw=payload,
                        view=view,
                        tags=tags,
                    )
            error = f"code={payload.get('code')} message={payload.get('message')}"
        except Exception as exc:  # noqa: BLE001
            error = str(exc)

        # Minimal fallback: category/stats are still available without tags.
        try:
            payload = self._get_json(config.VIEW_URL, params={"bvid": bvid})
            if payload.get("code") == 0 and isinstance(payload.get("data"), dict):
                return VideoDetail(
                    bvid=bvid,
                    source="view",
                    raw=payload,
                    view=payload["data"],
                    tags=[],
                )
            error = f"{error}; view fallback code={payload.get('code')}"
        except Exception as exc:  # noqa: BLE001
            error = f"{error}; view fallback: {exc}"
        return VideoDetail(bvid=bvid, source="none", raw=None, view=None, error=error)

    @staticmethod
    def select_issues(
        issues: Iterable[Issue],
        mode: str,
        *,
        number: int | None = None,
        start: date | str | None = None,
        end: date | str | None = None,
    ) -> list[Issue]:
        """Resolve latest / one issue / overlapping date range."""
        ordered = sorted(issues, key=lambda item: item.number, reverse=True)
        if not ordered:
            return []
        if mode == "latest":
            return [ordered[0]]
        if mode == "issue":
            selected = [item for item in ordered if item.number == int(number or 0)]
            if not selected:
                raise BilibiliError(f"未找到第{number}期。")
            return selected
        if mode == "range":
            if not start or not end:
                raise BilibiliError("时间范围需要同时提供开始日期和结束日期。")
            start_s = start.isoformat() if isinstance(start, date) else str(start)
            end_s = end.isoformat() if isinstance(end, date) else str(end)
            if start_s > end_s:
                start_s, end_s = end_s, start_s
            selected = [
                item
                for item in ordered
                if item.start_date
                and item.end_date
                and item.start_date <= end_s
                and item.end_date >= start_s
            ]
            return sorted(selected, key=lambda item: item.number, reverse=True)
        raise ValueError(f"未知选期方式：{mode}")


def utc_now_iso() -> str:
    """Timestamp used in manifests and processed records."""
    return datetime.now().astimezone().isoformat(timespec="seconds")
