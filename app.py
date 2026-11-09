from __future__ import annotations

import hmac
import html
import json
import math
import os
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

st.set_page_config(
    page_title="B站每周必看 · 内容洞察",
    page_icon="📺",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Streamlit Community Cloud exposes secrets through st.secrets, not os.environ.
# Copy the keys this app understands before importing config.
try:
    for _secret_key in (
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_API_KEY",
        "BILI_AI_MODEL",
        "APP_USER",
        "APP_PASSWORD",
        "DEMO_MODE",
    ):
        if _secret_key in st.secrets:
            os.environ[_secret_key] = str(st.secrets[_secret_key])
except Exception:
    pass

from src import analytics, chat, config, deepseek_chat, insights, personalization, preprocess, up_analysis, visuals  # noqa: E402
from src.bilibili import BilibiliClient, Issue  # noqa: E402
from src.pipeline import run_analysis  # noqa: E402

APP_USER = os.environ.get("APP_USER", "judge")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
DEMO_MODE = os.environ.get("DEMO_MODE", "").strip().lower() in {"1", "true", "yes", "on"}

if APP_PASSWORD and not st.session_state.get("app_authed"):
    st.markdown("## B站每周必看 · 内容洞察")
    st.caption("赛事评审体验入口")
    with st.form("access_form"):
        _user = st.text_input("账号")
        _password = st.text_input("密码", type="password")
        _submit = st.form_submit_button("进入")
    if _submit:
        if hmac.compare_digest(_user, APP_USER) and hmac.compare_digest(_password, APP_PASSWORD):
            st.session_state["app_authed"] = True
            st.rerun()
        st.error("账号或密码不正确。")
    st.stop()

st.session_state.setdefault("dark_mode", False)
st.session_state.setdefault("view_mode", "内容总览")

DARK = bool(st.session_state.get("dark_mode", False))
C = {
    "page": "#0d0d0d" if DARK else "#f7f7f5",
    "surface": "#1a1a19" if DARK else "#ffffff",
    "chart_surface": "#1a1a19" if DARK else "#fcfcfb",
    "ink": "#f0efec" if DARK else "#0b0b0b",
    "secondary": "#c3c2b7" if DARK else "#52514e",
    "muted": "#898781",
    "grid": "#2c2c2a" if DARK else "#e1e0d9",
    "axis": "#383835" if DARK else "#c3c2b7",
    "blue": "#3987e5" if DARK else "#2a78d6",
}
PINK = "#fb7299"
INK = C["ink"]
SECONDARY = C["secondary"]
MUTED = C["muted"]
GRID = C["grid"]
AXIS = C["axis"]
SURFACE = C["chart_surface"]
PAGE = C["page"]
BLUE = C["blue"]

THEME_CSS = """
<style>
html, body, .stApp { background: __PAGE__ !important; color: __INK__ !important; }
.block-container { max-width: 1480px; padding-top: 1.2rem; padding-bottom: 3rem; }
[data-testid="stSidebar"] { background: __SURFACE__ !important; border-right: 1px solid __GRID__; }
[data-testid="stSidebar"] * { color: __INK__; }
h1, h2, h3, h4 { color: __INK__ !important; letter-spacing: -0.02em; }
h1 { font-size: 2.35rem !important; margin-bottom: .1rem !important; }
p, label, .stMarkdown, [data-testid="stWidgetLabel"] { color: __INK__; }
[data-testid="stCaptionContainer"], .stCaption, small { color: __MUTED__ !important; }
a { color: __BLUE__; }
.hero-eyebrow { color: __PINK__; font-size: .74rem; font-weight: 700; letter-spacing: .14em;
  text-transform: uppercase; margin-bottom: .35rem; }
.hero-sub { color: __SECONDARY__; font-size: 1rem; margin-bottom: 1.3rem; }
.kpi { background: __SURFACE__; border: 1px solid __GRID__; border-radius: 12px; padding: 14px 16px 13px;
  min-height: 104px; }
.kpi-label { color: __SECONDARY__; font-size: .75rem; margin-bottom: 7px; }
.kpi-value { color: __INK__; font-size: 1.72rem; font-weight: 650; line-height: 1.1;
  font-variant-numeric: proportional-nums; }
.kpi-sub { color: __MUTED__; font-size: .7rem; margin-top: 7px; }
.insight { background: __SURFACE__; border-left: 3px solid __PINK__; border-radius: 6px;
  padding: 12px 16px; color: __SECONDARY__; font-size: .9rem; margin-bottom: 8px; }
.issue-single { background:__SURFACE__; border:1px solid __GRID__; border-radius:12px;
  padding:20px 22px; min-height:250px; display:flex; flex-direction:column; justify-content:center; }
.issue-single .label { color:__SECONDARY__; font-size:.82rem; }
.issue-single .big { color:__INK__; font-size:3rem; font-weight:750; line-height:1.05; margin:8px 0 2px; }
.issue-single .sub { color:__MUTED__; font-size:.8rem; }
.empty-card { background: __SURFACE__; border: 1px solid __GRID__; border-radius: 14px;
  padding: 26px 28px; margin-top: 14px; }
.empty-step { color: __SECONDARY__; font-size: .92rem; margin: 6px 0; }
.empty-step b { color: __INK__; }
.source-chip { display: inline-block; background: #fff0f5; color: #c9184a; border-radius: 999px;
  padding: 2px 9px; font-size: .68rem; font-weight: 600; }
.rank-card { display:flex; align-items:center; gap:14px; background:__SURFACE__; border:1px solid __GRID__;
  border-radius:11px; padding:12px 15px; margin-bottom:8px; }
.rank-num { color:__PINK__; font-size:1.05rem; font-weight:750; width:34px; flex:0 0 34px;
  font-variant-numeric:tabular-nums; }
.rank-main { min-width:0; flex:1; }
.rank-title { color:__INK__; font-weight:650; text-decoration:none; }
.rank-title:hover { text-decoration:underline; }
.rank-meta { color:__MUTED__; font-size:.73rem; margin-top:4px; overflow:hidden; text-overflow:ellipsis;
  white-space:nowrap; }
.rank-score { text-align:right; flex:0 0 96px; }
.rank-score b { color:__INK__; font-size:1.02rem; font-variant-numeric:tabular-nums; }
.rank-score span { color:__MUTED__; font-size:.67rem; display:block; margin-top:2px; }
.pref-note { color:__MUTED__; font-size:.78rem; margin:4px 0 12px; }
div[data-testid="stExpander"] { background: __SURFACE__; border: 1px solid __GRID__; border-radius: 10px; }
.stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: 1px solid __GRID__; }
.stTabs [data-baseweb="tab"] { padding: 8px 16px; color: __SECONDARY__; }
.stTabs [aria-selected="true"] { color: __INK__ !important; font-weight: 650; }
.stButton > button[kind="primary"] { background: __PINK__; border-color: __PINK__; color: #fff; }
.stButton > button[kind="primary"]:hover { background: #e85d86; border-color: #e85d86; }
div[data-baseweb="select"] > div, div[data-baseweb="select"] [role="button"],
div[data-baseweb="input"] > div, .stTextInput input, .stNumberInput input, .stDateInput input,
.stMultiSelect [data-baseweb="select"] > div {
  background-color: __SURFACE__ !important; color: __INK__ !important; border-color: __GRID__ !important;
}
[data-testid="stSelectbox"] div:has(> input[role="combobox"]),
[data-testid="stMultiSelect"] div:has(> input[role="combobox"]),
[data-testid="stDateInput"] div:has(> input),
[data-testid="stNumberInput"] div:has(> input) {
  background-color: __SURFACE__ !important; color: __INK__ !important; border-color: __GRID__ !important;
}
[data-testid="stSelectbox"] input, [data-testid="stMultiSelect"] input,
[data-testid="stDateInput"] input, [data-testid="stNumberInput"] input {
  color: __INK__ !important; background: transparent !important;
}
[data-testid="stDateInput"] div { background-color: __SURFACE__ !important; color: __INK__ !important; }
[data-testid="stDateInput"] svg { fill: __INK__ !important; color: __INK__ !important; }
input::placeholder { color: __MUTED__ !important; opacity: 1 !important; }
div[data-baseweb="select"] *, div[data-baseweb="select"] svg { color: __INK__ !important; fill: __INK__ !important; }
[data-baseweb="popover"], [data-baseweb="menu"], div[role="listbox"] { background: __SURFACE__ !important; }
[role="option"] { color: __INK__ !important; background: __SURFACE__ !important; }
[data-testid="stDataFrame"] { background: __SURFACE__ !important; border: 1px solid __GRID__; border-radius: 8px; }
[data-testid="stAlert"] { background: __SURFACE__ !important; color: __INK__ !important; }
pre, code, .stCode { background: __SURFACE__ !important; color: __INK__ !important; }
[data-testid="stSidebar"] pre, [data-testid="stSidebar"] code { background: __SURFACE__ !important; }
</style>
"""

st.markdown(
    THEME_CSS.replace("__PAGE__", PAGE)
    .replace("__SURFACE__", SURFACE)
    .replace("__INK__", INK)
    .replace("__SECONDARY__", SECONDARY)
    .replace("__MUTED__", MUTED)
    .replace("__GRID__", GRID)
    .replace("__BLUE__", BLUE)
    .replace("__PINK__", PINK),
    unsafe_allow_html=True,
)
if DARK:
    st.markdown(
        "<style>[data-testid=\"stDataFrame\"] { filter: invert(0.92) hue-rotate(180deg) !important; }</style>",
        unsafe_allow_html=True,
    )


@st.cache_data(ttl=300, show_spinner=False)
def load_issue_index() -> tuple[list[dict[str, Any]], str, list[str]]:
    client = BilibiliClient()
    issues, source, _ = client.list_issues()
    return [issue.to_dict() | {"label": issue.label} for issue in issues], source, client.warnings


def compact(value: float | int) -> str:
    number = float(value or 0)
    if number >= 100_000_000:
        return f"{number / 100_000_000:.2f}亿"
    if number >= 10_000:
        return f"{number / 10_000:.1f}万"
    return f"{int(number):,}"


def kpi(label: str, value: str, sub: str = "") -> None:
    st.markdown(
        '<div class="kpi">'
        f'<div class="kpi-label">{html.escape(label)}</div>'
        f'<div class="kpi-value">{html.escape(value)}</div>'
        f'<div class="kpi-sub">{html.escape(sub)}</div>'
        "</div>",
        unsafe_allow_html=True,
    )


def chart_layout(fig: go.Figure, *, height: int = 360) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=6, r=18, t=10, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(
            family='system-ui, -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif',
            color=SECONDARY,
            size=12,
        ),
        hoverlabel=dict(
            bgcolor=SURFACE,
            bordercolor=GRID,
            font=dict(color=INK, size=12, family='system-ui, "Microsoft YaHei", sans-serif'),
        ),
        showlegend=False,
    )
    fig.update_xaxes(
        showgrid=True, gridcolor=GRID, gridwidth=1, zeroline=False,
        linecolor=AXIS, tickfont=dict(color=MUTED), title_font=dict(color=SECONDARY),
    )
    fig.update_yaxes(
        showgrid=False, zeroline=False, linecolor=AXIS,
        tickfont=dict(color=MUTED), title_font=dict(color=SECONDARY),
    )
    return fig


