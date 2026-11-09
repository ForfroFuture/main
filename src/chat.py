"""Local, context-aware data Q&A for the fixed chat box (no model calls)."""

from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd

from . import analytics

CATEGORY_ALIASES = {
    "鬼畜区": "鬼畜",
    "鬼畜": "鬼畜",
    "游戏区": "游戏",
    "游戏": "游戏",
    "音乐区": "音乐",
    "音乐": "音乐",
    "影视区": "影视",
    "影视": "影视",
    "电影": "影视",
    "电视剧": "影视",
    "知识区": "知识",
    "知识": "知识",
    "科普": "知识",
    "美食区": "美食",
    "美食": "美食",
    "吃的": "美食",
    "动画区": "动画",
    "动画": "动画",
    "番剧": "动画",
    "舞蹈区": "舞蹈",
    "舞蹈": "舞蹈",
    "小剧场": "小剧场",
    "生活区": "生活",
    "生活": "生活",
    "科技区": "科技数码",
    "科技数码": "科技数码",
    "数码": "科技数码",
    "汽车区": "汽车",
    "汽车": "汽车",
    "鬼畜调教": "鬼畜",
    "二次元": "动画",
}

METRIC_MAP = {
    "播放": "views",
    "点赞": "likes",
    "投币": "coins",
    "收藏": "favorites",
    "评论": "replies",
    "弹幕": "danmaku",
    "转发": "shares",
}

HUMOR_LINES = [
    "当然，样本只有这么多条，统计学家的血压可能比互动率还高。",
    "数据不是水晶球，最多算一只会按计算器的锦鲤。",
    "如果下周预测翻车，请把锅甩给推荐算法，它今天不在场。",
    "以上结论仅代表这群视频此刻的状态，不代表互联网明天不发疯。",
]


