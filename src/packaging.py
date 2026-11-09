"""Create a portable ZIP with the Streamlit app and analysis artifacts."""

from __future__ import annotations

import os
import zipfile
from datetime import datetime
from pathlib import Path

from . import config

INCLUDE_PATHS = [
    "app.py",
    "launcher.py",
    "requirements.txt",
    "README.md",
    "README-DEPLOY.md",
    "Dockerfile",
    ".dockerignore",
    "启动应用.bat",
    "停止应用.bat",
    ".env.example",
    ".streamlit",
    "src",
    "assets",
    "scripts",
    "data/processed",
    "data/output",
]
EXCLUDE_PARTS = {
    "__pycache__",
    ".pytest_cache",
    ".git",
    ".venv",
    "raw",
    "cache",
    "dist",
    "logs",
    ".env",
}


def _should_include(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    if any(part in EXCLUDE_PARTS for part in relative.parts):
        return False
    if path.suffix in {".pyc", ".pyo", ".tmp"}:
        return False
    if path.name.startswith("~$"):
        return False
    return True


def build_app_package(
    *,
    project_root: Path | None = None,
    dist_dir: Path | None = None,
) -> str:
    """Bundle source, dependencies and existing outputs into one ZIP."""
    root = Path(project_root or config.PROJECT_ROOT)
    target = Path(dist_dir or config.DIST_DIR)
    os.makedirs(target, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    archive_path = target / f"bilibili_weekly_analytics_{stamp}.zip"
    manifest = [
        "B站每周必看 · 交互式分析应用",
        f"打包时间：{datetime.now().astimezone().isoformat(timespec='seconds')}",
        "",
        "运行：解压后双击 启动应用.bat，或执行 python -m streamlit run app.py",
        "首次运行：python -m pip install -r requirements.txt",
        "AI 凭据：设置 ANTHROPIC_BASE_URL / ANTHROPIC_AUTH_TOKEN（或 ANTHROPIC_API_KEY）；",
        "已包含 data/processed 与 data/output，可离线查看本次分析结果。",
    ]
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("MANIFEST.txt", "\n".join(manifest))
        for include in INCLUDE_PATHS:
            source = root / include
            if not source.exists():
                continue
            if source.is_file():
                archive.write(source, source.relative_to(root).as_posix())
                continue
            for path in source.rglob("*"):
                if path.is_file() and _should_include(path, root):
                    archive.write(path, path.relative_to(root).as_posix())
        for directory in ("data/raw/issues", "data/cache/tags", "logs"):
            archive.writestr(directory.rstrip("/") + "/", "")
    return str(archive_path)
