"""Paths and runtime configuration for the weekly must-watch project."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(
    os.environ.get("BILI_PROJECT_ROOT", Path(__file__).resolve().parent.parent)
).resolve()
load_dotenv(PROJECT_ROOT / ".env")

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
OUTPUT_DIR = DATA_DIR / "output"
CACHE_DIR = DATA_DIR / "cache"
LOGS_DIR = PROJECT_ROOT / "logs"
DIST_DIR = PROJECT_ROOT / "dist"
ASSETS_DIR = PROJECT_ROOT / "assets"

RAW_ISSUES_DIR = RAW_DIR / "issues"
TAG_CACHE_DIR = CACHE_DIR / "tags"

# Bilibili "每周必看" endpoints. The web endpoint is the documented one; the
# app endpoint is a resilient fallback because the web detail endpoint is
# frequently guarded by Bilibili's risk control (-352).
WEB_SERIES_LIST_URL = "https://api.bilibili.com/x/web-interface/popular/series/list"
WEB_SERIES_ONE_URL = "https://api.bilibili.com/x/web-interface/popular/series/one"
APP_SERIES_LIST_URL = (
    "https://app.bilibili.com/x/v2/show/popular/selected/series?type=weekly_selected"
)
APP_SERIES_ONE_URL = "https://app.bilibili.com/x/v2/show/popular/selected"
VIEW_DETAIL_URL = "https://api.bilibili.com/x/web-interface/view/detail"
VIEW_URL = "https://api.bilibili.com/x/web-interface/view"

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
APP_UA = "Mozilla/5.0 BiliDroid/7.20.0 (bbcallen@gmail.com) os/android"
BILI_REFERER = "https://www.bilibili.com/"

REQUEST_TIMEOUT = int(os.environ.get("BILI_REQUEST_TIMEOUT", "40"))
REQUEST_RETRIES = int(os.environ.get("BILI_REQUEST_RETRIES", "4"))
# ~100 requests/minute is the documented soft ceiling; jitter keeps bursts down.
REQUEST_DELAY = float(os.environ.get("BILI_REQUEST_DELAY", "0.68"))
MAX_ISSUES_PER_RUN = int(os.environ.get("BILI_MAX_ISSUES", "8"))

TAG_MIN = 1
TAG_MAX = 999
TAG_PROMPT_VERSION = "2026-11-v3"
TAG_MAX_WORKERS = int(os.environ.get("BILI_TAG_WORKERS", "4"))
TAG_MAX_ATTEMPTS = 2

AI_BASE_URL = (
    os.environ.get("ANTHROPIC_BASE_URL", "").rstrip("/")
    or os.environ.get("BILI_AI_BASE_URL", "").rstrip("/")
)
AI_AUTH_TOKEN = os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get(
    "ANTHROPIC_API_KEY", ""
)
AI_MODEL = os.environ.get("BILI_AI_MODEL") or (
    "deepseek-chat" if "deepseek" in AI_BASE_URL.lower() else "claude-sonnet-5-5"
)
AI_AVAILABLE = bool(AI_BASE_URL and AI_AUTH_TOKEN)

DATA_DIRS = (
    DATA_DIR,
    RAW_DIR,
    RAW_ISSUES_DIR,
    PROCESSED_DIR,
    OUTPUT_DIR,
    CACHE_DIR,
    TAG_CACHE_DIR,
    LOGS_DIR,
    DIST_DIR,
)


def ensure_dirs() -> None:
    """Create every project data directory, tolerating repeated startup."""
    for directory in DATA_DIRS:
        os.makedirs(directory, exist_ok=True)


def path_label(path: Path) -> str:
    """Return a stable Windows path string for UI display."""
    return str(path)
