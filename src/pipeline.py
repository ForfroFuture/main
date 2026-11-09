"""End-to-end fetch -> enrich -> AI tag -> analyse -> export pipeline."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import date
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from . import analytics, config, exporter, packaging, preprocess
from .bilibili import BilibiliClient, Issue, IssuePayload, VideoDetail, utc_now_iso
from .tagger import AITagger, TagResult

ProgressFn = Callable[[dict[str, Any]], None]


def _make_logger() -> logging.Logger:
    os.makedirs(config.LOGS_DIR, exist_ok=True)
    logger = logging.getLogger("bili_weekly")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.FileHandler(
            config.LOGS_DIR / "pipeline.log", encoding="utf-8"
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        )
        logger.addHandler(handler)
        stream = logging.StreamHandler()
        stream.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(stream)
    return logger


def _write_json(path: Path, payload: Any) -> None:
    os.makedirs(path.parent, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _selection_label(selected: list[Issue]) -> str:
    ordered = sorted(selected, key=lambda item: item.number)
    if not ordered:
        return ""
    numbers = [item.number for item in ordered]
    if len(numbers) == 1:
        return ordered[0].label
    contiguous = numbers == list(range(numbers[0], numbers[-1] + 1))
    number_label = (
        f"第{numbers[0]}–{numbers[-1]}期" if contiguous else "第" + "、".join(map(str, numbers)) + "期"
    )
    starts = [item.start_date for item in ordered if item.start_date]
    ends = [item.end_date for item in ordered if item.end_date]
    span = f"（{min(starts)} 至 {max(ends)}）" if starts and ends else ""
    return number_label + span


def _content_hash(record: dict[str, Any]) -> str:
    payload = "|".join(
        [
            str(record.get("bvid") or ""),
            str(record.get("title") or ""),
            str(record.get("category_path") or ""),
            str(record.get("description") or ""),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def run_analysis(
    *,
    mode: str = "latest",
    issue_number: int | None = None,
    start: date | str | None = None,
    end: date | str | None = None,
    use_ai: bool = True,
    force_retag: bool = False,
    max_workers: int = config.TAG_MAX_WORKERS,
    model: str | None = None,
    ai_base_url: str | None = None,
    ai_token: str | None = None,
    max_issues: int = config.MAX_ISSUES_PER_RUN,
    progress: ProgressFn | None = None,
    logger: logging.Logger | None = None,
) -> dict[str, Any]:
    """Run the complete pipeline for latest, one issue, or a date range."""
    config.ensure_dirs()
    log = logger or _make_logger()

    def emit(stage: str, message: str, **extra: Any) -> None:
        payload = {"stage": stage, "message": message, **extra}
        log.info(message)
        if progress:
            try:
                progress(payload)
            except Exception:  # noqa: BLE001 - UI progress must never break data work
                log.debug("progress callback failed", exc_info=True)

    emit("listing", "读取每周必看期数列表…")
    client = BilibiliClient(logger=log.info)
    issues, list_source, list_raw = client.list_issues()
    _write_json(config.RAW_DIR / "series_list.json", list_raw)
    _write_json(
        config.RAW_DIR / "series_list.meta.json",
        {
            "source": list_source,
            "fetched_at": utc_now_iso(),
            "issue_count": len(issues),
            "url": config.WEB_SERIES_LIST_URL if list_source == "web" else config.APP_SERIES_LIST_URL,
        },
    )

    selected = client.select_issues(
        issues, mode=mode, number=issue_number, start=start, end=end
    )
    if not selected:
        raise ValueError("所选时间范围内没有匹配的每周必看期数。")
    if len(selected) > max_issues:
        raise ValueError(
            f"本次选择 {len(selected)} 期，超过单次上限 {max_issues} 期；"
            "请缩小时间范围或分批分析。"
        )
    selection_label = _selection_label(selected)
    emit(
        "selected",
        f"已选择 {selection_label}，共 {len(selected)} 期。",
        total=len(selected),
    )

    payloads: dict[int, IssuePayload] = {}
    issue_rows: list[dict[str, Any]] = []
    details: dict[str, VideoDetail] = {}
    tag_inputs: dict[str, dict[str, Any]] = {}
    appearance_inputs: list[tuple[Issue, dict[str, Any], VideoDetail | None, int]] = []
    fetch_failures: list[dict[str, str]] = []
    raw_issue_summary: list[dict[str, Any]] = []
    raw_video_summary: list[dict[str, Any]] = []

    for issue_index, issue in enumerate(selected, start=1):
        emit(
            "issue",
            f"拉取第{issue.number}期：{issue.subject or issue.name}…",
            current=issue_index,
            total=len(selected),
            issue_number=issue.number,
        )
        try:
            payload = client.fetch_issue(issue.number)
        except Exception as exc:  # noqa: BLE001
            log.error("issue %s failed: %s", issue.number, exc)
            fetch_failures.append({"scope": f"issue:{issue.number}", "error": str(exc)})
            continue
        payloads[issue.number] = payload
        issue_dir = config.RAW_ISSUES_DIR / str(issue.number)
        _write_json(issue_dir / "series_one.json", payload.raw)
        _write_json(
            issue_dir / "series_one.meta.json",
            {
                "issue_number": issue.number,
                "source": payload.source,
                "fetched_at": utc_now_iso(),
                "video_cards": len(payload.videos),
                "url": config.WEB_SERIES_ONE_URL
                if payload.source == "web"
                else config.APP_SERIES_ONE_URL,
            },
        )
        raw_issue_summary.append(
            {
                "issue_number": issue.number,
                "source": payload.source,
                "video_cards": len(payload.videos),
                "path": str(issue_dir / "series_one.json"),
            }
        )

        seen_in_issue: set[str] = set()
        for rank, card in enumerate(payload.videos, start=1):
            bvid = str(card.get("bvid") or "").strip()
            if not bvid or bvid in seen_in_issue:
                continue
            seen_in_issue.add(bvid)
            if bvid not in details:
                detail = client.fetch_video_detail(bvid)
                details[bvid] = detail
                if detail.raw is not None:
                    video_path = issue_dir / "videos" / f"{bvid}.json"
                    _write_json(video_path, detail.raw)
                _write_json(
                    issue_dir / "videos" / f"{bvid}.meta.json",
                    {
                        "bvid": bvid,
                        "source": detail.source,
                        "error": detail.error,
                        "bilibili_tags": detail.tags,
                        "fetched_at": utc_now_iso(),
                    },
                )
                raw_video_summary.append(
                    {
                        "bvid": bvid,
                        "source": detail.source,
                        "ok": detail.view is not None,
                        "error": detail.error,
                        "path": str(issue_dir / "videos" / f"{bvid}.json"),
                    }
                )
                if detail.view is None:
                    fetch_failures.append(
                        {"scope": f"video:{bvid}", "error": detail.error or "unknown"}
                    )
            detail = details[bvid]
            provisional = preprocess.normalise_video(
                issue=issue,
                card=card,
                detail=detail,
                rank=rank,
                tag_result=None,
            )
            tag_inputs.setdefault(bvid, provisional)
            appearance_inputs.append((issue, card, detail, rank))

            emit(
                "video",
                f"第{issue.number}期 {rank}/{len(payload.videos)} · {bvid}",
                current=rank,
                total=len(payload.videos),
                issue_number=issue.number,
                bvid=bvid,
            )

        issue_rows.append(
            preprocess.normalise_issue(
                issue,
                payload,
                video_count=len(seen_in_issue),
            )
        )

    if not appearance_inputs:
        raise RuntimeError("没有成功获取任何视频，请检查网络或 B 站接口状态。")

    if client.warnings:
        log.warning("Bilibili warnings: %s", " | ".join(client.warnings))

    tagger = AITagger(
        base_url=ai_base_url,
        token=ai_token,
        model=model,
        max_workers=max_workers,
        logger=log.info,
        use_ai=use_ai,
    )
    if use_ai and not tagger.available:
        emit("tagging", "AI 接口未配置，将使用规则回退标签。")
    else:
        emit(
            "tagging",
            f"开始 AI 打标：{len(tag_inputs)} 条视频，模型 {tagger.model}，并发 {max_workers}…",
            current=0,
            total=len(tag_inputs),
        )

    def on_tag_progress(done: int, total: int, result: TagResult) -> None:
        source = "缓存" if result.cached else ("AI" if result.source == "ai" else "回退")
        emit(
            "tagging",
            f"标签 {done}/{total} · {result.bvid} · {source}",
            current=done,
            total=total,
            bvid=result.bvid,
        )

    tag_results = tagger.tag_many(
        tag_inputs.values(), force=force_retag, progress=on_tag_progress
    )

    records: list[dict[str, Any]] = []
    for issue, card, detail, rank in appearance_inputs:
        bvid = str(card.get("bvid") or "")
        record = preprocess.normalise_video(
            issue=issue,
            card=card,
            detail=detail,
            rank=rank,
            tag_result=tag_results.get(bvid),
        )
        record["content_hash"] = _content_hash(record)
        records.append(record)

    videos, appearances = preprocess.build_frames(records)
    tags_frame = preprocess.build_tags_frame(videos)
    issues_frame = preprocess.build_issues_frame(issue_rows, appearances)

    video_total = len(details)
    video_ok = sum(1 for detail in details.values() if detail.view is not None)
    fetch_report = {
        "issues_requested": len(selected),
        "issues_ok": len(payloads),
        "issue_failures": fetch_failures,
        "video_total": video_total,
        "video_ok": video_ok,
        "video_failed": video_total - video_ok,
        "series_list_source": list_source,
        "issue_sources": {str(key): value.source for key, value in payloads.items()},
    }
    meta = {
        "generated_at": utc_now_iso(),
        "selection_mode": mode,
        "selection_label": selection_label,
        "selected_issues": [issue.to_dict() for issue in selected],
        "tag_model": tagger.model,
        "tag_prompt_version": config.TAG_PROMPT_VERSION,
        "tag_range": [config.TAG_MIN, config.TAG_MAX],
        "use_ai": bool(use_ai),
        "fetch_report": fetch_report,
        "warnings": client.warnings,
        "paths": {
            "raw": str(config.RAW_DIR),
            "processed": str(config.PROCESSED_DIR),
            "output": str(config.OUTPUT_DIR),
        },
        "raw_summary": {
            "series_list": str(config.RAW_DIR / "series_list.json"),
            "issues": raw_issue_summary,
            "videos": raw_video_summary,
        },
        "counts": {
            "issues": int(videos["issue_number"].nunique()),
            "videos": int(len(videos)),
            "appearances": int(len(appearances)),
            "tags": int(len(tags_frame)),
        },
    }
    processed_paths = preprocess.save_processed(
        videos, appearances, issues_frame, tags_frame, meta
    )

    emit("analysing", "计算标签频次与分区统计…")
    tag_freq = analytics.tag_frequency(videos)
    parent_stats = analytics.category_stats(videos, level="parent")
    sub_stats = analytics.category_stats(videos, level="path")
    issue_perf = analytics.issue_stats(issues_frame, appearances)
    evaluation = analytics.build_quality_evaluation(
        videos, appearances, issues_frame, meta
    )
    findings = analytics.headline_findings(videos, tag_freq, parent_stats)

    emit("exporting", "生成标签频次、分区统计、词云与评估文件…")
    output_paths = exporter.export_outputs(
        videos=videos,
        appearances=appearances,
        issues=issues_frame,
        tag_freq=tag_freq,
        parent_stats=parent_stats,
        sub_stats=sub_stats,
        issue_perf=issue_perf,
        evaluation=evaluation,
        meta=meta,
        findings=findings,
    )
    try:
        package_path = packaging.build_app_package()
    except Exception as exc:  # noqa: BLE001
        log.warning("package build failed: %s", exc)
        package_path = ""

    result = {
        "meta": meta,
        "evaluation": evaluation,
        "findings": findings,
        "processed_paths": processed_paths,
        "output_paths": output_paths,
        "package_path": package_path,
        "tag_frequency": tag_freq,
        "category_stats": parent_stats,
    }
    emit(
        "done",
        f"完成：{len(videos)} 条视频、{len(tag_freq)} 个标签、{len(parent_stats)} 个分区。",
        current=len(videos),
        total=len(videos),
    )
    return result
