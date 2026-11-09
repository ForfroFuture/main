"""Export analysis tables, the tag word cloud, Excel workbook and report."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from . import analytics, config, personalization

BLUE_RAMP = [
    "#cde2fb",
    "#9ec5f4",
    "#6da7ec",
    "#3987e5",
    "#2a78d6",
    "#1c5cab",
    "#184f95",
    "#104281",
]
BLUE = "#2a78d6"
INK = "#0b0b0b"
SURFACE = "#fcfcfb"


def _font_path() -> str | None:
    candidates = [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\msyhbd.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return None


def generate_wordcloud(
    tag_freq: pd.DataFrame,
    output_path: Path,
    *,
    max_words: int = 120,
) -> bool:
    """Render a frequency-scaled Chinese word cloud in a single blue ramp."""
    if tag_freq.empty:
        return False
    frequencies = {
        str(row["tag"]): max(1, int(row["video_count"]))
        for _, row in tag_freq.head(max_words).iterrows()
    }
    if not frequencies:
        return False
    # Compress the frequency range so a few repeated tags do not swallow the
    # canvas; ordering (and therefore magnitude) is preserved.
    display_frequencies = {
        tag: max(1.0, count ** 0.58) for tag, count in frequencies.items()
    }
    font = _font_path()

    def color_for(word: str, font_size: int, position: Any, orientation: Any, random_state: Any = None, **_: Any) -> str:
        ratio = display_frequencies.get(word, 1) / max(display_frequencies.values())
        index = min(len(BLUE_RAMP) - 1, max(0, int(ratio * (len(BLUE_RAMP) - 1))))
        return BLUE_RAMP[index]

    try:
        from wordcloud import WordCloud

        cloud = WordCloud(
            font_path=font,
            width=1600,
            height=760,
            background_color=SURFACE,
            max_words=max_words,
            prefer_horizontal=0.94,
            max_font_size=140,
            min_font_size=10,
            relative_scaling=0.35,
            margin=7,
            random_state=42,
            collocations=False,
            color_func=color_for,
        ).generate_from_frequencies(display_frequencies)
        os.makedirs(Path(output_path).parent, exist_ok=True)
        # Add a quiet outer margin so large words are never clipped by the
        # canvas edge.
        from PIL import Image

        rendered = cloud.to_image().convert("RGB")
        canvas = Image.new("RGB", (1800, 900), SURFACE)
        canvas.paste(rendered, (100, 70))
        canvas.save(output_path)
        return True
    except Exception:
        # A readable typographic fallback keeps the deliverable intact even if
        # the optional wordcloud wheel is unavailable.
        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            top = tag_freq.head(50).sort_values("video_count", ascending=False)
            fig, ax = plt.subplots(figsize=(14, 7), dpi=150)
            ax.set_facecolor(SURFACE)
            fig.patch.set_facecolor(SURFACE)
            ax.axis("off")
            positions = [
                (0.5, 0.9), (0.25, 0.75), (0.75, 0.75), (0.15, 0.58),
                (0.42, 0.58), (0.7, 0.58), (0.88, 0.58), (0.2, 0.4),
                (0.5, 0.4), (0.8, 0.4), (0.35, 0.22), (0.65, 0.22),
            ]
            for i, (_, row) in enumerate(top.head(len(positions)).iterrows()):
                ax.text(
                    *positions[i],
                    str(row["tag"]),
                    ha="center",
                    va="center",
                    fontsize=max(9, 28 - i * 1.4),
                    color=BLUE_RAMP[min(len(BLUE_RAMP) - 1, 2 + i // 8)],
                    fontfamily="Microsoft YaHei" if font else None,
                )
            fig.savefig(output_path, bbox_inches="tight", facecolor=SURFACE)
            plt.close(fig)
            return True
        except Exception:
            return False


def _write_excel(
    path: Path,
    tables: dict[str, pd.DataFrame],
    meta: dict[str, Any],
    evaluation: dict[str, Any],
) -> None:
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    os.makedirs(path.parent, exist_ok=True)
    summary_rows = [
        ("生成时间", meta.get("generated_at", "")),
        ("期数范围", meta.get("selection_label", "")),
        ("视频数（去重）", evaluation.get("scope", {}).get("unique_videos", "")),
        ("上榜记录", evaluation.get("scope", {}).get("appearances", "")),
        ("标签赋值数", evaluation.get("tagging", {}).get("tag_assignments", "")),
        ("标签覆盖率", f"{evaluation.get('tagging', {}).get('tag_coverage_pct', 0)}%"),
        ("AI 覆盖率", f"{evaluation.get('tagging', {}).get('ai_success_rate_pct', 0)}%"),
        ("AI 模型", meta.get("tag_model", "")),
    ]
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame(summary_rows, columns=["指标", "值"]).to_excel(
            writer, sheet_name="报告摘要", index=False
        )
        for name, frame in tables.items():
            if frame is None:
                continue
            frame.to_excel(writer, sheet_name=name[:31], index=False)
        for sheet in writer.sheets.values():
            sheet.freeze_panes = "A2"
            for cell in sheet[1]:
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor="2A78D6")
                cell.alignment = Alignment(vertical="center")
            for idx, column in enumerate(sheet.iter_cols(values_only=True), start=1):
                max_len = max((len(str(value)) for value in column if value is not None), default=8)
                sheet.column_dimensions[get_column_letter(idx)].width = min(max(10, max_len + 2), 64)
            sheet.row_dimensions[1].height = 24


def _markdown_table(frame: pd.DataFrame, columns: list[str], limit: int = 10) -> str:
    if frame.empty:
        return "_暂无数据_"
    subset = frame.head(limit)[columns].copy()
    for column in subset.columns:
        if pd.api.types.is_float_dtype(subset[column]):
            subset[column] = subset[column].map(lambda value: f"{value:.2f}")
    header = "| " + " | ".join(subset.columns) + " |"
    divider = "| " + " | ".join(["---"] * len(subset.columns)) + " |"
    rows = [
        "| " + " | ".join(str(value) for value in row) + " |"
        for row in subset.itertuples(index=False, name=None)
    ]
    return "\n".join([header, divider, *rows])


def write_report(
    path: Path,
    *,
    meta: dict[str, Any],
    evaluation: dict[str, Any],
    findings: Iterable[str],
    parent_stats: pd.DataFrame,
    tag_freq: pd.DataFrame,
    ranking: pd.DataFrame | None = None,
    personalized_summary: list[str] | None = None,
    personalized_recs: pd.DataFrame | None = None,
) -> None:
    tagging = evaluation.get("tagging", {})
    scope = evaluation.get("scope", {})
    coverage = evaluation.get("coverage", {})
    performance = evaluation.get("performance", {})
    lines = [
        "# B站每周必看 · 内容分析报告",
        "",
        f"- 生成时间：{meta.get('generated_at', '')}",
        f"- 期数范围：{meta.get('selection_label', '')}",
        f"- 视频：{scope.get('unique_videos', 0)} 条去重视频 / {scope.get('appearances', 0)} 条上榜记录",
        f"- 模型：{meta.get('tag_model', '')}；提示词版本：{meta.get('tag_prompt_version', '')}",
        "",
        "## 核心发现",
        "",
    ]
    lines.extend(f"- {finding}" for finding in findings)
    lines.extend(
        [
            "",
            "## 分区概览",
            "",
            _markdown_table(
                parent_stats,
                ["category", "video_count", "share_pct", "median_views", "avg_engagement_rate", "top_tag"],
                limit=12,
            ),
            "",
            "## 高频标签",
            "",
            _markdown_table(
                tag_freq,
                ["tag", "video_count", "share_pct", "median_views", "category_count"],
                limit=20,
            ),
            "",
            "## 综合加权榜单 Top 10",
            "",
            "权重：播放 0.1、点赞 0.3、投币 1.0、收藏 0.5、评论 0.75、弹幕 0.4、转发 1.5。",
            "",
            _markdown_table(
                ranking if ranking is not None else pd.DataFrame(),
                ["rank", "title", "category_path", "uploader", "weighted_score"],
                limit=10,
            ),
            "",
            "## 个性化分析（默认画像）",
            "",
            "默认以样本前 2 个分区和前 3 个标签作为偏好画像；应用内可自由调整。",
            "",
        ]
    )
    lines.extend(f"- {line}" for line in (personalized_summary or []))
    lines.extend(["", "推荐视频："])
    if personalized_recs is not None and not personalized_recs.empty:
        for row in personalized_recs.head(8).itertuples(index=False):
            url = getattr(row, "video_url", "")
            title = getattr(row, "title", "")
            lines.append(f"- [{title}]({url}) · 偏好得分 {getattr(row, 'affinity_score', 0):.1f}")
    lines.extend(
        [
            "",
            "## 数据质量评估",
            "",
            f"- 标签覆盖率：**{tagging.get('tag_coverage_pct', tagging.get('compliance_rate_pct', 0))}%**"
            f"（{tagging.get('compliant_videos', 0)}/{scope.get('unique_videos', 0)} 条至少 1 个标签）",
            f"- AI 打标覆盖率：**{tagging.get('ai_success_rate_pct', 0)}%**"
            f"；回退规则标签 {tagging.get('fallback_tags', 0)} 条",
            f"- 唯一标签数：{tagging.get('unique_tags', 0)}；标签词汇丰富度："
            f"{tagging.get('vocabulary_ratio_pct', 0)}%；Top10 集中度：{tagging.get('top10_concentration_pct', 0)}%",
            f"- 平均每视频标签数：{tagging.get('avg_tags_per_video', 0)}（数量不设上限）；"
            f"平均标签长度：{tagging.get('avg_tag_chars', 0)} 字",
            f"- AI 延迟中位数 / P95：{tagging.get('median_latency_ms', 0)} ms / "
            f"{tagging.get('p95_latency_ms', 0)} ms",
            f"- 分区识别覆盖：{coverage.get('known_category_pct', 0)}%；"
            f"视频详情成功率：{coverage.get('video_detail_success_pct', 0)}%",
            f"- 中位播放量：{performance.get('median_views', 0):,}；"
            f"中位互动率：{performance.get('median_engagement_rate_pct', 0)}%",
            "",
            "## 方法说明",
            "",
            "数据来自 B 站“每周必看”公开期数接口（`series/list` 与 `series/one`）。"
            "当 web 详情接口被风控（-352）时自动切换到 app 详情接口，并逐条调用视频详情接口补齐分区、播放/互动数据和 UP 主标签。"
            "标签由大模型基于标题、简介、分区、推荐语、UP 主和 B 站现有标签生成，经去重、分区名/UP 名过滤，标签数量不设上限；失败时使用规则回退并单独标记。"
            "分区使用 B 站 v2 分区表映射。",
            "",
            "## 文件",
            "",
            "- `tag_frequency.csv` / `category_stats.csv` / `subcategory_stats.csv`",
            "- `issue_stats.csv` / `ranking.csv` / `videos_with_tags.csv`",
            "- `personalized_default.json` / `bilibili_weekly_analytics.xlsx`",
            "- `tag_wordcloud.png` / `evaluation.json`",
            "",
        ]
    )
    os.makedirs(path.parent, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def export_outputs(
    *,
    videos: pd.DataFrame,
    appearances: pd.DataFrame,
    issues: pd.DataFrame,
    tag_freq: pd.DataFrame,
    parent_stats: pd.DataFrame,
    sub_stats: pd.DataFrame,
    issue_perf: pd.DataFrame,
    evaluation: dict[str, Any],
    meta: dict[str, Any],
    findings: list[str],
    ranking: pd.DataFrame | None = None,
    output_dir: Path | None = None,
) -> dict[str, str]:
    """Write every requested artifact into data/output."""
    target = Path(output_dir or config.OUTPUT_DIR)
    os.makedirs(target, exist_ok=True)
    ranking = ranking if ranking is not None else analytics.ranking_table(videos)
    default_categories = (
        parent_stats["category"].astype(str).head(2).tolist()
        if not parent_stats.empty
        else []
    )
    default_tags = (
        tag_freq["tag"].astype(str).head(3).tolist()
        if not tag_freq.empty
        else []
    )
    personalized_recs = personalization.recommend(
        videos, categories=default_categories, tags=default_tags, top_n=10
    )
    personalized_summary = personalization.build_summary(
        videos, personalized_recs, categories=default_categories, tags=default_tags
    )
    paths = {
        "tag_frequency_csv": target / "tag_frequency.csv",
        "category_stats_csv": target / "category_stats.csv",
        "subcategory_stats_csv": target / "subcategory_stats.csv",
        "issue_stats_csv": target / "issue_stats.csv",
        "videos_csv": target / "videos_with_tags.csv",
        "ranking_csv": target / "ranking.csv",
        "personalized": target / "personalized_default.json",
        "wordcloud": target / "tag_wordcloud.png",
        "evaluation": target / "evaluation.json",
        "report": target / "analysis_report.md",
        "excel": target / "bilibili_weekly_analytics.xlsx",
    }
    tag_freq.to_csv(paths["tag_frequency_csv"], index=False, encoding="utf-8-sig")
    parent_stats.to_csv(paths["category_stats_csv"], index=False, encoding="utf-8-sig")
    sub_stats.to_csv(paths["subcategory_stats_csv"], index=False, encoding="utf-8-sig")
    issue_perf.to_csv(paths["issue_stats_csv"], index=False, encoding="utf-8-sig")
    videos.to_csv(paths["videos_csv"], index=False, encoding="utf-8-sig")
    ranking.to_csv(paths["ranking_csv"], index=False, encoding="utf-8-sig")
    personalization.save_profile(
        categories=default_categories,
        tags=default_tags,
        recommendations=personalized_recs,
        summary=personalized_summary,
        path=paths["personalized"],
    )
    paths["evaluation"].write_text(
        json.dumps(evaluation, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    generate_wordcloud(tag_freq, paths["wordcloud"])
    _write_excel(
        paths["excel"],
        {
            "标签频次": tag_freq,
            "分区统计": parent_stats,
            "子分区统计": sub_stats,
            "期数趋势": issue_perf,
            "综合榜单": ranking,
            "默认个性化": personalized_recs,
            "视频明细": videos,
            "上场记录": appearances,
        },
        meta,
        evaluation,
    )
    write_report(
        paths["report"],
        meta=meta,
        evaluation=evaluation,
        findings=findings,
        parent_stats=parent_stats,
        tag_freq=tag_freq,
        ranking=ranking,
        personalized_summary=personalized_summary,
        personalized_recs=personalized_recs,
    )
    return {key: str(value) for key, value in paths.items()}
