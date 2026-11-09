"""Self-contained interactive SVG/HTML chart components for Streamlit."""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from typing import Any, Iterable

import pandas as pd

PALETTE_LIGHT = [
    "#2a78d6",
    "#eb6834",
    "#1baf7a",
    "#eda100",
    "#e87ba4",
    "#008300",
    "#6250d6",
    "#e34948",
]
PALETTE_DARK = [
    "#3987e5",
    "#d95926",
    "#199e70",
    "#c98500",
    "#d55181",
    "#008300",
    "#9085e9",
    "#e66767",
]
OTHER_COLOR = "#898781"

# Semantic globe anchors. The positions deliberately put technology (dark)
# next to AI and agriculture (teal/green) so the surface glows blend through a
# dark-blue -> teal -> green field as the globe rotates.
GLOBE_PARTITION_GEO = {
    "科技数码": (52, -150, "#1f2937", "#334155"),
    "人工智能": (22, -100, "#0f766e", "#14b8a6"),
    "三农": (-8, -55, "#16a34a", "#22c55e"),
    "美食": (-33, 0, "#65a30d", "#84cc16"),
    "动物": (-20, 40, "#15803d", "#4ade80"),
    "知识": (28, 55, "#b45309", "#f59e0b"),
    "游戏": (8, 110, "#2563eb", "#60a5fa"),
    "影视": (-25, 150, "#ea580c", "#fb923c"),
    "音乐": (-50, 95, "#db2777", "#f472b6"),
    "鬼畜": (55, 75, "#7c3aed", "#a78bfa"),
    "动画": (38, 175, "#8b5cf6", "#c4b5fd"),
    "舞蹈": (-55, 155, "#e11d48", "#fb7185"),
    "生活": (20, 20, "#0d9488", "#2dd4bf"),
    "生活兴趣": (12, 30, "#0f766e", "#2dd4bf"),
    "小剧场": (60, 20, "#f59e0b", "#fbbf24"),
    "娱乐": (-38, 60, "#f43f5e", "#fb7185"),
    "汽车": (0, -25, "#475569", "#94a3b8"),
    "户外潮流": (-48, -125, "#059669", "#34d399"),
    "旅游出行": (-45, -140, "#0d9488", "#2dd4bf"),
    "时尚美妆": (40, -70, "#c026d3", "#e879f9"),
    "其他": (0, 0, "#64748b", "#94a3b8"),
}


def _tag_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return []
    return [item.strip() for item in str(value).split("|") if item.strip()]


def build_pie_items(
    parent_stats: pd.DataFrame, top_n: int = 7, *, dark: bool = False
) -> list[dict[str, Any]]:
    """Top partitions plus an explicit Other slice."""
    if parent_stats.empty:
        return []
    palette = PALETTE_DARK if dark else PALETTE_LIGHT
    frame = parent_stats.sort_values("video_count", ascending=False)
    total = float(frame["video_count"].sum()) or 1.0
    top = frame.head(top_n)
    items: list[dict[str, Any]] = []
    for index, row in enumerate(top.itertuples(index=False)):
        items.append(
            {
                "name": str(row.category),
                "value": int(row.video_count),
                "pct": round(int(row.video_count) / total * 100, 1),
                "color": palette[index % len(palette)],
            }
        )
    remaining = frame.iloc[top_n:]
    if not remaining.empty:
        value = int(remaining["video_count"].sum())
        items.append(
            {
                "name": "其他",
                "value": value,
                "pct": round(value / total * 100, 1),
                "color": OTHER_COLOR,
            }
        )
    return items


def pie_chart_html(items: list[dict[str, Any]], *, dark: bool = False, height: int = 520) -> str:
    """SVG pie with a hover/focus leader-line callout and a legend."""
    surface = "#1a1a19" if dark else "#fcfcfb"
    ink = "#f0efec" if dark else "#0b0b0b"
    secondary = "#c3c2b7" if dark else "#52514e"
    muted = "#898781"
    line = "#c3c2b7" if dark else "#c3c2b7"
    data = json.dumps(items, ensure_ascii=False).replace("</", "<\\/")
    total = sum(item["value"] for item in items)
    template = r"""
    <style>html, body { margin:0; background:transparent; }</style>
    <div class="pie-shell">
      <div class="pie-head"><b>主分区占比</b><span>共 __TOTAL__ 条视频 · 悬停扇区查看名称和占比</span></div>
      <svg id="pie" viewBox="0 0 760 430" role="img" aria-label="视频分区饼图">
        <g id="sectors"></g>
        <g id="callout" style="display:none" pointer-events="none">
          <polyline id="leader" fill="none" stroke="__SECONDARY__" stroke-width="1.4"></polyline>
          <text id="leader-text" font-size="14" font-weight="650" fill="__INK__"
                stroke="__SURFACE__" stroke-width="4" paint-order="stroke"
                font-family="system-ui, 'Microsoft YaHei', sans-serif"></text>
        </g>
      </svg>
      <div class="legend" id="legend"></div>
    </div>
    <style>
      .pie-shell { font-family: system-ui, -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
        color: __INK__; background: transparent; width: 100%; }
      .pie-head { display:flex; justify-content:space-between; align-items:baseline; gap:12px;
        padding: 2px 4px 0; color: __SECONDARY__; font-size: 12px; }
      .pie-head b { color: __INK__; font-size: 14px; }
      #pie { display:block; width:100%; height:auto; overflow:visible; }
      .sector { cursor:pointer; transition: opacity .13s ease, transform .13s ease;
        transform-origin: 380px 215px; outline:none; }
      .sector:hover, .sector:focus { opacity:1 !important; }
      .sector.dim { opacity:.30 !important; }
      .sector.active { transform: scale(1.025); }
      .legend { display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:7px 14px;
        padding: 0 2px 4px; }
      .leg { display:flex; align-items:center; gap:7px; min-width:0; color:__SECONDARY__;
        font-size:12px; cursor:default; }
      .dot { width:9px; height:9px; border-radius:50%; flex:0 0 9px; }
      .leg-name { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
      .leg-val { margin-left:auto; color:__MUTED__; font-variant-numeric:tabular-nums; }
      @media (max-width: 640px) { .legend { grid-template-columns:repeat(2, minmax(0,1fr)); } }
    </style>
    <script>
      const ITEMS = __DATA__;
      const svg = document.getElementById('pie');
      const sectors = document.getElementById('sectors');
      const callout = document.getElementById('callout');
      const leader = document.getElementById('leader');
      const leaderText = document.getElementById('leader-text');
      const legend = document.getElementById('legend');
      const cx = 380, cy = 215, r = 128;
      let active = null;

      function point(angle, radius) {
        return { x: cx + Math.cos(angle) * radius, y: cy + Math.sin(angle) * radius };
      }
      function show(item, path) {
        active = path;
        document.querySelectorAll('.sector').forEach(p => {
          p.classList.toggle('dim', p !== path);
          p.classList.toggle('active', p === path);
        });
        const start = -Math.PI / 2 + (item.start / 100) * Math.PI * 2;
        const end = -Math.PI / 2 + (item.end / 100) * Math.PI * 2;
        const mid = (start + end) / 2;
        const p1 = point(mid, r + 2);
        const p2 = point(mid, r + 32);
        const side = Math.cos(mid) >= 0 ? 1 : -1;
        const x3 = p2.x + side * 58;
        const y3 = p2.y;
        leader.setAttribute('points', `${p1.x},${p1.y} ${p2.x},${p2.y} ${x3},${y3}`);
        leaderText.setAttribute('x', x3 + side * 5);
        leaderText.setAttribute('y', y3 + 4);
        leaderText.setAttribute('text-anchor', side > 0 ? 'start' : 'end');
        leaderText.textContent = `${item.name}  ${item.pct.toFixed(1)}%`;
        callout.style.display = '';
      }
      function hide() {
        document.querySelectorAll('.sector').forEach(p => p.classList.remove('dim', 'active'));
        callout.style.display = 'none';
        active = null;
      }
      let cumulative = 0;
      ITEMS.forEach((item) => {
        const pct = item.value / Math.max(1, ITEMS.reduce((s, x) => s + x.value, 0)) * 100;
        item.start = cumulative;
        item.end = cumulative + pct;
        cumulative += pct;
        const a0 = -Math.PI / 2 + (item.start / 100) * Math.PI * 2;
        const a1 = -Math.PI / 2 + (item.end / 100) * Math.PI * 2;
        const p0 = point(a0, r);
        const p1 = point(a1, r);
        const large = a1 - a0 > Math.PI ? 1 : 0;
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        if (pct >= 99.99) {
          path.setAttribute('d', `M${cx - r},${cy} a${r},${r} 0 1,0 ${r * 2},0 a${r},${r} 0 1,0 ${-r * 2},0`);
        } else {
          path.setAttribute('d', `M${cx},${cy} L${p0.x},${p0.y} A${r},${r} 0 ${large} 1 ${p1.x},${p1.y} Z`);
        }
        path.setAttribute('fill', item.color);
        path.setAttribute('stroke', '__SURFACE__');
        path.setAttribute('stroke-width', '2');
        path.setAttribute('class', 'sector');
        path.setAttribute('tabindex', '0');
        path.setAttribute('aria-label', `${item.name} ${item.pct.toFixed(1)}%`);
        path.addEventListener('mouseenter', () => show(item, path));
        path.addEventListener('focus', () => show(item, path));
        path.addEventListener('mouseleave', hide);
        path.addEventListener('blur', hide);
        sectors.appendChild(path);

        const row = document.createElement('div');
        row.className = 'leg';
        const dot = document.createElement('span');
        dot.className = 'dot';
        dot.style.background = item.color;
        const name = document.createElement('span');
        name.className = 'leg-name';
        name.textContent = item.name;
        const value = document.createElement('span');
        value.className = 'leg-val';
        value.textContent = `${item.pct.toFixed(1)}%`;
        row.append(dot, name, value);
        row.addEventListener('mouseenter', () => show(item, path));
        row.addEventListener('mouseleave', hide);
        legend.appendChild(row);
      });
    </script>
    """
    return (
        template.replace("__DATA__", data)
        .replace("__TOTAL__", str(total))
        .replace("__SURFACE__", surface)
        .replace("__INK__", ink)
        .replace("__SECONDARY__", secondary)
        .replace("__MUTED__", muted)
    )