def horizontal_bar(
    frame: pd.DataFrame,
    *,
    label_col: str,
    value_col: str,
    height: int = 360,
    top_n: int = 12,
    value_suffix: str = "条",
) -> go.Figure:
    data = frame.head(top_n).iloc[::-1].copy()
    values = data[value_col].astype(float).tolist()
    labels = data[label_col].astype(str).tolist()
    labels_text = [
        f"{int(value):,}{value_suffix}" if index >= len(values) - 3 else ""
        for index, value in enumerate(values)
    ]
    fig = go.Figure(
        go.Bar(
            x=values, y=labels, orientation="h", width=0.58,
            marker=dict(color=BLUE, cornerradius=4),
            text=labels_text, textposition="outside",
            textfont=dict(color=INK, size=11), cliponaxis=False,
            hovertemplate="%{y}<br>%{x:,} " + value_suffix + "<extra></extra>",
        )
    )
    maximum = max(values) if values else 1
    fig.update_xaxes(range=[0, maximum * 1.18])
    return chart_layout(fig, height=height)


def issue_bars(frame: pd.DataFrame, height: int = 330) -> go.Figure:
    data = frame.sort_values("issue_number")
    labels = [f"第{int(number)}期" for number in data["issue_number"]]
    values = data["video_count"].astype(int).tolist()
    fig = go.Figure(
        go.Bar(
            x=values, y=labels, orientation="h", width=0.52,
            marker=dict(color=BLUE, cornerradius=4),
            text=[str(value) for value in values], textposition="outside",
            textfont=dict(color=INK, size=11), cliponaxis=False,
            hovertemplate="%{y}<br>%{x} 条视频<extra></extra>",
        )
    )
    maximum = max(values) if values else 1
    fig.update_xaxes(range=[0, maximum * 1.2])
    fig.update_yaxes(showgrid=False)
    fig = chart_layout(fig, height=height)
    fig.update_layout(margin=dict(l=6, r=42, t=10, b=8))
    return fig


def up_trend_figure(months: pd.DataFrame, height: int = 330) -> go.Figure:
    data = months.copy()
    x = data["month"].astype(str).tolist()
    y = data["count"].astype(int).tolist()
    labels = [str(value) if value else "" for value in y]
    fig = go.Figure(
        go.Scatter(
            x=x, y=y, mode="lines+markers+text", text=labels,
            textposition="top center", textfont=dict(color=INK, size=11),
            line=dict(color=BLUE, width=2),
            marker=dict(color=BLUE, size=9, line=dict(color=SURFACE, width=2)),
            fill="tozeroy", fillcolor="rgba(42,120,214,0.10)",
            hovertemplate="%{x}<br>%{y} 条上榜视频<extra></extra>",
        )
    )
    fig.update_yaxes(rangemode="tozero", dtick=1 if max(y or [0]) <= 8 else None)
    fig.update_xaxes(type="category")
    fig = chart_layout(fig, height=height)
    fig.update_layout(margin=dict(l=6, r=30, t=24, b=8))
    fig.update_traces(cliponaxis=False)
    return fig


def scatter_engagement(frame: pd.DataFrame, height: int = 390) -> go.Figure | None:
    data = frame.copy()
    data["views"] = pd.to_numeric(data["views"], errors="coerce").fillna(0)
    data["engagement_pct"] = pd.to_numeric(data["engagement_rate"], errors="coerce").fillna(0) * 100
    data = data[(data["views"] > 0) & (data["engagement_pct"] >= 0)]
    if data.empty:
        return None
    views = data["views"].astype(float)
    xmin = max(1.0, float(views.min()) * 0.75)
    xmax = max(xmin * 2, float(views.max()) * 1.25)
    ticks = [10**power for power in range(3, 9) if xmin <= 10**power <= xmax]
    tick_text = {
        1e3: "1千",
        1e4: "1万",
        1e5: "10万",
        1e6: "100万",
        1e7: "1000万",
        1e8: "1亿",
    }
    ymax = max(40, int(max(40, data["engagement_pct"].quantile(0.99) * 1.15 + 4)))
    fig = go.Figure(
        go.Scatter(
            x=views,
            y=data["engagement_pct"],
            mode="markers",
            marker=dict(size=9, color=BLUE, opacity=0.72, line=dict(color=SURFACE, width=2)),
            customdata=data[["title", "category_path", "bvid", "video_url"]].fillna("").values,
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>%{customdata[1]}<br>"
                "播放 %{x:,.0f}<br>互动率 %{y:.2f}%<extra></extra>"
            ),
        )
    )
    fig.update_xaxes(
        type="log", title="播放量（对数轴）", showgrid=True,
        range=[math.log10(xmin), math.log10(xmax)],
        tickmode="array", tickvals=ticks,
        ticktext=[tick_text.get(value, f"{value:g}") for value in ticks],
    )
    fig.update_yaxes(
        title="互动率（%）", showgrid=True, rangemode="tozero",
        range=[0, ymax], tickmode="array",
        tickvals=list(range(0, ymax + 1, 10)),
    )
    return chart_layout(fig, height=height)