def _tags(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [item for item in str(value or "").split("|") if item.strip()]


def _fmt(value: float | int) -> str:
    number = float(value or 0)
    if number >= 100_000_000:
        return f"{number / 100_000_000:.2f}亿"
    if number >= 10_000:
        return f"{number / 10_000:.1f}万"
    return f"{int(number):,}"


def _best_contains(query: str, candidates: list[str]) -> str | None:
    hits = [item for item in candidates if item and item in query]
    return max(hits, key=len) if hits else None


def _detect_categories(query: str, categories: list[str]) -> list[str]:
    hits: list[str] = []
    for alias, canonical in sorted(CATEGORY_ALIASES.items(), key=lambda x: len(x[0]), reverse=True):
        if alias in query and canonical in categories and canonical not in hits:
            hits.append(canonical)
    # Preserve order of appearance in the query when possible.
    hits.sort(key=lambda item: query.find(item) if item in query else 999)
    return hits[:4]


def _stats(frame: pd.DataFrame, metric: str | None = None) -> dict[str, Any]:
    if frame.empty:
        return {}
    frame = analytics.add_weighted_score(frame)
    views = pd.to_numeric(frame["views"], errors="coerce").fillna(0)
    engagement = pd.to_numeric(frame["engagement_rate"], errors="coerce").fillna(0) * 100
    tag_counter: Counter[str] = Counter()
    for value in frame["tags"]:
        tag_counter.update(_tags(value))
    sort_column = METRIC_MAP.get(metric or "", "weighted_score")
    ordered = frame.sort_values(sort_column, ascending=False)
    return {
        "count": len(frame),
        "median_views": views.median(),
        "mean_engagement": engagement.mean(),
        "max_views": views.max(),
        "top_tags": tag_counter.most_common(6),
        "top_videos": ordered.head(5),
        "ordered": ordered,
        "share": len(frame) / max(1, len(frame)),
        "metric": metric,
    }


def _extract_intent(query: str, videos: pd.DataFrame) -> dict[str, Any]:
    categories = sorted(
        set(videos["category_parent"].fillna("").astype(str))
        | set(videos["category_name"].fillna("").astype(str)),
        key=len,
        reverse=True,
    )
    all_tags = sorted(
        set(tag for value in videos["tags"] for tag in _tags(value)),
        key=len,
        reverse=True,
    )
    uploaders = sorted(
        set(videos["uploader"].fillna("").astype(str)) - {""},
        key=len,
        reverse=True,
    )
    matched_categories = _detect_categories(query, categories)
    tag = _best_contains(query, all_tags)
    uploader = _best_contains(query, uploaders)
    if uploader:
        matched_categories = []
    if tag and len(matched_categories) < 2 and not any(word in query for word in ("区", "分区", "板块")):
        matched_categories = []
    if any(word in query for word in ("区", "分区", "板块")):
        tag = None
        uploader = None
    metric = next((label for label in METRIC_MAP if label in query), None)
    compare = any(word in query for word in ("对比", "相比", "比一下", "哪个更", "谁更"))
    return {
        "categories": matched_categories,
        "tag": tag,
        "uploader": uploader,
        "metric": metric,
        "compare": compare,
        "why": any(word in query for word in ("为什么", "原因", "怎么火", "为啥")),
        "predict": any(word in query for word in ("预测", "下周", "下月", "下个月", "趋势", "热点", "会火")),
        "recommend": any(word in query for word in ("推荐", "看什么", "值得看", "安利")),
    }


def _context_intent(query: str, videos: pd.DataFrame, history: list[dict[str, Any]] | None) -> tuple[dict[str, Any], bool]:
    current = _extract_intent(query, videos)
    if any((current["categories"], current["tag"], current["uploader"])):
        return current, False
    follow_up = any(word in query for word in ("那", "再", "这个", "它", "呢", "继续", "还是", "上面"))
    if not history or not follow_up:
        return current, False
    users = [item.get("content", "") for item in history if item.get("role") == "user"]
    if not users:
        return current, False
    previous = _extract_intent(str(users[-1]), videos)
    for key in ("categories", "tag", "uploader"):
        if previous.get(key):
            current[key] = previous[key]
    return current, True


def _video_lines(frame: pd.DataFrame, limit: int = 5) -> list[str]:
    lines: list[str] = []
    for index, row in enumerate(frame.head(limit).itertuples(index=False), start=1):
        title = str(getattr(row, "title", "未命名视频"))
        url = str(getattr(row, "video_url", ""))
        lines.append(f"{index}. [{title}]({url}) · {_fmt(getattr(row, 'views', 0))} 播放")
    return lines


def _category_block(name: str, frame: pd.DataFrame, all_count: int) -> tuple[dict[str, Any], list[str]]:
    stats = _stats(frame)
    views = pd.to_numeric(frame["views"], errors="coerce").fillna(0)
    engagement = pd.to_numeric(frame["engagement_rate"], errors="coerce").fillna(0) * 100
    stats["median_views"] = views.median()
    stats["mean_engagement"] = engagement.mean()
    stats["count"] = len(frame)
    stats["share"] = len(frame) / max(1, all_count) * 100
    top_tags = ", ".join(f"{tag}({count})" for tag, count in stats["top_tags"][:4])
    lines = [
        f"- **{name}**：{len(frame)} 条，占 {stats['share']:.1f}%，"
        f"中位播放 {_fmt(stats['median_views'])}，平均互动率 {stats['mean_engagement']:.2f}%；"
        f"门面标签是 {top_tags or '暂无'}。"
    ]
    return stats, lines


def _answer_compare(intent: dict[str, Any], videos: pd.DataFrame, context_used: bool) -> str:
    categories = intent["categories"]
    blocks = []
    for name in categories:
        frame = videos[
            (videos["category_parent"].astype(str) == name)
            | (videos["category_name"].astype(str) == name)
        ]
        blocks.append((name, frame, _stats(frame)))
    lines = [
        f"接着{'上一句' if context_used else '你点的两个分区'}说，我把 **"
        + " vs ".join(name for name, _, _ in blocks)
        + f"** 放在同一张桌上比了比。当前样本共 {len(videos)} 条，谁也别嫌桌子小。",
        "",
        "| 指标 | " + " | ".join(name for name, _, _ in blocks) + " |",
        "| --- | " + " | ".join("---" for _ in blocks) + " |",
        "| 视频数 | " + " | ".join(str(len(frame)) for _, frame, _ in blocks) + " |",
        "| 中位播放 | " + " | ".join(_fmt(stats["median_views"]) for _, _, stats in blocks) + " |",
        "| 平均互动率 | " + " | ".join(f"{stats['mean_engagement']:.2f}%" for _, _, stats in blocks) + " |",
        "| 最高播放 | " + " | ".join(_fmt(stats["max_views"]) for _, _, stats in blocks) + " |",
        "",
        "**人话结论**：",
    ]
    scale_winner = max(blocks, key=lambda item: item[2]["count"])
    engagement_winner = max(blocks, key=lambda item: item[2]["mean_engagement"])
    lines.append(
        f"论数量，**{scale_winner[0]}** 更像大超市，货架多、路过的人也多；"
        f"论互动，**{engagement_winner[0]}** 更像小酒馆，人不一定最多，但坐下的人愿意聊。"
    )
    for name, _, stats in blocks:
        lines.append(
            f"- {name} 的高频标签：" + "、".join(f"{tag}({count})" for tag, count in stats["top_tags"][:5])
        )
    lines.extend(
        [
            "",
            "**为什么会这样**：分区本身就是一层内容预期。观众点进一个分区时，已经带着“我想看什么”的滤镜；"
            "同样的播放量，在不同分区会被解读成不同的情绪价值。数量领先通常靠供给和分发，"
            "互动领先则更像是内容把观众按在了座位上。",
            "",
            "**补充观察**：如果只看中位播放，两个分区都可能被少数爆款拉高平均数；"
            "所以这里特意把中位数和最高播放分开写，免得一边拿平均值装门面。",
            "",
            "**下一周 / 下个月**：",
            f"可以观察 **{scale_winner[0]}** 的头部标签是否能跨区扩散，以及 "
            f"**{engagement_winner[0]}** 的高互动题材是否会被其他分区借走。"
            "跨区借梗通常比单区自嗨更容易长成下一波热点。",
            "",
            "**代表视频**：",
        ]
    )
    for name, _, stats in blocks:
        lines.append(f"- {name}：")
        for item in _video_lines(stats["top_videos"], limit=2):
            lines.append(f"  {item}")
    lines.extend(
        [
            "",
            "**无意义吐槽**：",
            f"- {HUMOR_LINES[len(categories) % len(HUMOR_LINES)]}",
            f"- {HUMOR_LINES[(len(categories) + 1) % len(HUMOR_LINES)]}",
            "",
            "_以上是本地样本的对比观察，不调用外部模型。_",
        ]
    )
    return "\n".join(lines)


def answer_query(
    query: str,
    videos: pd.DataFrame,
    history: list[dict[str, Any]] | None = None,
) -> str:
    """Answer category / tag / uploader / comparison / ranking questions."""
    query = (query or "").strip()
    if not query:
        return "想问点什么？试试“鬼畜区的情况”“鬼畜和游戏哪个更火”或“下周会火什么”。"
    if videos.empty:
        return "当前还没有分析数据，先在左侧完成一次拉取，我再来接客。"

    full = analytics.add_weighted_score(videos)
    intent, context_used = _context_intent(query, full, history)
    categories = intent["categories"]
    tag = intent["tag"]
    uploader = intent["uploader"]
    metric = intent["metric"]
    if len(categories) >= 2:
        return _answer_compare(intent, full, context_used)

    filtered = full.copy()
    scope_parts: list[str] = []
    if categories:
        category = categories[0]
        filtered = filtered[
            (filtered["category_parent"].astype(str) == category)
            | (filtered["category_name"].astype(str) == category)
        ]
        scope_parts.append(f"分区「{category}」")
    if tag:
        filtered = filtered[
            filtered["tags"].fillna("").astype(str).map(lambda value: tag in _tags(value))
        ]
        scope_parts.append(f"标签「{tag}」")
    if uploader:
        filtered = filtered[filtered["uploader"].astype(str) == uploader]
        scope_parts.append(f"UP主「{uploader}」")
    if filtered.empty:
        options = "、".join(sorted(set(full["category_parent"].astype(str)))[:10])
        return (
            f"我把「{query}」翻了一遍，没找到匹配视频。\n\n"
            f"当前可选分区：{options}。也可以问“鬼畜区的情况”或“本周最火”。"
        )

    metric_column = METRIC_MAP.get(metric or "", "weighted_score")
    if metric:
        filtered[metric_column] = pd.to_numeric(filtered[metric_column], errors="coerce").fillna(0)
        ordered = filtered.sort_values(metric_column, ascending=False)
    else:
        ordered = filtered.sort_values("weighted_score", ascending=False)
    stats = _stats(filtered, metric)
    views = pd.to_numeric(filtered["views"], errors="coerce").fillna(0)
    engagement = pd.to_numeric(filtered["engagement_rate"], errors="coerce").fillna(0) * 100
    scope = " + ".join(scope_parts) or "当前样本"
    top_tags = stats["top_tags"]
    tag_text = "、".join(f"{name}({count})" for name, count in top_tags[:5]) or "标签样本不足"

    lines = [
        f"先给结论：按 **{scope}** 查，当前 {len(full)} 条样本里命中 **{len(filtered)} 条**"
        f"（{len(filtered) / len(full) * 100:.1f}%）。"
        + ("这句是接着你上一问说的。" if context_used else ""),
        "",
        f"- 中位播放：**{_fmt(stats['median_views'])}**",
        f"- 平均互动率：**{stats['mean_engagement']:.2f}%**",
        f"- 最高播放：**{_fmt(stats['max_views'])}**",
        f"- 高频标签：**{tag_text}**",
    ]

    if categories:
        all_cat = full[(full["category_parent"].astype(str) == categories[0])]
        all_engagement = (
            float(pd.to_numeric(all_cat["engagement_rate"], errors="coerce").median()) * 100
            if not all_cat.empty
            else 0
        )
        lines.extend(
            [
                "",
                "**为什么值得看（人话版）**：",
                f"这组视频的播放中位数约为 {_fmt(stats['median_views'])}，"
                f"平均互动率 {stats['mean_engagement']:.2f}%（全分区中位约 {all_engagement:.2f}%）。"
                + (
                    "互动率明显高于分区常态，说明观众不只是路过，甚至可能顺手把按钮都点了一遍。"
                    if stats["mean_engagement"] > all_engagement * 1.1
                    else "数据不算炸裂，但胜在标签集中、受众清楚，属于细水长流型内容。"
                ),
                f"标签组合里最抢眼的是 **{top_tags[0][0] if top_tags else '暂无'}**，"
                "它把“这是什么”说得很清楚，也让推荐系统省了不少脑细胞。",
            ]
        )
    elif tag:
        category_counter: Counter[str] = Counter(
            filtered["category_parent"].fillna("其他").astype(str)
        )
        lines.extend(
            [
                "",
                "**补一句人话**：",
                f"「{tag}」不是一个孤零零的标签，它跨了 {len(category_counter)} 个分区。"
                "跨区标签通常比单区标签更有机会长成通用题材，也更容易被不同受众重复消费。",
            ]
        )
    elif uploader:
        lines.extend(
            [
                "",
                "**补一句人话**：",
                f"这位 UP 主的命中视频中位播放是 {_fmt(stats['median_views'])}，"
                "数据不一定每次都在天上飞，但能稳定出现在每周必看里，本身就是一种内容能力。",
            ]
        )
    else:
        top_categories = (
            full.groupby("category_parent").size().sort_values(ascending=False).head(5)
        )
        lines.extend(
            [
                "",
                "**本期结构**：",
                "- 分区前五：" + "、".join(f"{name}({count})" for name, count in top_categories.items()),
                "- 这不是“谁最火”的单一答案，更像是不同内容一起拼出来的注意力拼图。",
            ]
        )

    # Supplement with the next adjacent content cluster.
    suggestions = [
        str(value)
        for value in full["category_parent"].dropna().astype(str).unique()
        if value not in categories
    ][:3]
    if suggestions:
        lines.extend(
            [
                "",
                "**顺手补充**：",
                "如果你还想横向看，可以继续问：" + "、".join(f"“{name}区的情况”" for name in suggestions) + "。"
                "不同分区放一起比，通常比单看一个分区更容易看出平台的口味。",
            ]
        )

    lines.extend(
        [
            "",
            "**下一周 / 下个月看什么**：",
            (
                f"下一周值得盯 **{top_tags[0][0] if top_tags else '同分区新题材'}** 是否继续扩散；"
                f"下个月可以观察 **{top_tags[1][0] if len(top_tags) > 1 else '跨区二创'}** "
                "与当前题材的组合。热点通常不是凭空出现，而是几个标签先在小圈子里反复碰撞，"
                "然后突然被推荐页一脚踹到广场中央。"
            ),
            "",
            "**代表视频**：",
        ]
    )
    lines.extend(_video_lines(ordered, limit=5))
    lines.extend(
        [
            "",
            "**无意义吐槽**：",
            f"- {HUMOR_LINES[len(query) % len(HUMOR_LINES)]}",
            f"- {HUMOR_LINES[(len(query) + 2) % len(HUMOR_LINES)]}",
            "",
            "_回答基于当前本地样本，不调用外部模型；链接可直接打开 B 站视频。_",
        ]
    )
    return "\n".join(lines)
