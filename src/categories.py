"""Category lookup built from Bilibili's v2 video-zone table."""

from __future__ import annotations

from typing import Any

from .category_map import CATEGORY_MAP

_FALLBACK = {
    "parent": "其他",
    "name": "未分类",
    "path": "其他/未分类",
    "slug": "other",
}


def _coerce_map() -> dict[int, dict[str, str]]:
    result: dict[int, dict[str, str]] = {}
    for key, value in CATEGORY_MAP.items():
        try:
            result[int(key)] = value
        except (TypeError, ValueError):
            continue
    return result


_CATEGORIES = _coerce_map()


def category_for(
    tid_v2: Any = None,
    tid: Any = None,
    tname_v2: str | None = None,
    tname: str | None = None,
) -> dict[str, str]:
    """Resolve the most specific category path available.

    New responses expose ``tid_v2``; older ones only have ``tid``. If no id is
    in the mapping, a non-empty tname is used rather than dropping the row.
    """
    for candidate in (tid_v2, tid):
        try:
            key = int(candidate)
        except (TypeError, ValueError):
            continue
        if key in _CATEGORIES:
            return dict(_CATEGORIES[key])

    label = (tname_v2 or tname or "").strip()
    if label:
        return {
            "parent": label,
            "name": label,
            "path": label,
            "slug": "unknown",
        }
    return dict(_FALLBACK)


def category_names() -> list[str]:
    """Return sorted top-level category names for filter controls."""
    return sorted({item["parent"] for item in _CATEGORIES.values()})