def tag_heatmap(frame: pd.DataFrame, parent_stats: pd.DataFrame, height: int = 420) -> go.Figure | None:
    if frame.empty:
        return None
    records: list[dict[str, Any]] = []
    for row in frame.to_dict("records"):
        for tag in str(row.get("tags") or "").split("|"):
            if tag:
                records.append({"tag": tag, "category": row.get("category_parent") or "其他"})
    if not records:
        return None
    exploded = pd.DataFrame(records)
    top_tags = exploded["tag"].value_counts().head(10).index.tolist()
    top_categories = parent_stats.head(6)["category"].astype(str).tolist()
    matrix = (
        exploded[exploded["tag"].isin(top_tags) & exploded["category"].isin(top_categories)]
        .groupby(["tag", "category"]).size().unstack(fill_value=0)
        .reindex(index=top_tags, columns=top_categories, fill_value=0)
    )
    colorscale = (
        [[0.0, "#12263f"], [0.3, "#1c5cab"], [0.6, "#3987e5"], [0.85, "#86b6ef"], [1.0, "#cde2fb"]]
        if DARK
        else [[0.0, "#f4f8fe"], [0.25, "#cde2fb"], [0.5, "#86b6ef"], [0.75, "#3987e5"], [1.0, "#184f95"]]
    )
    fig = go.Figure(
        go.Heatmap(
            z=matrix.values, x=matrix.columns.tolist(), y=matrix.index.tolist(),
            colorscale=colorscale, showscale=True,
            colorbar=dict(thickness=8, len=0.72, outlinewidth=0, tickfont=dict(color=MUTED, size=10)),
            hovertemplate="%{y} × %{x}<br>%{z} 条视频<extra></extra>",
            xgap=2, ygap=2,
        )
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=False, autorange="reversed")
    return chart_layout(fig, height=height)


def issue_matches(issues: list[dict[str, Any]], start: date, end: date) -> list[dict[str, Any]]:
    start_s, end_s = start.isoformat(), end.isoformat()
    return [
        item for item in issues
        if item.get("start_date") and item.get("end_date")
        and item["start_date"] <= end_s and item["end_date"] >= start_s
    ]


def issue_objects(issue_dicts: list[dict[str, Any]]) -> list[Issue]:
    return [
        Issue(
            number=int(item["number"]),
            name=str(item.get("name") or ""),
            subject=str(item.get("subject") or ""),
            status=item.get("status"),
            start_date=item.get("start_date"),
            end_date=item.get("end_date"),
            source=str(item.get("source") or "web"),
        )
        for item in issue_dicts
    ]


def _date_bounds(issues: list[dict[str, Any]]) -> tuple[date, date]:
    starts = [item["start_date"] for item in issues if item.get("start_date")]
    ends = [item["end_date"] for item in issues if item.get("end_date")]
    if starts and ends:
        return date.fromisoformat(min(starts)), date.fromisoformat(max(ends))
    return date.today() - timedelta(days=30), date.today()


def run_from_sidebar(
    *, mode: str, issue_number: int | None, start: date | None, end: date | None,
    use_ai: bool, force_retag: bool, workers: int, model: str, api_key: str, base_url: str,
) -> None:
    status = st.status("正在准备分析…", expanded=True)
    progress = st.progress(0)
    message = st.empty()

    def callback(event: dict[str, Any]) -> None:
        stage = event.get("stage")
        message.caption(str(event.get("message") or ""))
        if stage == "video":
            total = max(1, int(event.get("total") or 1))
            progress.progress(min(0.48, 0.08 + 0.40 * int(event.get("current") or 0) / total))
        elif stage == "tagging":
            total = max(1, int(event.get("total") or 1))
            progress.progress(min(0.90, 0.52 + 0.36 * int(event.get("current") or 0) / total))
        elif stage == "exporting":
            progress.progress(0.94)
        elif stage == "done":
            progress.progress(1.0)

    try:
        result = run_analysis(
            mode=mode, issue_number=issue_number, start=start, end=end,
            use_ai=use_ai, force_retag=force_retag, max_workers=workers,
            model=model or None, ai_base_url=base_url or None, ai_token=api_key or None,
            progress=callback,
        )
        status.update(label="分析完成", state="complete", expanded=False)
        st.session_state["flash"] = (
            f"已完成 {result['evaluation'].get('scope', {}).get('unique_videos', 0)} 条视频的分析，"
            "结果已写入 data/output。"
        )
        st.cache_data.clear()
        st.rerun()
    except Exception as exc:  # noqa: BLE001
        status.update(label="分析失败", state="error", expanded=True)
        st.error(str(exc))
        st.exception(exc)


def run_up_from_sidebar(
    *, up_name: str, start: date, end: date, issue_dicts: list[dict[str, Any]]
) -> None:
    if not issue_dicts:
        st.error("期数列表不可用，无法分析历史上榜。")
        return
    status = st.status("正在读取历史期数…", expanded=True)
    progress = st.progress(0)
    message = st.empty()

    def callback(current: int, total: int, text: str) -> None:
        message.caption(text)
        progress.progress(min(1.0, current / max(1, total)))

    try:
        client = BilibiliClient()
        result = up_analysis.build_up_trend(
            client, issue_objects(issue_dicts), up_name, start, end,
            progress=callback,
        )
        status.update(label="UP 主分析完成", state="complete", expanded=False)
        st.session_state["up_result"] = result
        st.session_state["flash_up"] = f"已统计 {result.up_name} 在所选区间的每周必看上榜记录。"
        st.rerun()
    except Exception as exc:  # noqa: BLE001
        status.update(label="UP 主分析失败", state="error", expanded=True)
        st.error(str(exc))
        st.exception(exc)


def video_url(row: Any) -> str:
    bvid = str(row.get("bvid") or "")
    return f"https://www.bilibili.com/video/{bvid}" if bvid else ""


def render_rank_cards(frame: pd.DataFrame, *, metric_label: str, top_n: int = 10) -> None:
    if frame.empty:
        st.info("当前筛选下没有视频。")
        return
    cards: list[str] = []
    for _, row in frame.head(top_n).iterrows():
        url = html.escape(str(row.get("video_url") or video_url(row)), quote=True)
        title = html.escape(str(row.get("title") or "未命名视频"))
        meta = " · ".join(
            html.escape(str(row.get(key) or ""))
            for key in ("category_path", "uploader")
            if row.get(key)
        )
        tags = " / ".join(str(row.get("tags") or "").split("|")[:3])
        score = compact(float(row.get("rank_value") or 0))
        cards.append(
            f'<div class="rank-card"><div class="rank-num">{int(row["rank"]):02d}</div>'
            f'<div class="rank-main"><a class="rank-title" href="{url}" target="_blank" rel="noopener">{title}</a>'
            f'<div class="rank-meta">{meta}</div>'
            f'<div class="rank-meta">{html.escape(tags)}</div></div>'
            f'<div class="rank-score"><b>{score}</b><span>{html.escape(metric_label)}</span></div></div>'
        )
    st.markdown("".join(cards), unsafe_allow_html=True)