def _ordered_tags(tags: list[str], cooccurrence: Counter[tuple[str, str]], counts: Counter[str]) -> list[str]:
    """Greedy chain: keep co-occurring tags adjacent in the sector."""
    remaining = list(dict.fromkeys(tags))
    if not remaining:
        return []
    remaining.sort(key=lambda tag: (-counts[tag], tag))
    ordered = [remaining.pop(0)]
    while remaining:
        last = ordered[-1]
        best = max(
            remaining,
            key=lambda tag: (
                cooccurrence.get(tuple(sorted((last, tag))), 0),
                counts[tag],
            ),
        )
        remaining.remove(best)
        ordered.append(best)
    return ordered


def build_wordcloud_data(
    videos: pd.DataFrame,
    *,
    dark: bool = False,
    max_partitions: int = 7,
    tags_per_partition: int = 6,
) -> dict[str, Any]:
    """Aggregate partitions and tags into a semantic radial layout.

    Partition names are the large anchors. Tags are assigned to their strongest
    partition, ordered by co-occurrence, and placed in a shared circular field.
    """
    if videos.empty:
        return {"nodes": [], "edges": [], "partitions": [], "total_videos": 0}
    palette = PALETTE_DARK if dark else PALETTE_LIGHT
    records = videos.to_dict("records")
    partition_counts: Counter[str] = Counter()
    tag_counts: Counter[str] = Counter()
    tag_partition: dict[str, Counter[str]] = defaultdict(Counter)
    video_tags: list[tuple[str, set[str]]] = []

    for row in records:
        partition = str(row.get("category_parent") or "其他")
        tags = _tag_list(row.get("tags"))
        partition_counts[partition] += 1
        unique = set(tags)
        for tag in unique:
            tag_counts[tag] += 1
            tag_partition[tag][partition] += 1
        video_tags.append((partition, unique))

    selected_partitions = [name for name, _ in partition_counts.most_common(max_partitions)]
    partition_index = {name: index for index, name in enumerate(selected_partitions)}
    total_partition_count = sum(partition_counts[name] for name in selected_partitions) or 1
    assigned: dict[str, list[str]] = defaultdict(list)
    for tag, per_partition in tag_partition.items():
        candidates = [(count, name) for name, count in per_partition.items() if name in partition_index]
        if not candidates:
            continue
        _, partition = max(candidates)
        assigned[partition].append(tag)

    selected_tags: list[str] = []
    selected_by_partition: dict[str, list[str]] = {}
    for partition in selected_partitions:
        tags = sorted(assigned[partition], key=lambda tag: (-tag_counts[tag], tag))[:tags_per_partition]
        selected_by_partition[partition] = tags
        selected_tags.extend(tags)
    selected_set = set(selected_tags)

    cooccurrence: Counter[tuple[str, str]] = Counter()
    for _, tags in video_tags:
        chosen = sorted(tags & selected_set)
        for i, first in enumerate(chosen):
            for second in chosen[i + 1 :]:
                cooccurrence[tuple(sorted((first, second)))] += 1

    gap = 0.075
    available = math.pi * 2 - gap * len(selected_partitions)
    nodes: list[dict[str, Any]] = []
    partition_meta: list[dict[str, Any]] = []
    cursor = -math.pi / 2
    max_partition = max(partition_counts[name] for name in selected_partitions)
    max_tag = max((tag_counts[tag] for tag in selected_tags), default=1)

    for index, partition in enumerate(selected_partitions):
        count = partition_counts[partition]
        span = available * count / total_partition_count
        start = cursor
        center = start + span / 2
        color = palette[index % len(palette)]
        nodes.append(
            {
                "id": f"partition-{index}",
                "label": partition,
                "type": "partition",
                "partition": partition,
                "value": int(count),
                "angle": center,
                "radius": 70,
                "fontSize": 24 + 7 * (count / max_partition) ** 0.5,
                "color": color,
            }
        )
        partition_meta.append(
            {"name": partition, "count": int(count), "color": color, "angle": center}
        )
        ordered = _ordered_tags(
            selected_by_partition[partition], cooccurrence, tag_counts
        )
        inner_start = start + span * 0.13
        inner_span = max(0.08, span * 0.74)
        for tag_index, tag in enumerate(ordered):
            ratio = tag_counts[tag] / max_tag
            angle = inner_start + inner_span * (tag_index + 0.5) / max(1, len(ordered))
            radius = 132 + 45 * (tag_index % 3) + 28 * (1 - ratio) + (tag_index // 3) * 11
            nodes.append(
                {
                    "id": f"tag-{index}-{tag_index}",
                    "label": tag,
                    "type": "tag",
                    "partition": partition,
                    "value": int(tag_counts[tag]),
                    "angle": angle,
                    "radius": radius,
                    "fontSize": 11 + 13 * ratio**0.7,
                    "color": color,
                }
            )
        cursor += span + gap

    id_by_tag = {
        node["label"]: node["id"] for node in nodes if node["type"] == "tag"
    }
    edges = []
    for (first, second), weight in cooccurrence.most_common(90):
        if first in id_by_tag and second in id_by_tag and weight >= 1:
            edges.append([id_by_tag[first], id_by_tag[second], int(weight)])
    return {
        "nodes": nodes,
        "edges": edges,
        "partitions": partition_meta,
        "total_videos": len(records),
        "selected_tags": selected_tags,
    }


def _sphere(lat_deg: float, lon_deg: float) -> tuple[float, float, float]:
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    cos_lat = math.cos(lat)
    return (
        cos_lat * math.sin(lon),
        math.sin(lat),
        cos_lat * math.cos(lon),
    )


def _normalize(vector: tuple[float, float, float]) -> tuple[float, float, float]:
    length = math.sqrt(sum(value * value for value in vector)) or 1.0
    return tuple(value / length for value in vector)  # type: ignore[return-value]


def _cross(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


_GLOBE_SLOTS = (
    (-22, -160),
    (26, -118),
    (-34, -72),
    (12, -28),
    (36, 18),
    (-15, 62),
    (22, 108),
    (-32, 152),
)

_CHILD_CANON = {
    "游戏": (
        (r"独立|单机", "独立游戏"),
        (r"二次元|手游", "二次元游戏"),
        (r"MOBA|英雄联盟|电竞", "MOBA游戏"),
        (r"RPG|角色扮演", "RPG游戏"),
        (r"角色演示|角色", "角色演示"),
        (r"实况", "游戏实况"),
        (r"解说", "游戏解说"),
        (r"攻略", "游戏攻略"),
        (r"PV|预告", "游戏PV"),
        (r"沙盒|我的世界", "沙盒游戏"),
        (r"休闲|小游戏", "休闲游戏"),
        (r"射击", "射击游戏"),
        (r"竞速|赛车", "竞速游戏"),
        (r"赛事", "电竞赛事"),
    ),
    "影视": (
        (r"AI", "AI短片"),
        (r"解说", "影视解说"),
        (r"剪辑", "影视剪辑"),
        (r"剧情", "剧情短片"),
        (r"混剪", "影视混剪"),
        (r"预告", "影视预告"),
    ),
    "知识": (
        (r"历史", "历史解读"),
        (r"科普", "知识科普"),
        (r"访谈|对话", "深度访谈"),
        (r"社会", "社会观察"),
        (r"科学", "科学科普"),
    ),
    "音乐": (
        (r"翻唱", "音乐翻唱"),
        (r"现场", "音乐现场"),
        (r"MV", "音乐MV"),
        (r"二创|混剪", "音乐二创"),
        (r"演奏|钢琴|吉他", "乐器演奏"),
        (r"古风", "古风音乐"),
    ),
    "美食": (
        (r"制作|教程", "美食制作"),
        (r"探店", "美食探店"),
        (r"记录", "美食记录"),
        (r"吃|下饭", "美食体验"),
    ),
    "动画": (
        (r"手书|手搓", "手书动画"),
        (r"原创", "原创动画"),
        (r"同人", "同人动画"),
        (r"角色", "角色演绎"),
        (r"AI", "AI动画"),
    ),
    "小剧场": (
        (r"搞笑", "搞笑短剧"),
        (r"剧情", "剧情演绎"),
        (r"情景", "情景短剧"),
        (r"配音", "配音短剧"),
    ),
    "鬼畜": (
        (r"调教", "鬼畜调教"),
        (r"音MAD|MAD", "音MAD"),
        (r"混剪", "鬼畜混剪"),
        (r"鬼畜", "鬼畜内容"),
    ),
    "舞蹈": (
        (r"翻跳", "舞蹈翻跳"),
        (r"编舞", "编舞设计"),
        (r"双人", "双人舞"),
        (r"街舞", "街舞"),
        (r"K-Pop|韩舞", "韩舞"),
    ),
}


def _canonical_child(parent: str, tag: str) -> str:
    for pattern, label in _CHILD_CANON.get(parent, ()):
        if re.search(pattern, tag, re.IGNORECASE):
            return label
    return tag


def build_globe_data(
    videos: pd.DataFrame,
    *,
    max_partitions: int = 8,
    tags_per_partition: int = 15,
) -> dict[str, Any]:
    """Build a two-level (partition -> detail tag) spherical hierarchy.

    Parents are the big partition labels shown when zoomed out. Children are
    concise tags packed around the parent and revealed as the user zooms in.
    """
    if videos.empty:
        return {"nodes": [], "partitions": [], "total_videos": 0}
    records = videos.to_dict("records")
    partition_counts: Counter[str] = Counter()
    child_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for row in records:
        partition = str(row.get("category_parent") or "其他")
        partition_counts[partition] += 1
        seen = set()
        for tag in _tag_list(row.get("tags")):
            child = _canonical_child(partition, tag)
            if child and child not in seen:
                seen.add(child)
                child_counts[partition][child] += 1

    selected = [name for name, _ in partition_counts.most_common(max_partitions)]
    nodes: list[dict[str, Any]] = []
    partitions: list[dict[str, Any]] = []
    max_partition = max((partition_counts[name] for name in selected), default=1)
    for p_index, partition in enumerate(selected):
        geo = GLOBE_PARTITION_GEO.get(partition)
        if geo is None:
            color = PALETTE_LIGHT[p_index % len(PALETTE_LIGHT)]
            glow = color
        else:
            _, _, color, glow = geo
        lat, lon = _GLOBE_SLOTS[p_index % len(_GLOBE_SLOTS)]
        center = _normalize(_sphere(lat, lon))
        up = (0.0, 1.0, 0.0)
        tangent = _cross(up, center)
        if math.sqrt(sum(v * v for v in tangent)) < 0.01:
            tangent = (1.0, 0.0, 0.0)
        tangent = _normalize(tangent)
        bitangent = _normalize(_cross(center, tangent))
        count = partition_counts[partition]
        parent_id = f"p-{p_index}"
        parent_font = 12.5 + 2.0 * (count / max_partition) ** 0.5
        parent_diameter = min(92, 62 + 18 * (count / max_partition))
        nodes.append(
            {
                "id": parent_id,
                "label": partition,
                "type": "parent",
                "partition": partition,
                "value": int(count),
                "pos": list(center),
                "parentPos": list(center),
                "color": color,
                "accent": glow,
                "fontSize": parent_font,
                "diameter": round(parent_diameter, 1),
                "radius": round(parent_diameter / 2, 1),
            }
        )
        partitions.append(
            {
                "name": partition,
                "value": int(count),
                "color": color,
                "glowColor": glow,
                "center": list(center),
            }
        )

        children = child_counts[partition].most_common(tags_per_partition)
        if not children:
            continue
        max_child = max(value for _, value in children)
        for c_index, (label, value) in enumerate(children):
            theta = 2 * math.pi * c_index / max(1, len(children)) + p_index * 0.63
            offset = 0.55 + 0.55 * (1 - value / max_child) + (c_index % 2) * 0.025
            pos = (
                math.cos(offset) * center[0]
                + math.sin(offset) * (math.cos(theta) * tangent[0] + math.sin(theta) * bitangent[0]),
                math.cos(offset) * center[1]
                + math.sin(offset) * (math.cos(theta) * tangent[1] + math.sin(theta) * bitangent[1]),
                math.cos(offset) * center[2]
                + math.sin(offset) * (math.cos(theta) * tangent[2] + math.sin(theta) * bitangent[2]),
            )
            pos = _normalize(pos)
            ratio = value / max_child
            font_size = 7.0 + 2.6 * ratio**0.65
            diameter = min(50, max(24, 10 + len(label) * font_size * 0.46 + font_size * 1.2))
            nodes.append(
                {
                    "id": f"c-{p_index}-{c_index}",
                    "label": label,
                    "type": "child",
                    "parent": parent_id,
                    "childRank": c_index,
                    "partition": partition,
                    "value": int(value),
                    "pos": list(pos),
                    "parentPos": list(center),
                    "color": color,
                    "accent": glow,
                    "fontSize": font_size,
                    "diameter": round(diameter, 1),
                    "radius": round(diameter / 2, 1),
                }
            )

    # Spread all child tags over a global Fibonacci sphere. This keeps the
    # surface covered at every zoom instead of concentrating each partition in
    # a small cluster around its parent bubble.
    children = [node for node in nodes if node["type"] == "child"]
    golden = math.pi * (3 - math.sqrt(5))
    for index, node in enumerate(children):
        y = 1 - 2 * (index + 0.5) / max(1, len(children))
        radius = math.sqrt(max(0.0, 1 - y * y))
        phi = index * golden
        node["pos"] = [math.cos(phi) * radius, y, math.sin(phi) * radius]

    parent_nodes = {node["id"]: node for node in nodes if node["type"] == "parent"}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for node in children:
        grouped[node["parent"]].append(node)
    for parent_id, group in grouped.items():
        center = _normalize(
            (
                sum(node["pos"][0] for node in group),
                sum(node["pos"][1] for node in group),
                sum(node["pos"][2] for node in group),
            )
        )
        parent = parent_nodes.get(parent_id)
        if parent is not None:
            parent["pos"] = list(center)
            parent["parentPos"] = list(center)
        for node in group:
            node["parentPos"] = list(center)
    for item in partitions:
        group = grouped.get(
            next(
                (node["id"] for node in parent_nodes.values() if node["partition"] == item["name"]),
                "",
            ),
            [],
        )
        if group:
            center = _normalize(
                (
                    sum(node["pos"][0] for node in group),
                    sum(node["pos"][1] for node in group),
                    sum(node["pos"][2] for node in group),
                )
            )
            item["center"] = list(center)

    def rotated_z(pos: list[float], yaw: float, pitch: float) -> float:
        x = pos[0] * math.cos(yaw) + pos[2] * math.sin(yaw)
        z0 = -pos[0] * math.sin(yaw) + pos[2] * math.cos(yaw)
        return pos[1] * math.sin(pitch) + z0 * math.cos(pitch)

    best_yaw = 0.35
    best_balance = -1
    for degree in range(-180, 180, 5):
        candidate = math.radians(degree)
        children = [node for node in nodes if node["type"] == "child"]
        front = sum(1 for node in children if rotated_z(node["pos"], candidate, -0.14) > 0.015)
        balance = min(front, len(children) - front)
        if balance > best_balance:
            best_balance = balance
            best_yaw = candidate
    return {
        "nodes": nodes,
        "partitions": partitions,
        "total_videos": len(records),
        "max_partition": int(max_partition),
        "initialYaw": best_yaw,
    }


def globe_html(data: dict[str, Any], *, height: int = 640) -> str:
    """Two synchronized orthographic globe views with draggable tag bubbles."""
    if not data.get("nodes"):
        return "<div style='padding:24px;color:#94a3b8'>当前筛选下没有可展示的标签。</div>"
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    template = r"""
    <div class="geo-shell" translate="no">
      <div class="geo-head">
        <div><b>词云</b><span>拖拽空白旋转 · 滚轮/按钮缩放 · 双击词球把视角转到它</span></div>
        <div class="geo-tools">
          <span class="geo-count">__COUNT__ 条视频 · __TAG_COUNT__ 个代表标签 · 正反同步</span>
          <div class="zoom-box">
            <button id="zoom-out" type="button" aria-label="缩小">−</button>
            <span id="zoom-val">100%</span>
            <button id="zoom-in" type="button" aria-label="放大">+</button>
            <button id="zoom-reset" type="button" aria-label="重置缩放">⟲</button>
          </div>
        </div>
      </div>
      <div class="views">
        <div class="globe-card">
          <div class="globe-label">正面 <span>FRONT</span></div>
          <div class="globe" data-view="front"><canvas></canvas><div class="tag-layer"></div></div>
        </div>
        <div class="globe-card">
          <div class="globe-label">背面 <span>BACK</span></div>
          <div class="globe" data-view="back"><canvas></canvas><div class="tag-layer"></div></div>
        </div>
      </div>
      <div class="geo-legend" id="geo-legend"></div>
      <div class="geo-foot">
        <span>词球大小 = 覆盖视频数</span><span>缩小合并分区 · 放大展开细分</span><span>固定球面 · 正反联动</span>
      </div>
      <div id="geo-error" style="display:none;color:#fca5a5;font-size:10px;text-align:center;padding-top:6px"></div>
    </div>
    <style>
      html, body { margin:0; background:#05070d; }
      .geo-shell { box-sizing:border-box; width:100%; padding:0 6px 4px; color:#e5e7eb;
        font-family: system-ui, -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif; }
      .geo-head { display:flex; justify-content:space-between; align-items:flex-start; gap:18px;
        padding:0 8px 12px; color:#94a3b8; font-size:12px; }
      .geo-head b { display:block; color:#f8fafc; font-size:14px; margin-bottom:3px; }
      .geo-count { white-space:nowrap; color:#64748b; }
      .geo-tools { display:flex; align-items:center; gap:12px; flex-wrap:wrap; justify-content:flex-end; }
      .zoom-box { display:flex; align-items:center; gap:2px; border:1px solid #263244;
        border-radius:8px; padding:2px; background:#0a0f18; color:#cbd5e1; }
      .zoom-box button { background:transparent; border:0; color:#cbd5e1; width:24px; height:24px;
        border-radius:5px; cursor:pointer; font-size:15px; line-height:1; }
      .zoom-box button:hover { background:#172033; color:#fff; }
      .zoom-box span { min-width:42px; text-align:center; font-size:10px; color:#94a3b8;
        font-variant-numeric:tabular-nums; }
      .views { display:flex; justify-content:center; align-items:flex-start; gap:34px; flex-wrap:wrap; }
      .globe-card { width:min(450px, 92vw); }
      .globe-label { color:#cbd5e1; font-size:12px; font-weight:650; letter-spacing:.08em;
        text-align:center; margin-bottom:7px; }
      .globe-label span { color:#64748b; font-weight:500; font-size:10px; margin-left:5px; }
      .globe { position:relative; width:100%; aspect-ratio:1 / 1; border-radius:50%;
        overflow:hidden; touch-action:none; cursor:grab; background:#05070d;
        box-shadow:0 0 42px rgba(15,118,110,.13), inset 0 0 30px rgba(0,0,0,.8); }
      .globe:active { cursor:grabbing; }
      .globe canvas { position:absolute; inset:0; width:100%; height:100%; }
      .tag-layer { position:absolute; inset:0; pointer-events:none; }
      .tag { position:absolute; display:flex; align-items:center; justify-content:center;
        border-radius:50%; box-sizing:border-box; padding:5px; text-align:center;
        color:#fff; font-weight:650; line-height:1.06; letter-spacing:.01em;
        text-shadow:0 1px 4px rgba(0,0,0,.72); border:1px solid rgba(255,255,255,.28);
        box-shadow:0 4px 18px rgba(0,0,0,.35), inset 0 0 14px rgba(255,255,255,.08);
        pointer-events:auto; cursor:default; user-select:none; transform:translate(-50%,-50%);
        will-change:left,top; overflow:hidden; word-break:break-all; }
      .tag.parent { border-width:2px; font-weight:800; letter-spacing:.02em; }
      .tag:hover { filter:brightness(1.16); }
      .tag.dragging { cursor:grabbing; filter:brightness(1.25); }
      .tag.echo { opacity:.30; filter:saturate(.65); border-style:dashed; pointer-events:none; }
      .tag.focused { box-shadow:0 0 0 3px rgba(250,204,21,.55), 0 0 26px rgba(250,204,21,.35); }
      .geo-legend { display:flex; justify-content:center; align-items:center; gap:14px;
        flex-wrap:wrap; padding:12px 8px 0; color:#94a3b8; font-size:11px; }
      .geo-legend span { display:inline-flex; align-items:center; gap:5px; white-space:nowrap; }
      .geo-legend i { width:8px; height:8px; border-radius:50%; display:inline-block; }
      .geo-foot { display:flex; justify-content:center; gap:18px; flex-wrap:wrap;
        padding:8px 4px 0; color:#64748b; font-size:11px; }
      @media (max-width:720px) { .views { gap:20px; } .globe-card { width:min(340px, 88vw); } }
    </style>
    <script>
      const DATA = __DATA__;
      const DPR = window.devicePixelRatio || 1;
      const TAU = Math.PI * 2;
      const views = {};
      document.querySelectorAll('.globe').forEach((el) => {
        const view = el.dataset.view;
        const canvas = el.querySelector('canvas');
        const layer = el.querySelector('.tag-layer');
        views[view] = { el, canvas, layer, size: el.clientWidth, R: el.clientWidth * 0.42 };
      });

      const nodes = DATA.nodes.map(n => ({
        ...n,
        pos: { x:n.pos[0], y:n.pos[1], z:n.pos[2] },
        els: {},
        dragging: false,
        dragSpeed: 0
      }));
      [...nodes].sort((a,b)=>b.value-a.value).forEach((n,i)=>{ n.rank=i; });
      const byId = Object.fromEntries(nodes.map(n => [n.id, n]));
      const partitions = DATA.partitions;
      const legend = document.getElementById('geo-legend');
      for (const p of partitions) {
        const item=document.createElement('span');
        const dot=document.createElement('i');
        dot.style.background=p.color;
        item.append(dot, document.createTextNode(`${p.name} ${p.value}`));
        legend.appendChild(item);
      }

      let yaw = (typeof DATA.initialYaw === 'number' ? DATA.initialYaw : 0.35), pitch = -0.14;
      let autoUntil = 0, focus = null;
      let rotateDrag = null;
      let lastInteract = 0;
      let zoom = 0.80, targetZoom = 1.0;
      let dragNode = null, dragView = null;
      const ZOOM_MIN = 0.78, ZOOM_MAX = 1.25;
      const zoomLabel = document.getElementById('zoom-val');

      function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
      function norm(p) {
        const m = Math.hypot(p.x,p.y,p.z) || 1;
        return {x:p.x/m, y:p.y/m, z:p.z/m};
      }
      function rot(p) {
        const cy=Math.cos(yaw), sy=Math.sin(yaw);
        const x = p.x*cy + p.z*sy;
        const z0 = -p.x*sy + p.z*cy;
        const cp=Math.cos(pitch), sp=Math.sin(pitch);
        return {x, y:p.y*cp - z0*sp, z:p.y*sp + z0*cp};
      }
      function invRot(p) {
        const cp=Math.cos(pitch), sp=Math.sin(pitch);
        const y1 = p.y*cp + p.z*sp;
        const z1 = -p.y*sp + p.z*cp;
        const cy=Math.cos(yaw), sy=Math.sin(yaw);
        return {
          x: p.x*cy - z1*sy,
          y: y1,
          z: p.x*sy + z1*cy
        };
      }
      function project(p, view) {
        const r = rot(p);
        const depth = view === 'front' ? r.z : -r.z;
        const R = views[view].R;
        const cx = views[view].size / 2, cy = views[view].size / 2;
        return {
          x: cx + (view === 'front' ? r.x : -r.x) * R,
          y: cy - r.y * R,
          depth,
          r
        };
      }

      function syncSizes() {
        for (const view of ['front','back']) {
          const v=views[view];
          const size=v.el.clientWidth;
          if (size > 10 && size !== v.size) {
            v.size=size;
          }
          if (v.size > 10) v.R = v.size * 0.39 * zoom;
        }
      }

      function drawGlobe(view) {
        const v = views[view];
        const canvas = v.canvas;
        const size = v.size;
        if (!size) return;
        if (canvas.width !== Math.round(size*DPR)) {
          canvas.width = Math.round(size*DPR);
          canvas.height = Math.round(size*DPR);
        }
        const ctx = canvas.getContext('2d');
        ctx.setTransform(DPR,0,0,DPR,0,0);
        ctx.clearRect(0,0,size,size);
        const cx=size/2, cy=size/2, R=v.R;
        ctx.save();
        ctx.beginPath(); ctx.arc(cx,cy,R,0,TAU); ctx.clip();
        const base = ctx.createRadialGradient(cx-R*.45,cy-R*.48,R*.1,cx,cy,R);
        base.addColorStop(0,'#101b2b');
        base.addColorStop(.38,'#08131d');
        base.addColorStop(.76,'#0b211d');
        base.addColorStop(1,'#03080c');
        ctx.fillStyle=base; ctx.fillRect(0,0,size,size);
        const field=ctx.createLinearGradient(cx-R*.75,cy-R*.62,cx+R*.42,cy+R*.78);
        field.addColorStop(0,'rgba(4,8,18,.58)');
        field.addColorStop(.42,'rgba(10,55,55,.22)');
        field.addColorStop(.74,'rgba(20,83,45,.28)');
        field.addColorStop(1,'rgba(4,38,18,.38)');
        ctx.fillStyle=field; ctx.fillRect(0,0,size,size);
        ctx.globalCompositeOperation='lighter';
        for (const p of partitions) {
          if (!p.center) continue;
          const r = rot({x:p.center[0], y:p.center[1], z:p.center[2]});
          if ((view === 'front' ? r.z : -r.z) <= -0.02) continue;
          const px = cx + (view === 'front' ? r.x : -r.x) * R;
          const py = cy - r.y * R;
          const grad = ctx.createRadialGradient(px,py,2,px,py,R*.62);
          grad.addColorStop(0, p.glowColor + '99');
          grad.addColorStop(.55, p.glowColor + '38');
          grad.addColorStop(1, p.glowColor + '00');
          ctx.fillStyle=grad;
          ctx.beginPath(); ctx.arc(px,py,R*.62,0,TAU); ctx.fill();
        }
        ctx.globalCompositeOperation='source-over';
        ctx.strokeStyle='rgba(148,163,184,.12)';
        ctx.lineWidth=1;
        for (let lat=-60; lat<=60; lat+=30) {
          let started=false;
          ctx.beginPath();
          for (let lon=0; lon<=360; lon+=6) {
            const pr=project({x:Math.cos(lat*Math.PI/180)*Math.sin(lon*Math.PI/180),
              y:Math.sin(lat*Math.PI/180), z:Math.cos(lat*Math.PI/180)*Math.cos(lon*Math.PI/180)}, view);
            if (pr.depth > 0.01) { if(!started){ctx.moveTo(pr.x,pr.y);started=true;} else ctx.lineTo(pr.x,pr.y); }
            else started=false;
          }
          ctx.stroke();
        }
        for (let lon=0; lon<360; lon+=30) {
          let started=false;
          ctx.beginPath();
          for (let lat=-90; lat<=90; lat+=4) {
            const pr=project({x:Math.cos(lat*Math.PI/180)*Math.sin(lon*Math.PI/180),
              y:Math.sin(lat*Math.PI/180), z:Math.cos(lat*Math.PI/180)*Math.cos(lon*Math.PI/180)}, view);
            if (pr.depth > 0.01) { if(!started){ctx.moveTo(pr.x,pr.y);started=true;} else ctx.lineTo(pr.x,pr.y); }
            else started=false;
          }
          ctx.stroke();
        }
        ctx.restore();
        ctx.beginPath(); ctx.arc(cx,cy,R,0,TAU);
        ctx.strokeStyle='rgba(148,163,184,.35)'; ctx.lineWidth=1; ctx.stroke();
        const rim=ctx.createRadialGradient(cx,cy,R*.92,cx,cy,R*1.04);
        rim.addColorStop(0,'rgba(45,212,191,0)');
        rim.addColorStop(.7,'rgba(45,212,191,.09)');
        rim.addColorStop(1,'rgba(45,212,191,0)');
        ctx.fillStyle=rim; ctx.beginPath(); ctx.arc(cx,cy,R*1.04,0,TAU); ctx.fill();
      }

      function ensureElements() {
        for (const n of nodes) {
          for (const view of ['front','back']) {
            const el=document.createElement('div');
            el.className='tag ' + (n.type === 'parent' ? 'parent' : 'child');
            el.textContent=n.label;
            el.title=`${n.label} · ${n.value} 条视频`;
            el.style.width=n.diameter+'px'; el.style.height=n.diameter+'px';
            el.style.fontSize=n.fontSize+'px';
            el.style.background=n.color;
            el.style.borderColor=n.accent;
            el.style.boxShadow=`0 4px 18px rgba(0,0,0,.35), inset 0 0 14px ${n.accent}33`;
            el.addEventListener('pointerdown', e => e.stopPropagation());
            el.addEventListener('dblclick', e => {
              e.stopPropagation();
              focusOn(n,view);
            });
            views[view].layer.appendChild(el);
            n.els[view]=el;
          }
        }
      }

      function startWordDrag(e,n,view,el) {
        e.stopPropagation(); e.preventDefault();
        dragNode=n; dragView=view; n.dragging=true;
        n.dragSpeed=0;
        el.classList.add('dragging');
        try { el.setPointerCapture(e.pointerId); } catch(_) {}
        lastInteract=Date.now();
        const move = (ev) => {
          if (!dragNode || dragNode !== n) return;
          const v=views[view];
          const rect=v.el.getBoundingClientRect();
          let u=(ev.clientX-rect.left-v.size/2)/v.R;
          let vv=(v.size/2-(ev.clientY-rect.top))/v.R;
          const radius=Math.hypot(u,vv);
          if (radius>0.92) { u=u/radius*0.92; vv=vv/radius*0.92; }
          const z=Math.sqrt(Math.max(0.04,1-u*u-vv*vv))*(view==='front'?1:-1);
          const camera={x:view==='front'?u:-u, y:vv, z};
          const world=norm(invRot(camera));
          const dx=world.x-n.pos.x, dy=world.y-n.pos.y, dz=world.z-n.pos.z;
          n.pos=world;
          n.dragSpeed=clamp(Math.hypot(dx,dy,dz)*18,0,1);
          lastInteract=Date.now();
          ev.preventDefault();
        };
        const up = (ev) => {
          n.dragging=false; dragNode=null; dragView=null;
          el.classList.remove('dragging');
          try { el.releasePointerCapture(ev.pointerId); } catch(_) {}
          el.removeEventListener('pointermove',move);
          el.removeEventListener('pointerup',up);
          el.removeEventListener('pointercancel',up);
          lastInteract=Date.now();
        };
        el.addEventListener('pointermove',move);
        el.addEventListener('pointerup',up);
        el.addEventListener('pointercancel',up);
      }

      function focusOn(n,view) {
        const p=n.pos;
        let targetYaw, targetPitch;
        if (view === 'front') {
          targetYaw=Math.atan2(-p.x,p.z);
          targetPitch=Math.asin(clamp(p.y,-1,1));
        } else {
          targetYaw=Math.atan2(p.x,-p.z);
          targetPitch=-Math.asin(clamp(p.y,-1,1));
        }
        let dy=targetYaw-yaw; dy=Math.atan2(Math.sin(dy),Math.cos(dy));
        focus={start:performance.now(), fromYaw:yaw, fromPitch:pitch,
          toYaw:yaw+dy, toPitch:targetPitch, node:n};
        autoUntil=performance.now()+5000;
        lastInteract=Date.now();
      }

      window.addEventListener('pointerup', () => {
        if (dragNode) {
          dragNode.dragging = false;
          dragNode = null;
          dragView = null;
          document.querySelectorAll('.tag.dragging').forEach(e => e.classList.remove('dragging'));
          lastInteract = Date.now();
        }
      });
      window.addEventListener('pointercancel', () => {
        if (dragNode) {
          dragNode.dragging = false;
          dragNode = null;
          dragView = null;
          document.querySelectorAll('.tag.dragging').forEach(e => e.classList.remove('dragging'));
          lastInteract = Date.now();
        }
      });

      function startRotate(e,view) {
        if (e.target.closest('.tag')) return;
        e.preventDefault();
        rotateDrag={view, x:e.clientX, y:e.clientY};
        lastInteract=Date.now();
        const el=views[view].el;
        try { el.setPointerCapture(e.pointerId); } catch(_) {}
        const move=(ev)=>{
          if(!rotateDrag||rotateDrag.view!==view) return;
          const dx=ev.clientX-rotateDrag.x, dy=ev.clientY-rotateDrag.y;
          yaw += dx*0.006;
          pitch = clamp(pitch - dy*0.006,-1.2,1.2);
          rotateDrag.x=ev.clientX; rotateDrag.y=ev.clientY;
          lastInteract=Date.now();
        };
        const up=(ev)=>{
          rotateDrag=null;
          try { el.releasePointerCapture(ev.pointerId); } catch(_) {}
          el.removeEventListener('pointermove',move);
          el.removeEventListener('pointerup',up);
          el.removeEventListener('pointercancel',up);
          lastInteract=Date.now();
        };
        el.addEventListener('pointermove',move);
        el.addEventListener('pointerup',up);
        el.addEventListener('pointercancel',up);
      }

      function softCollide(multiplier = 1) {
        const sphereR = views.front.R || 172;
        for (let iteration=0; iteration<3; iteration++) {
          for (let i=0;i<nodes.length;i++) {
            for (let j=i+1;j<nodes.length;j++) {
              const a=nodes[i], b=nodes[j];
              const dot=clamp(a.pos.x*b.pos.x+a.pos.y*b.pos.y+a.pos.z*b.pos.z,-1,1);
              const angle=Math.acos(dot);
              const minAngle=((a.radius+b.radius)/sphereR)*0.99;
              if (angle <= 0.0001 || angle >= minAngle) continue;
              const overlap=minAngle-angle;
              let tx=b.pos.x-a.pos.x*dot, ty=b.pos.y-a.pos.y*dot, tz=b.pos.z-a.pos.z*dot;
              const tl=Math.hypot(tx,ty,tz)||1; tx/=tl; ty/=tl; tz/=tl;
              let factor=0.12*multiplier;
              if (a===dragNode) factor=clamp(0.18 + a.dragSpeed*.9,.18,.95);
              if (b===dragNode) factor=clamp(0.18 + b.dragSpeed*.9,.18,.95);
              if (a!==dragNode) { a.pos=norm({x:a.pos.x+tx*overlap*factor,y:a.pos.y+ty*overlap*factor,z:a.pos.z+tz*overlap*factor}); }
              if (b!==dragNode) { b.pos=norm({x:b.pos.x-tx*overlap*factor,y:b.pos.y-ty*overlap*factor,z:b.pos.z-tz*overlap*factor}); }
            }
          }
        }
      }

      function smoothstep(edge0, edge1, value) {
        const t=clamp((value-edge0)/(edge1-edge0),0,1);
        return t*t*(3-2*t);
      }

      function updateDOM() {
        const detail=smoothstep(0.82, 1.12, zoom);
        const posT=0.78 + 0.22 * detail;
        const allowedChildren=10 + Math.ceil(5 * detail);
        for (const n of nodes) {
          const parent = n.type === 'parent';
          const pos = parent
            ? {x:n.pos.x,y:n.pos.y,z:n.pos.z}
            : norm({
                x:n.parentPos[0]*(1-posT) + n.pos.x*posT,
                y:n.parentPos[1]*(1-posT) + n.pos.y*posT,
                z:n.parentPos[2]*(1-posT) + n.pos.z*posT
              });
          const scale = parent ? (1 - 0.30*detail) : (0.72 + 0.28*detail);
          const opacity = parent
            ? Math.max(0, 1 - detail*1.6)
            : Math.min(1, 0.84 + detail*0.16);
          for (const view of ['front','back']) {
            const el=n.els[view];
            if (!el) continue;
            const p=project(pos,view);
            const childVisible = !parent && n.childRank < allowedChildren;
            const visible = p.depth > 0.015 && (parent ? detail < 0.98 : childVisible);
            el.style.display=visible?'flex':'none';
            if (!visible) continue;
            el.style.left=p.x+'px'; el.style.top=p.y+'px';
            el.style.width=(n.diameter*scale)+'px';
            el.style.height=(n.diameter*scale)+'px';
            el.style.fontSize=(n.fontSize*(parent ? 1 : (0.86+0.14*detail)))+'px';
            el.style.opacity=opacity.toFixed(2);
            el.style.zIndex=Math.round((p.depth+1)*1000);
            el.classList.toggle('focused', focus && focus.node===n);
          }
        }
      }

      function tick(now) {
        try {
          if (Math.abs(targetZoom-zoom) > 0.001) {
            zoom += (targetZoom-zoom)*0.18;
            if (zoomLabel) zoomLabel.textContent = Math.round(zoom*100) + '%';
          }
          syncSizes();
          if (focus) {
            const t=clamp((now-focus.start)/650,0,1);
            const e=1-Math.pow(1-t,3);
            yaw=focus.fromYaw+(focus.toYaw-focus.fromYaw)*e;
            pitch=focus.fromPitch+(focus.toPitch-focus.fromPitch)*e;
            if (t>=1) focus=null;
          }
          drawGlobe('front'); drawGlobe('back');
          updateDOM();
        } catch (err) {
          const box=document.getElementById('geo-error');
          if (box) { box.style.display='block'; box.textContent='渲染提示：' + err.message; }
          console.error(err);
        }
      }

      function setZoom(value) {
        targetZoom = clamp(value, ZOOM_MIN, ZOOM_MAX);
        lastInteract = Date.now();
      }
      document.getElementById('zoom-out').addEventListener('click', () => setZoom(targetZoom - 0.06));
      document.getElementById('zoom-in').addEventListener('click', () => setZoom(targetZoom + 0.06));
      document.getElementById('zoom-reset').addEventListener('click', () => setZoom(1.0));

      function packChildren() {
        const children = nodes.filter(n => n.type === 'child');
        const sphereR = views.front.R || 175;
        for (let iteration=0; iteration<170; iteration++) {
          for (let i=0;i<children.length;i++) {
            for (let j=i+1;j<children.length;j++) {
              const a=children[i], b=children[j];
              const dot=clamp(a.pos.x*b.pos.x+a.pos.y*b.pos.y+a.pos.z*b.pos.z,-1,1);
              const angle=Math.acos(dot);
              const minAngle=((a.radius+b.radius)/sphereR)*0.92;
              if (angle <= 0.0001 || angle >= minAngle) continue;
              const overlap=minAngle-angle;
              let tx=b.pos.x-a.pos.x*dot, ty=b.pos.y-a.pos.y*dot, tz=b.pos.z-a.pos.z*dot;
              const tl=Math.hypot(tx,ty,tz)||1; tx/=tl; ty/=tl; tz/=tl;
              a.pos=norm({x:a.pos.x+tx*overlap*0.24,y:a.pos.y+ty*overlap*0.24,z:a.pos.z+tz*overlap*0.24});
              b.pos=norm({x:b.pos.x-tx*overlap*0.24,y:b.pos.y-ty*overlap*0.24,z:b.pos.z-tz*overlap*0.24});
            }
          }
        }
      }

      packChildren();
      ensureElements();
      syncSizes();
      for (const view of ['front','back']) {
        const el=views[view].el;
        el.addEventListener('pointerdown', e => startRotate(e,view));
        el.addEventListener('wheel', e => {
          e.preventDefault();
          setZoom(targetZoom + (e.deltaY < 0 ? 0.05 : -0.05));
        }, {passive:false});
      }
      // Set an initial frame synchronously because a Streamlit tab can be
      // created while hidden, where requestAnimationFrame may be suspended.
      // Sizes are re-synced every tick because hidden tabs start at width 0.
      tick(performance.now());
      setInterval(() => tick(performance.now()), 33);
    </script>
    """
    tag_count = sum(1 for node in data.get("nodes", []) if node.get("type") == "child")
    return (
        template.replace("__DATA__", payload)
        .replace("__COUNT__", str(data.get("total_videos", 0)))
        .replace("__TAG_COUNT__", str(tag_count))
    )


def wordcloud_html(data: dict[str, Any], *, dark: bool = False, height: int = 760) -> str:
    """Render a draggable, circular, partition-clustered word cloud."""
    if not data.get("nodes"):
        return "<div style='padding:24px;color:#898781'>当前筛选下没有可展示的标签。</div>"
    surface = "#1a1a19" if dark else "#fcfcfb"
    page = "#0d0d0d" if dark else "#f7f7f5"
    ink = "#f0efec" if dark else "#0b0b0b"
    secondary = "#c3c2b7" if dark else "#52514e"
    muted = "#898781"
    grid = "#2c2c2a" if dark else "#e1e0d9"
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    template = r"""
    <style>html, body { margin:0; background:transparent; }</style>
    <div class="wc-shell">
      <div class="wc-head">
        <div><b>分区 × 标签语义词云</b><span>分区是主标签；标签数量不设上限。可拖拽词块。</span></div>
        <div class="wc-count">__COUNT__ 条视频</div>
      </div>
      <div class="stage-wrap">
        <div class="stage" id="stage">
          <div class="tip" id="tip"></div>
        </div>
      </div>
      <div class="wc-foot">
        <span>词块大小 = 覆盖视频数</span><span>位置 = 分区聚类 + 共现排序</span><span>拖拽可移动</span>
      </div>
    </div>
    <style>
      .wc-shell { font-family: system-ui, -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
        color: __INK__; background: transparent; width:100%; }
      .wc-head { display:flex; justify-content:space-between; align-items:flex-start; gap:18px;
        padding: 0 8px 10px; color:__SECONDARY__; font-size:12px; }
      .wc-head b { color:__INK__; font-size:14px; display:block; margin-bottom:3px; }
      .wc-count { color:__MUTED__; white-space:nowrap; font-size:12px; }
      .stage-wrap { display:flex; justify-content:center; }
      .stage { position:relative; width:min(720px, 94vw); aspect-ratio:1 / 1;
        border-radius:50%; overflow:hidden; isolation:isolate;
        background: radial-gradient(circle at 50% 48%, __SURFACE__ 0%, __SURFACE__ 58%, __PAGE__ 100%);
        border:1px solid __GRID__; touch-action:none; }
      .word { position:absolute; transform:translate(-50%,-50%); white-space:nowrap;
        cursor:grab; user-select:none; line-height:1; padding:3px 4px; border-radius:5px;
        transition: opacity .12s ease, filter .12s ease; }
      .word:hover { filter:brightness(1.12); opacity:1 !important; z-index:20; }
      .word.dragging { cursor:grabbing; z-index:30; filter:brightness(1.2); }
      .word.partition { font-weight:750; letter-spacing:.02em; }
      .tip { position:absolute; display:none; z-index:40; pointer-events:none; padding:5px 8px;
        border-radius:6px; background:__INK__; color:__SURFACE__; font-size:11px;
        white-space:nowrap; transform:translate(-50%,-125%); }
      .wc-foot { display:flex; gap:16px; flex-wrap:wrap; justify-content:center;
        padding:10px 4px 0; color:__MUTED__; font-size:11px; }
    </style>
    <script>
      const DATA = __DATA__;
      const stage = document.getElementById('stage');
      const tip = document.getElementById('tip');
      const DESIGN = 640, R = 286;
      const W = stage.clientWidth || 680;
      const H = stage.clientHeight || W;
      const scale = Math.min(W, H) / DESIGN;
      const cx = W / 2, cy = H / 2;
      const nodes = DATA.nodes.map((n, index) => {
        const tr = n.radius * scale;
        const tx = cx + Math.cos(n.angle) * tr;
        const ty = cy + Math.sin(n.angle) * tr;
        const fs = n.fontSize * scale;
        const w = n.label.length * fs * 0.98 + 9;
        const h = fs * 1.22 + 5;
        return {
          ...n,
          fs, w, h, tx, ty,
          x: tx + (index % 2 ? 1 : -1) * (5 + (index % 5) * 3),
          y: ty + (index % 3 - 1) * 6,
          vx: 0, vy: 0,
          rad: Math.max(w, h) / 2
        };
      });
      const byId = Object.fromEntries(nodes.map(n => [n.id, n]));
      const edges = DATA.edges.map(e => [byId[e[0]], byId[e[1]], e[2]]).filter(e => e[0] && e[1]);

      for (let iter = 0; iter < 650; iter++) {
        for (const n of nodes) {
          n.vx += (n.tx - n.x) * 0.014;
          n.vy += (n.ty - n.y) * 0.014;
        }
        for (let i = 0; i < nodes.length; i++) {
          for (let j = i + 1; j < nodes.length; j++) {
            const a = nodes[i], b = nodes[j];
            const dx = b.x - a.x, dy = b.y - a.y;
            const overlapX = (a.w + b.w) / 2 + 5 - Math.abs(dx);
            const overlapY = (a.h + b.h) / 2 + 4 - Math.abs(dy);
            if (overlapX > 0 && overlapY > 0) {
              if (overlapX < overlapY) {
                const push = Math.sign(dx || (i % 2 ? 1 : -1)) * overlapX * 0.16;
                a.vx -= push; b.vx += push;
              } else {
                const push = Math.sign(dy || (j % 2 ? 1 : -1)) * overlapY * 0.20;
                a.vy -= push; b.vy += push;
              }
            }
          }
        }
        for (const [a, b, weight] of edges) {
          const dx = b.x - a.x, dy = b.y - a.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
          const desired = a.rad + b.rad + 18;
          const push = (dist - desired) / dist * Math.min(0.0025, 0.0006 + weight * 0.0001);
          a.vx += dx * push; a.vy += dy * push;
          b.vx -= dx * push; b.vy -= dy * push;
        }
        for (const n of nodes) {
          n.x += n.vx * 0.52; n.y += n.vy * 0.52;
          n.vx *= 0.72; n.vy *= 0.72;
          const dx = n.x - cx, dy = n.y - cy;
          const dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
          const maxR = R * scale - n.rad - 2;
          if (dist > maxR) {
            n.x = cx + dx / dist * maxR;
            n.y = cy + dy / dist * maxR;
            n.vx *= 0.35; n.vy *= 0.35;
          }
        }
      }

      function clampi(n, x, y) {
        let dx = x - cx, dy = y - cy;
        let dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
        const maxR = R * scale - n.rad - 2;
        if (dist > maxR) {
          return [cx + dx / dist * maxR, cy + dy / dist * maxR];
        }
        return [x, y];
      }

      for (const n of nodes) {
        const el = document.createElement('div');
        el.className = 'word ' + (n.type === 'partition' ? 'partition' : 'tag');
        el.textContent = n.label;
        el.title = `${n.label} · ${n.value} 条视频`;
        el.style.fontSize = n.fs + 'px';
        el.style.color = n.color;
        el.style.left = n.x + 'px';
        el.style.top = n.y + 'px';
        el.dataset.id = n.id;
        el.addEventListener('pointerenter', (event) => {
          const rect = stage.getBoundingClientRect();
          tip.textContent = `${n.label} · ${n.value} 条视频`;
          tip.style.display = 'block';
          tip.style.left = (event.clientX - rect.left) + 'px';
          tip.style.top = (event.clientY - rect.top) + 'px';
        });
        el.addEventListener('pointermove', (event) => {
          const rect = stage.getBoundingClientRect();
          tip.style.left = (event.clientX - rect.left) + 'px';
          tip.style.top = (event.clientY - rect.top) + 'px';
        });
        el.addEventListener('pointerleave', () => { tip.style.display = 'none'; });
        let dragging = false;
        el.addEventListener('pointerdown', (event) => {
          event.preventDefault();
          dragging = true;
          el.classList.add('dragging');
          el.setPointerCapture(event.pointerId);
        });
        el.addEventListener('pointermove', (event) => {
          if (!dragging) return;
          const rect = stage.getBoundingClientRect();
          let x = event.clientX - rect.left;
          let y = event.clientY - rect.top;
          [x, y] = clampi(n, x, y);
          n.x = x; n.y = y;
          el.style.left = x + 'px';
          el.style.top = y + 'px';
        });
        const stop = (event) => {
          dragging = false;
          el.classList.remove('dragging');
          try { el.releasePointerCapture(event.pointerId); } catch (_) {}
        };
        el.addEventListener('pointerup', stop);
        el.addEventListener('pointercancel', stop);
        stage.appendChild(el);
      }
    </script>
    """
    return (
        template.replace("__DATA__", payload)
        .replace("__COUNT__", str(data.get("total_videos", 0)))
        .replace("__SURFACE__", surface)
        .replace("__PAGE__", page)
        .replace("__INK__", ink)
        .replace("__SECONDARY__", secondary)
        .replace("__MUTED__", muted)
        .replace("__GRID__", grid)
    )
