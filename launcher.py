"""Idempotent local launcher for the Streamlit app.

If the app is already listening, open it instead of starting a second process.
If the default port is occupied by something else, pick the next free port.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
DEFAULT_PORT = 8501
PORT_LIMIT = 8510


def health_ok(port: int) -> bool:
    try:
        with urllib.request.urlopen(
            f"http://{HOST}:{port}/_stcore/health", timeout=1.5
        ) as response:
            return response.status == 200 and response.read().strip() == b"ok"
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((HOST, port))
            return True
        except OSError:
            return False


def open_url(url: str) -> None:
    if os.environ.get("BILI_NO_BROWSER") != "1":
        webbrowser.open(url)


def open_existing(port: int) -> bool:
    if not health_ok(port):
        return False
    url = f"http://{HOST}:{port}"
    print(f"已有实例在运行：{url}")
    open_url(url)
    return True


def main() -> int:
    for port in range(DEFAULT_PORT, PORT_LIMIT + 1):
        if open_existing(port):
            return 0

    port = next(
        (candidate for candidate in range(DEFAULT_PORT, PORT_LIMIT + 1) if port_free(candidate)),
        None,
    )
    if port is None:
        print(f"{DEFAULT_PORT}-{PORT_LIMIT} 端口均被占用，请先关闭占用程序。")
        return 1

    url = f"http://{HOST}:{port}"
    print(f"正在启动 B站每周必看分析应用：{url}")
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(ROOT / "app.py"),
        "--server.address",
        HOST,
        "--server.port",
        str(port),
    ]
    process = subprocess.Popen(command, cwd=str(ROOT))
    ready = False
    for _ in range(90):
        if health_ok(port):
            ready = True
            break
        if process.poll() is not None:
            break
        time.sleep(0.5)
    if not ready:
        print("启动失败，请查看上方 Streamlit 输出。")
        if process.poll() is None:
            process.terminate()
        return 1
    print(f"启动完成：{url}")
    print("关闭此窗口会停止应用；下次双击启动脚本时会复用已运行实例。")
    open_url(url)
    try:
        return process.wait()
    except KeyboardInterrupt:
        process.terminate()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