def render_personal_cards(frame: pd.DataFrame, top_n: int = 8) -> None:
    if frame.empty:
        st.info("没有匹配的推荐视频。")
        return
    cards: list[str] = []
    for index, (_, row) in enumerate(frame.head(top_n).iterrows(), start=1):
        url = html.escape(str(row.get("video_url") or video_url(row)), quote=True)
        title = html.escape(str(row.get("title") or "未命名视频"))
        cards.append(
            f'<div class="rank-card"><div class="rank-num">{index:02d}</div>'
            f'<div class="rank-main"><a class="rank-title" href="{url}" target="_blank" rel="noopener">{title}</a>'
            f'<div class="rank-meta">{html.escape(str(row.get("category_path") or ""))} · '
            f'{html.escape(str(row.get("uploader") or ""))}</div>'
            f'<div class="rank-meta">{html.escape(str(row.get("recommend_reason") or ""))}</div></div>'
            f'<div class="rank-score"><b>{float(row.get("affinity_score") or 0):.1f}</b>'
            f'<span>偏好得分</span></div></div>'
        )
    st.markdown("".join(cards), unsafe_allow_html=True)


def render_up_result(result: up_analysis.UpTrendResult) -> None:
    st.markdown('<div class="hero-eyebrow">UP TRACKER</div>', unsafe_allow_html=True)
    st.title(f"{result.up_name} · 每周必看轨迹")
    st.markdown(
        f'<div class="hero-sub">仅统计上过每周必看的 UP 主 · {result.start.isoformat()} 至 {result.end.isoformat()} · '
        f'扫描 {result.issues_scanned} 期</div>',
        unsafe_allow_html=True,
    )
    if "flash_up" in st.session_state:
        st.success(st.session_state.pop("flash_up"))
    if result.appearances.empty:
        st.info("这个时间范围内没有找到该 UP 主的上榜视频。可以扩大时间范围后再试。")
    cols = st.columns(4, gap="small")
    with cols[0]:
        kpi("上榜视频", f"{len(result.appearances):,}", result.up_name)
    with cols[1]:
        active = int((result.months["count"] > 0).sum()) if not result.months.empty else 0
        kpi("活跃月份", f"{active}", "有上榜记录的月份")
    with cols[2]:
        best = int(result.months["count"].max()) if not result.months.empty else 0
        kpi("单月最高", f"{best}", "上榜视频数")
    with cols[3]:
        kpi("扫描期数", f"{result.issues_scanned}", "历史接口命中")
    st.write("")
    st.markdown("#### 每月的每周必看上榜数量")
    if not result.months.empty:
        st.plotly_chart(
            up_trend_figure(result.months),
            width="stretch", config={"displayModeBar": False},
        )
        with st.expander("查看月度数据表"):
            st.dataframe(result.months, width="stretch", hide_index=True)
    if not result.appearances.empty:
        st.markdown("#### 上榜视频")
        table = result.appearances.copy()
        display = table[["issue_number", "week_end", "rank", "title", "rcmd_reason", "video_url"]].copy()
        st.dataframe(
            display, width="stretch", hide_index=True,
            column_config={
                "issue_number": st.column_config.NumberColumn("期数", format="%d"),
                "week_end": st.column_config.TextColumn("周结束"),
                "rank": st.column_config.NumberColumn("当期序号", format="%d"),
                "title": st.column_config.TextColumn("标题", width="large"),
                "rcmd_reason": st.column_config.TextColumn("推荐语"),
                "video_url": st.column_config.LinkColumn("链接", display_text="打开视频"),
            },
        )
    if result.warnings or result.issues_failed:
        with st.expander("运行提示"):
            for warning in result.warnings:
                st.caption(f"• {warning}")
            for failure in result.issues_failed[:10]:
                st.caption(f"• 第{failure.get('issue')}期读取失败：{failure.get('error')}")
    st.caption("UP 主候选仅来自已抓取到的每周必看视频；历史月份按每周的结束日期归档。")


CHAT_HISTORY_PATH = config.PROCESSED_DIR / "chat_history.json"


def load_chat_sessions() -> list[dict[str, Any]]:
    if not CHAT_HISTORY_PATH.exists():
        return []
    try:
        payload = json.loads(CHAT_HISTORY_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    sessions = payload.get("sessions") if isinstance(payload, dict) else payload
    return sessions if isinstance(sessions, list) else []


def save_chat_sessions(sessions: list[dict[str, Any]]) -> None:
    CHAT_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHAT_HISTORY_PATH.write_text(
        json.dumps({"sessions": sessions[-30:]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def render_chat_panel(videos: pd.DataFrame) -> None:
    """Right-side conversation panel plus the bottom-fixed chat input."""
    st.divider()
    st.markdown("### 数据问答")
    left, right = st.columns([0.72, 1.45], gap="large")
    sessions = st.session_state.get("chat_sessions", [])
    active_id = st.session_state.get("active_chat_id")
    active = next((item for item in sessions if item.get("id") == active_id), None)
    with left:
        st.caption("对话记录显示在右侧；左侧栏可切换历史对话。")
        st.markdown("**可以这样问**")
        st.write("· 查询一下鬼畜区的情况")
        st.write("· 鬼畜和游戏哪个更火")
        st.write("· 知识科普相关视频")
        st.write("· 本周最火 / 播放最高")
        st.write("· 影视飓风最近怎么样")
        use_deepseek = st.toggle(
            "DeepSeek 综合",
            value=bool(config.AI_AVAILABLE),
            disabled=not config.AI_AVAILABLE,
            help="DeepSeek 官网搜索没有公开接口；开启后会在本地分析基础上调用 DeepSeek API 做长文综合分析，余额不足时自动回退本地。",
        )
        if use_deepseek and not config.AI_AVAILABLE:
            st.caption("未配置 DeepSeek API，使用本地分析。")
        else:
            st.caption("关闭时使用本地数据引擎；开启后需要 API 余额。")
    with right:
        with st.container(height=430, border=True):
            flash = st.session_state.pop("chat_flash", None)
            if flash:
                st.caption(flash)
            if active is None or not active.get("messages"):
                st.caption("还没有对话。直接在下方输入框提问即可。")
            else:
                for message in active.get("messages", []):
                    role = message.get("role", "assistant")
                    content = str(message.get("content") or "")
                    with st.chat_message(role):
                        if role == "user":
                            st.write(content)
                        else:
                            st.markdown(content)
    prompt = st.chat_input("输入查询，例如：鬼畜区的情况")
    if not prompt:
        return
    sessions = st.session_state.setdefault("chat_sessions", [])
    active_id = st.session_state.get("active_chat_id")
    active = next((item for item in sessions if item.get("id") == active_id), None)
    history = active.get("messages", []) if active else []
    answer = (
        chat.answer_query(prompt, videos, history=history)
        if not videos.empty
        else "还没有分析数据，先在左侧完成一次拉取，我再来分析。"
    )
    if use_deepseek and not videos.empty:
        try:
            answer = deepseek_chat.enhance_answer(
                prompt, answer, history=history
            )
        except Exception as exc:  # noqa: BLE001
            st.session_state["chat_flash"] = (
                f"DeepSeek 综合暂不可用，已回退本地分析：{exc}"
            )
    if active is None:
        active = {
            "id": f"chat-{time.time_ns()}",
            "title": prompt.strip()[:24] or "新对话",
            "created_at": time.strftime("%Y-%m-%d %H:%M"),
            "messages": [],
        }
        sessions.append(active)
        st.session_state["active_chat_id"] = active["id"]
    active["messages"].append(
        {"role": "user", "content": prompt, "time": time.strftime("%H:%M")}
    )
    active["messages"].append(
        {"role": "assistant", "content": answer, "time": time.strftime("%H:%M")}
    )
    save_chat_sessions(sessions)
    st.rerun()


# ---------------------------------------------------------------------------
# Data / navigation
# ---------------------------------------------------------------------------
dataset = preprocess.load_processed()
if "chat_sessions" not in st.session_state:
    st.session_state["chat_sessions"] = load_chat_sessions()
if "active_chat_id" not in st.session_state:
    st.session_state["active_chat_id"] = None
all_ups_by_name: dict[str, int] = {}
if dataset is not None and not dataset["videos"].empty:
    all_ups_by_name = (
        dataset["videos"]["uploader"].fillna("").astype(str).replace("", pd.NA)
        .dropna().value_counts().to_dict()
    )

index_error: str | None = None
try:
    issues, index_source, index_warnings = load_issue_index()
except Exception as exc:  # noqa: BLE001
    issues, index_source, index_warnings = [], "unavailable", []
    index_error = str(exc)
if not issues and dataset is not None and not dataset["issues"].empty:
    issues = [
        {
            "number": int(row.issue_number),
            "name": str(getattr(row, "issue_name", "") or f"第{int(row.issue_number)}期"),
            "subject": str(getattr(row, "issue_subject", "") or ""),
            "status": None,
            "start_date": str(getattr(row, "week_start", "") or ""),
            "end_date": str(getattr(row, "week_end", "") or ""),
            "source": "local",
            "label": f"第{int(row.issue_number)}期",
        }
        for row in dataset["issues"].itertuples(index=False)
    ]
    index_source = "local"

run_clicked = False
mode = "latest"
selected_issue: int | None = None
start_date: date | None = None
end_date: date | None = None
matched: list[dict[str, Any]] = []
use_ai, force_retag, workers, model, api_key, base_url = True, False, 4, config.AI_MODEL, "", ""
ranking_metric = "weighted"
up_run_clicked = False
selected_up: str | None = None
up_start: date | None = None
up_end: date | None = None

with st.sidebar:
    st.markdown("### 每周必看 · 控制台")
    st.caption("数据源：Bilibili 公开接口")
    st.toggle("夜间模式", key="dark_mode")
    st.radio("分析视图", ["内容总览", "UP主追踪"], key="view_mode", horizontal=True)
    view_mode = st.session_state.get("view_mode", "内容总览")
    if DEMO_MODE:
        st.caption("演示模式：使用预置数据，不触发重新拉取。")
    if index_error:
        st.warning(f"期数列表暂不可用：{index_error}")
    elif index_source == "app":
        st.caption("web 列表异常，当前使用 app 索引")

    if view_mode == "内容总览":
        st.markdown("#### 选择范围")
        mode_label = st.radio(
            "选期方式", ["最新一期", "指定期数", "时间范围"],
            label_visibility="collapsed", disabled=not issues,
        )
        mode = {"最新一期": "latest", "指定期数": "issue", "时间范围": "range"}[mode_label]
        if issues:
            latest = issues[0]
            if mode == "latest":
                st.markdown(f"**{latest['label']}**  \n<span class='source-chip'>WEEKLY</span>", unsafe_allow_html=True)
            elif mode == "issue":
                selected_issue = st.selectbox(
                    "期数", [item["number"] for item in issues],
                    format_func=lambda number: next(item["label"] for item in issues if item["number"] == number),
                )
            else:
                min_date, max_date = _date_bounds(issues)
                default_end = date.fromisoformat(latest.get("end_date") or max_date.isoformat())
                default_start = max(min_date, default_end - timedelta(days=20))
                picked = st.date_input("时间范围", value=(default_start, default_end), min_value=min_date, max_value=max_date)
                if isinstance(picked, tuple) and len(picked) == 2:
                    start_date, end_date = picked
                elif isinstance(picked, date):
                    start_date = end_date = picked
                if start_date and end_date:
                    matched = issue_matches(issues, start_date, end_date)
                    st.caption(f"匹配 **{len(matched)}** 期，上限 {config.MAX_ISSUES_PER_RUN} 期")
                    if matched:
                        with st.expander("查看匹配期数"):
                            for item in matched[:12]:
                                st.write(f"第{item['number']}期 · {item.get('subject', '')}")
                    if len(matched) > config.MAX_ISSUES_PER_RUN:
                        st.warning("选中期数超过单次上限，请缩小时间范围。")
        ranking_metric = st.selectbox(
            "榜单排序", list(analytics.RANK_LABELS.keys()),
            format_func=lambda key: analytics.RANK_LABELS[key],
            help="默认按播放/点赞/投币/收藏/评论/弹幕/转发加权；也可按单项查看。",
        )
        with st.expander("AI 打标设置", expanded=False):
            use_ai = st.checkbox("启用 AI 标签", value=True, help="关闭后使用规则回退标签")
            model = st.text_input("模型", value=config.AI_MODEL)
            api_key = st.text_input("API Key（留空使用环境变量）", type="password", value="")
            base_url = st.text_input("API Base URL（可选）", value="")
            workers = st.slider("并发数", 1, 8, config.TAG_MAX_WORKERS)
            force_retag = st.checkbox("忽略标签缓存，重新打标", value=False)
            if not config.AI_AVAILABLE and not api_key:
                st.warning("未检测到环境变量凭据；未填写 API Key 时将使用规则回退标签。")
        if issues:
            run_clicked = st.button(
                "开始拉取并分析", type="primary", width="stretch",
                disabled=DEMO_MODE
                or (mode == "range" and not matched)
                or (mode == "range" and len(matched) > config.MAX_ISSUES_PER_RUN),
            )
    else:
        st.markdown("#### UP 主追踪")
        up_options = sorted(all_ups_by_name, key=lambda name: (-all_ups_by_name[name], name))
        if up_options:
            default_up_index = up_options.index("影视飓风") if "影视飓风" in up_options else 0
            selected_up = st.selectbox(
                "选择 UP 主", up_options, index=default_up_index,
                format_func=lambda name: f"{name} · {all_ups_by_name.get(name, 0)} 条",
                help="只列出已出现在当前每周必看数据中的 UP 主。",
            )
            current_result = st.session_state.get("up_result")
            if selected_up and (
                current_result is None or getattr(current_result, "up_name", None) != selected_up
            ):
                cached_result = up_analysis.load_up_trend(selected_up)
                if cached_result is not None:
                    st.session_state["up_result"] = cached_result
            min_date, max_date = _date_bounds(issues) if issues else (date.today() - timedelta(days=365), date.today())
            default_end = min(max_date, date.fromisoformat(issues[0]["end_date"])) if issues and issues[0].get("end_date") else max_date
            default_start = max(min_date, default_end - timedelta(days=365))
            picked = st.date_input("统计时间范围", value=(default_start, default_end), min_value=min_date, max_value=max_date)
            if isinstance(picked, tuple) and len(picked) == 2:
                up_start, up_end = picked
            elif isinstance(picked, date):
                up_start = up_end = picked
            if up_start and up_end:
                count = len(issue_matches(issues, up_start, up_end))
                st.caption(f"匹配 {count} 期 · 单次最多扫描 60 期")
            up_run_clicked = st.button(
                "分析该 UP 主", type="primary", width="stretch", disabled=DEMO_MODE
            )
            st.caption("折线图按月份统计该 UP 主在每周必看中的上榜视频数。")
        else:
            st.info("当前数据里还没有 UP 主；请先完成一次内容分析。")

    st.divider()
    st.caption("数据目录")
    st.code(str(config.DATA_DIR), language=None)
    st.caption("原始 JSON → processed CSV → output 报告")
    if index_warnings:
        with st.expander("接口提示"):
            for warning in index_warnings:
                st.caption(warning)

    st.divider()
    st.markdown("#### 对话记录")
    if st.button("＋ 新对话", width="stretch", key="new_chat"):
        st.session_state["active_chat_id"] = None
        st.rerun()
    chat_sessions = st.session_state.get("chat_sessions", [])
    if not chat_sessions:
        st.caption("还没有对话")
    else:
        for session in reversed(chat_sessions[-10:]):
            title = str(session.get("title") or "未命名对话")[:22]
            if st.button(title, width="stretch", key=f"open_chat_{session['id']}"):
                st.session_state["active_chat_id"] = session["id"]
                st.rerun()


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown('<div class="hero-eyebrow">BILIBILI WEEKLY INSIGHT</div>', unsafe_allow_html=True)

if view_mode == "UP主追踪":
    if up_run_clicked and selected_up and up_start and up_end:
        run_up_from_sidebar(
            up_name=selected_up, start=up_start, end=up_end, issue_dicts=issues
        )
    result = st.session_state.get("up_result")
    if result is None or (selected_up and result.up_name != selected_up):
        st.title("UP主上榜追踪")
        st.markdown(
            '<div class="hero-sub">选择一位上过每周必看的 UP 主，查看其按月累计的上榜数量与视频链接。</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="empty-card"><div class="empty-step"><b>1.</b> 在左侧选择 UP 主与时间范围（默认最近 12 个月）。</div>'
            '<div class="empty-step"><b>2.</b> 点击“分析该 UP 主”，应用会读取历史每周必看期数并统计。</div>'
            '<div class="empty-step"><b>3.</b> 首次读取历史期数约需 1 分钟，之后会复用本地缓存。</div></div>',
            unsafe_allow_html=True,
        )
    else:
        render_up_result(result)
    render_chat_panel(dataset["videos"] if dataset is not None else pd.DataFrame())
    st.stop()

if "flash" in st.session_state:
    st.success(st.session_state.pop("flash"))

st.title("B站每周必看 · 内容洞察")
st.markdown(
    '<div class="hero-sub">把每周必看拆成可比较的内容结构：分区、播放表现、加权榜单与 AI 标签。</div>',
    unsafe_allow_html=True,
)

if run_clicked:
    run_from_sidebar(
        mode=mode, issue_number=selected_issue, start=start_date, end=end_date,
        use_ai=use_ai, force_retag=force_retag, workers=workers,
        model=model, api_key=api_key, base_url=base_url,
    )

if dataset is None:
    st.markdown(
        """
        <div class="empty-card">
          <div style="font-size:1.1rem;font-weight:650;margin-bottom:10px;">还没有分析数据</div>
          <div class="empty-step"><b>1.</b> 在左侧选择最新一期、指定期数或时间范围。</div>
          <div class="empty-step"><b>2.</b> 点击“开始拉取并分析”，应用会拉取 B 站数据并为每条视频生成内容标签（数量不设上限）。</div>
          <div class="empty-step"><b>3.</b> 完成后自动进入分区分析、交互词云和加权榜单。</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()

videos = dataset["videos"]
appearances = dataset["appearances"]
issues_df = dataset["issues"]
meta = dataset["meta"]
if videos.empty:
    st.warning("processed 数据为空，请重新运行分析。")
    st.stop()

all_categories = sorted(videos["category_parent"].dropna().astype(str).unique().tolist())
max_views = int(pd.to_numeric(videos["views"], errors="coerce").fillna(0).max())
filter_cols = st.columns([2.2, 1.1, 1.3])
with filter_cols[0]:
    chosen_categories = st.multiselect("分区筛选（作用于全部图表）", all_categories, default=[])
with filter_cols[1]:
    min_views = st.number_input("最低播放量", min_value=0, max_value=max(1, max_views), value=0, step=100_000, format="%d")
with filter_cols[2]:
    st.caption("当前数据")
    st.markdown(f"<span class='source-chip'>{html.escape(meta.get('selection_label', '')[:44])}</span>", unsafe_allow_html=True)

filtered = videos.copy()
if chosen_categories:
    filtered = filtered[filtered["category_parent"].isin(chosen_categories)]
filtered = filtered[pd.to_numeric(filtered["views"], errors="coerce").fillna(0) >= min_views]
filtered_appearances = appearances.copy()
if chosen_categories:
    filtered_appearances = filtered_appearances[filtered_appearances["category_parent"].isin(chosen_categories)]
filtered_appearances = filtered_appearances[pd.to_numeric(filtered_appearances["views"], errors="coerce").fillna(0) >= min_views]
if filtered.empty:
    st.info("当前筛选条件下没有视频，请放宽分区或播放量条件。")
    st.stop()

tag_freq = analytics.tag_frequency(filtered)
parent_stats = analytics.category_stats(filtered, level="parent")
sub_stats = analytics.category_stats(filtered, level="path")
issue_perf = analytics.issue_stats(issues_df, filtered_appearances)
evaluation = analytics.build_quality_evaluation(filtered, filtered_appearances, issues_df, meta)
findings = analytics.headline_findings(filtered, tag_freq, parent_stats)
tagging = evaluation.get("tagging", {})
scope = evaluation.get("scope", {})
coverage = evaluation.get("coverage", {})
performance = evaluation.get("performance", {})
ranking = analytics.ranking_table(filtered, metric=ranking_metric)
pie_items = visuals.build_pie_items(parent_stats, top_n=7, dark=DARK)
globe_data = visuals.build_globe_data(filtered)

issue_numbers = sorted(filtered["issue_number"].dropna().astype(int).unique().tolist())
issue_span = (
    f"第{issue_numbers[0]}–{issue_numbers[-1]}期" if len(issue_numbers) > 1
    else f"第{issue_numbers[0]}期" if issue_numbers else ""
)
kpi_cols = st.columns(5, gap="small")
with kpi_cols[0]:
    kpi("去重视频", f"{len(filtered):,}", f"{len(filtered_appearances):,} 条上榜记录")
with kpi_cols[1]:
    kpi("覆盖期数", f"{filtered['issue_number'].nunique():,}", issue_span)
with kpi_cols[2]:
    kpi("唯一标签", f"{tagging.get('unique_tags', 0):,}", f"平均 {tagging.get('avg_tags_per_video', 0):.1f} 个/视频")
with kpi_cols[3]:
    kpi("中位播放", compact(performance.get("median_views", 0)), "每条视频")
with kpi_cols[4]:
    kpi("AI 标签覆盖", f"{tagging.get('ai_success_rate_pct', 0):.1f}%", f"平均 {tagging.get('avg_tags_per_video', 0):.1f} 个/视频 · 不设上限")
st.write("")

tabs = st.tabs(["总览", "分区分析", "词云", "榜单", "个性化", "视频明细", "数据质量"])

with tabs[0]:
    left, right = st.columns([1.05, 1], gap="large")
    with left:
        st.markdown("#### 每期收录视频数")
        if len(issue_perf) == 1:
            row = issue_perf.iloc[0]
            st.markdown(
                f'<div class="issue-single"><div class="label">第{int(row["issue_number"])}期 · '
                f'{html.escape(str(row.get("week_start", "")))} 至 {html.escape(str(row.get("week_end", "")))}</div>'
                f'<div class="big">{int(row["video_count"])}</div>'
                f'<div class="sub">条视频 · {html.escape(str(row.get("issue_subject", "")))}</div></div>',
                unsafe_allow_html=True,
            )
        else:
            st.plotly_chart(issue_bars(issue_perf), width="stretch", config={"displayModeBar": False})
        with st.expander("查看期数数据表"):
            st.dataframe(
                issue_perf[["issue_number", "issue_subject", "video_count", "median_views", "top_category", "top_tag"]],
                width="stretch", hide_index=True,
            )
    with right:
        st.iframe(visuals.pie_chart_html(pie_items, dark=DARK), height=470)
        with st.expander("查看分区数据表"):
            display = parent_stats.copy()
            display["top_video_url"] = display["top_video_bvid"].map(lambda bvid: video_url({"bvid": bvid}))
            st.dataframe(
                display[["category", "video_count", "share_pct", "median_views", "avg_engagement_rate", "top_tag", "top_video", "top_video_url"]],
                width="stretch", hide_index=True,
                column_config={
                    "median_views": st.column_config.NumberColumn("中位播放", format="localized"),
                    "avg_engagement_rate": st.column_config.NumberColumn("互动率", format="%.2f%%"),
                    "top_video_url": st.column_config.LinkColumn("示例视频", display_text="打开"),
                },
            )
    st.markdown("#### 核心发现")
    for finding in findings:
        st.markdown(f'<div class="insight">{html.escape(finding)}</div>', unsafe_allow_html=True)

with tabs[1]:
    st.markdown("#### 分区结构与表现")
    col1, col2 = st.columns([1.05, 1], gap="large")
    with col1:
        st.iframe(visuals.pie_chart_html(pie_items, dark=DARK), height=470)
    with col2:
        st.caption("子分区 · 视频数")
        sub_display = sub_stats.copy()
        sub_display["category_short"] = sub_display["category"].astype(str).str.split("/").str[-1]
        st.plotly_chart(
            horizontal_bar(sub_display, label_col="category_short", value_col="video_count", top_n=14, height=430),
            width="stretch", config={"displayModeBar": False},
        )
    st.markdown("#### 播放量与互动率")
    scatter = scatter_engagement(filtered)
    if scatter is None:
        st.info("当前筛选下没有有效播放量/互动率数据。")
    else:
        st.caption("点击散点查看视频；下方数据表保留全部可跳转链接。")
        selection = st.plotly_chart(
            scatter, width="stretch", config={"displayModeBar": False},
            on_select="rerun", selection_mode="points", key="engagement_scatter",
        )
        points = (selection or {}).get("selection", {}).get("points", []) if isinstance(selection, dict) else []
        if points:
            try:
                index = int(points[0].get("point_index", points[0].get("pointIndex", 0)))
                picked = filtered.iloc[index]
                st.link_button("打开选中视频", str(picked.get("video_url") or video_url(picked)))
            except (IndexError, TypeError, ValueError):
                pass
    with st.expander("查看分区统计表", expanded=True):
        display = parent_stats.copy()
        display["top_video_url"] = display["top_video_bvid"].map(lambda bvid: video_url({"bvid": bvid}))
        st.dataframe(
            display[["category", "video_count", "share_pct", "total_views", "median_views", "avg_engagement_rate", "top_tag", "top_video", "top_video_url"]],
            width="stretch", hide_index=True,
            column_config={
                "total_views": st.column_config.NumberColumn("总播放", format="localized"),
                "median_views": st.column_config.NumberColumn("中位播放", format="localized"),
                "avg_engagement_rate": st.column_config.NumberColumn("互动率", format="%.2f%%"),
                "top_video_url": st.column_config.LinkColumn("示例视频", display_text="打开"),
            },
        )

with tabs[2]:
    st.iframe(visuals.globe_html(globe_data), height=700)
    st.markdown("#### 标签频次")
    if not tag_freq.empty:
        st.plotly_chart(
            horizontal_bar(tag_freq, label_col="tag", value_col="video_count", top_n=20, height=440, value_suffix=" 条"),
            width="stretch", config={"displayModeBar": False},
        )
        with st.expander("查看标签频次表"):
            display = tag_freq.copy()
            display["example_url"] = display["example_bvid"].map(lambda bvid: video_url({"bvid": bvid}))
            st.dataframe(
                display[["tag", "video_count", "share_pct", "median_views", "category_count", "example_title", "example_url"]],
                width="stretch", hide_index=True,
                column_config={
                    "median_views": st.column_config.NumberColumn("中位播放", format="localized"),
                    "example_url": st.column_config.LinkColumn("示例视频", display_text="打开"),
                },
            )
    st.markdown("#### 标签 × 主分区")
    heat = tag_heatmap(filtered, parent_stats)
    if heat is not None:
        st.plotly_chart(heat, width="stretch", config={"displayModeBar": False})
        with st.expander("查看标签 × 分区数据表"):
            records: list[dict[str, Any]] = []
            for row in filtered.to_dict("records"):
                for tag in str(row.get("tags") or "").split("|"):
                    if tag:
                        records.append({"tag": tag, "category": row.get("category_parent") or "其他"})
            cross = (
                pd.DataFrame(records).groupby(["tag", "category"]).size()
                .reset_index(name="video_count").sort_values("video_count", ascending=False)
            )
            st.dataframe(cross.head(100), width="stretch", hide_index=True)

with tabs[3]:
    st.markdown("#### 加权榜单")
    st.caption(
        "默认综合权重：播放 ×0.1 + 点赞 ×0.3 + 投币 ×1.0 + 收藏 ×0.5 + "
        "评论 ×0.75 + 弹幕 ×0.4 + 转发 ×1.5。左侧可切换单项排序。"
    )
    render_rank_cards(
        ranking,
        metric_label=ranking.iloc[0]["rank_metric"] if not ranking.empty else analytics.RANK_LABELS.get(ranking_metric, "综合加权"),
    )
    display = ranking[
        ["rank", "title", "category_path", "uploader", "views", "likes", "coins", "favorites", "replies", "danmaku", "shares", "weighted_score", "video_url"]
    ].copy()
    st.dataframe(
        display, width="stretch", hide_index=True,
        column_config={
            "rank": st.column_config.NumberColumn("排名", format="%d"),
            "title": st.column_config.TextColumn("标题", width="large"),
            "category_path": st.column_config.TextColumn("分区", width="medium"),
            "uploader": st.column_config.TextColumn("UP 主", width="medium"),
            "views": st.column_config.NumberColumn("播放", format="localized"),
            "likes": st.column_config.NumberColumn("点赞", format="localized"),
            "coins": st.column_config.NumberColumn("投币", format="localized"),
            "favorites": st.column_config.NumberColumn("收藏", format="localized"),
            "replies": st.column_config.NumberColumn("评论", format="localized"),
            "danmaku": st.column_config.NumberColumn("弹幕", format="localized"),
            "shares": st.column_config.NumberColumn("转发", format="localized"),
            "weighted_score": st.column_config.NumberColumn("加权分", format="%.0f"),
            "video_url": st.column_config.LinkColumn("链接", display_text="打开视频"),
        },
    )

with tabs[4]:
    st.markdown("#### 个性化分析")
    st.caption("在整体数据分析之上，结合你的分区和标签偏好重排视频；偏好只影响本页，不改变原始统计。")
    default_categories = parent_stats["category"].astype(str).head(2).tolist() if not parent_stats.empty else []
    default_tags = tag_freq["tag"].astype(str).head(3).tolist() if not tag_freq.empty else []
    pcol1, pcol2 = st.columns(2, gap="large")
    with pcol1:
        pref_categories = st.multiselect("偏好分区", all_categories, default=default_categories, key="pref_categories")
    with pcol2:
        pref_tags = st.multiselect("偏好标签", tag_freq["tag"].astype(str).head(30).tolist(), default=default_tags, key="pref_tags")
    recs = personalization.recommend(filtered, categories=pref_categories, tags=pref_tags, top_n=10)
    summary = personalization.build_summary(filtered, recs, categories=pref_categories, tags=pref_tags)
    st.markdown("##### 你的偏好画像")
    for line in summary:
        st.markdown(f'<div class="insight">{html.escape(line)}</div>', unsafe_allow_html=True)
    st.markdown("##### 为你推荐")
    render_personal_cards(recs, top_n=8)
    if not recs.empty:
        with st.expander("查看完整推荐表"):
            st.dataframe(
                recs[["title", "category_path", "uploader", "affinity_score", "recommend_reason", "video_url"]],
                width="stretch", hide_index=True,
                column_config={
                    "title": st.column_config.TextColumn("标题", width="large"),
                    "affinity_score": st.column_config.NumberColumn("偏好得分", format="%.1f"),
                    "recommend_reason": st.column_config.TextColumn("推荐理由", width="large"),
                    "video_url": st.column_config.LinkColumn("链接", display_text="打开视频"),
                },
            )

with tabs[5]:
    st.markdown("#### 视频明细")
    search_col, sort_col = st.columns([2, 1])
    with search_col:
        keyword = st.text_input("搜索标题 / UP 主 / 标签", "")
    with sort_col:
        sort_key = st.selectbox("排序", ["播放量", "互动率", "发布时间", "上榜期数"], index=0)
    table = filtered.copy()
    if keyword.strip():
        needle = keyword.strip().casefold()
        mask = (
            table["title"].astype(str).str.casefold().str.contains(needle, regex=False)
            | table["uploader"].astype(str).str.casefold().str.contains(needle, regex=False)
            | table["tags"].astype(str).str.casefold().str.contains(needle, regex=False)
        )
        table = table[mask]
    sort_map = {"播放量": ("views", False), "互动率": ("engagement_rate", False), "发布时间": ("pubdate", False), "上榜期数": ("appearance_count", False)}
    table = table.sort_values(sort_map[sort_key][0], ascending=sort_map[sort_key][1])
    st.caption(f"显示 {len(table)} 条 · 可按标题、UP 主或标签搜索")
    display_table = table[
        ["title", "video_url", "category_path", "uploader", "views", "engagement_rate", "tags", "issue_number", "appearance_count"]
    ].copy()
    display_table["engagement_rate"] = (display_table["engagement_rate"].astype(float) * 100).round(2)
    st.dataframe(
        display_table, width="stretch", height=560, hide_index=True,
        column_config={
            "title": st.column_config.TextColumn("标题", width="large"),
            "video_url": st.column_config.LinkColumn("链接", display_text="打开", width="small"),
            "category_path": st.column_config.TextColumn("分区", width="medium"),
            "uploader": st.column_config.TextColumn("UP 主", width="medium"),
            "views": st.column_config.NumberColumn("播放", format="localized"),
            "engagement_rate": st.column_config.NumberColumn("互动率", format="%.2f%%"),
            "tags": st.column_config.TextColumn("AI 标签", width="medium"),
            "issue_number": st.column_config.NumberColumn("期数", format="%d"),
            "appearance_count": st.column_config.NumberColumn("上榜次数", format="%d"),
        },
    )

    st.divider()
    st.markdown("#### 单条视频分析")
    pool = filtered.sort_values("views", ascending=False).reset_index(drop=True)
    selected_bvid = st.selectbox(
        "选择一条视频查看分析",
        pool["bvid"].astype(str).tolist(),
        format_func=lambda bvid: next(
            (
                str(row["title"])[:60]
                for _, row in pool.iterrows()
                if str(row["bvid"]) == str(bvid)
            ),
            bvid,
        ),
        key="video_insight_select",
    )
    selected_row = pool[pool["bvid"].astype(str) == str(selected_bvid)].iloc[0]
    metric_cols = st.columns(4, gap="small")
    with metric_cols[0]:
        kpi("播放", compact(selected_row.get("views", 0)), "本条视频")
    with metric_cols[1]:
        kpi("互动率", f"{float(selected_row.get('engagement_rate', 0)) * 100:.2f}%", "赞/币/藏/评/弹/转")
    with metric_cols[2]:
        kpi("投币", compact(selected_row.get("coins", 0)), "含金量按钮")
    with metric_cols[3]:
        kpi("收藏", compact(selected_row.get("favorites", 0)), "先码住再说")
    st.markdown(f"**{html.escape(str(selected_row.get('title') or ''))}**")
    selected_tags = [tag for tag in str(selected_row.get("tags") or "").split("|") if tag]
    st.caption(
        f"{selected_row.get('category_path')} · {selected_row.get('uploader')} · "
        f"标签 {len(selected_tags)} 个：{' / '.join(selected_tags)}"
    )
    st.link_button("打开 B 站视频", str(selected_row.get("video_url") or ""))
    st.markdown("##### 本期人话总结")
    st.markdown(
        insights.video_insight(selected_row, filtered, tag_freq, parent_stats)
    )

with tabs[6]:
    st.markdown("#### 本次分析的质量评估")
    q1, q2, q3, q4 = st.columns(4, gap="small")
    with q1:
        kpi("标签覆盖", f"{tagging.get('tag_coverage_pct', tagging.get('compliance_rate_pct', 0)):.1f}%", "每条至少 1 个 · 数量不设上限")
    with q2:
        kpi("AI 打标覆盖", f"{tagging.get('ai_success_rate_pct', 0):.1f}%", f"回退 {tagging.get('fallback_tags', 0)} 条")
    with q3:
        kpi("标签去重率", f"{100 - tagging.get('duplicate_within_video_videos', 0) / max(1, len(filtered)) * 100:.1f}%", "视频内无重复")
    with q4:
        kpi("分区识别", f"{coverage.get('known_category_pct', 0):.1f}%", "已映射 B 站 v2 分区")
    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("##### 数据规模与覆盖")
        st.dataframe(
            pd.DataFrame([
                ("唯一视频", str(scope.get("unique_videos", 0))),
                ("上榜记录", str(scope.get("appearances", 0))),
                ("跨期重复上榜", str(scope.get("duplicate_appearances", 0))),
                ("唯一标签", str(tagging.get("unique_tags", 0))),
                ("标签赋值", str(tagging.get("tag_assignments", 0))),
                ("标签词汇丰富度", f"{tagging.get('vocabulary_ratio_pct', 0)}%"),
                ("Top10 标签集中度", f"{tagging.get('top10_concentration_pct', 0)}%"),
            ], columns=["指标", "值"]),
            width="stretch", hide_index=True,
        )
    with right:
        st.markdown("##### 打标与接口表现")
        st.dataframe(
            pd.DataFrame([
                ("AI 延迟中位数", f"{tagging.get('median_latency_ms', 0):,} ms"),
                ("AI 延迟 P95", f"{tagging.get('p95_latency_ms', 0):,} ms"),
                ("详情接口成功率", f"{coverage.get('video_detail_success_pct', 0)}%"),
                ("简介为空比例", f"{coverage.get('description_empty_pct', 0)}%"),
                ("web 期数接口", "正常" if meta.get("fetch_report", {}).get("series_list_source") == "web" else "回退 app"),
                ("期数详情成功", f"{meta.get('fetch_report', {}).get('issues_ok', 0)}/{meta.get('fetch_report', {}).get('issues_requested', 0)}"),
            ], columns=["指标", "值"]),
            width="stretch", hide_index=True,
        )
    st.markdown("##### 方法与边界")
    st.markdown(
        "- 分区使用 B 站 v2 分区表映射；`series/one` 被风控时自动改用 app 详情接口，并逐条补齐视频详情。\n"
        "- 标签由 AI 生成，经分区名、UP 名、泛词过滤；标签数量不设上限；失败时回退规则标签并在数据中标记来源。\n"
        "- 加权榜单使用用户给定的互动权重；单项榜单只改变排序，不改动原始数据。\n"
        "- 播放量与互动率为抓取时点快照，会随时间变化；跨期比较时请结合发布时间理解。"
    )
    if meta.get("warnings"):
        with st.expander("运行提示"):
            for warning in meta["warnings"]:
                st.caption(f"• {warning}")

st.divider()
st.caption(
    f"数据目录：{config.DATA_DIR} · 原始 JSON：{config.RAW_DIR} · "
    f"输出：{config.OUTPUT_DIR} · 模型：{meta.get('tag_model', '')}"
)

render_chat_panel(videos)
