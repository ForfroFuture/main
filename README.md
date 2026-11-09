# B站每周必看 · 内容洞察

从 B 站「每周必看」公开接口动态拉取期数，补齐视频分区与互动数据，使用 AI 为每条视频生成内容标签（数量不设上限），再用 Streamlit 完成分区饼图、交互词云、加权榜单、个性化推荐和 UP 主上榜追踪。

## 功能一览

- **内容总览**：最新一期 / 指定期数 / 时间范围，自动拉取并打标。
- **分区饼图**：不同颜色扇区，鼠标悬停显示“斜线 + 直线”标注，标注内容为分区名和占比。
- **可旋转词云**：正反两个同步视角，深色球面固定不随夜间模式变化；圆形词球固定在球面语义锚点上，大小按覆盖视频数，颜色沿分区语义场过渡。拖拽空白旋转，滚轮或 `− / +` 按钮缩放；缩小合并为分区大标签，放大展开为细分标签。双击词球会把视角转到它。
- **加权榜单**：默认按播放 ×0.1、点赞 ×0.3、投币 ×1.0、收藏 ×0.5、评论 ×0.75、弹幕 ×0.4、转发 ×1.5 计算；也可切换播放、点赞等单项排序。
- **个性化分析**：选择偏好分区与标签后，按“加权热度 50% + 分区匹配 25% + 标签匹配 15% + 互动率 10%”重排推荐。
- **单条视频分析**：视频明细页底部可选择任意视频，展示数据侧写、为什么可能火、下一周/下个月潜在热点，以及带点幽默感的本地总结。
- **底部数据问答**：页面底部固定输入框；对话记录显示在右侧，左侧栏可打开历史对话。支持分区、标签、UP 主、对比、追问上下文、最火/播放最高等本地查询；可开启 “DeepSeek 综合” 在本地分析基础上调用 DeepSeek API 做长文综合分析，余额不足自动回退本地。
- **UP 主追踪**：仅从“上过每周必看”的 UP 主中选择，按月份统计其上榜视频数量，并给出所有上榜视频的 B 站链接。
- **夜间模式**：左侧开关切换全页暗色主题，图表与自定义组件同步换色。
- 所有榜单卡片、推荐卡片和数据表均提供 B 站视频跳转链接。

## 快速开始

```powershell
cd D:\下载转移\bilibili视频数据反馈
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

浏览器打开 `http://localhost:8501`。也可以直接双击 `启动应用.bat`：如果应用已经运行，会复用现有实例并打开浏览器；如果 8501 被其他程序占用，会自动尝试 8502–8510。需要关闭时双击 `停止应用.bat`。

AI 打标读取 `ANTHROPIC_BASE_URL` 与 `ANTHROPIC_AUTH_TOKEN`（或 `ANTHROPIC_API_KEY`）。本地可直接复制 `.env.example` 为 `.env` 并填写；也可以只通过环境变量配置，不会把密钥写进代码。

```powershell
$env:ANTHROPIC_BASE_URL = "https://api.deepseek.com/anthropic"
$env:ANTHROPIC_AUTH_TOKEN = "你的 Key"
$env:BILI_AI_MODEL = "deepseek-chat"
python -m streamlit run app.py
```

没有 AI 凭据时仍可运行，应用会使用规则回退标签，并在数据质量页标记回退比例。

## 使用方式

1. 左侧选择：最新一期 / 指定期数 / 时间范围。
2. 点击 **开始拉取并分析**。时间范围按每周必看的周区间与所选日期是否重叠来匹配期数。
3. 拉取完成后自动生成 processed 数据、标签频次、分区统计、词云、榜单、Excel 和评估报告。
4. 切换到 **UP主追踪**，选择已上榜的 UP 主与时间范围；首次会读取历史期数，之后复用本地缓存。

单次最多分析 8 期，避免触发 B 站接口限流和产生过多 AI 调用。UP 主追踪单次最多扫描 60 期。首次处理需要逐条补齐视频详情，通常每期约 35–50 秒；标签结果会按内容哈希缓存，重复分析不会重复调用模型。

## 数据流

```text
Bilibili series/list ──► raw/series_list.json
Bilibili series/one  ──► raw/issues/{期数}/series_one.json
    └─ web 详情被风控 -352 时自动切换 app 详情
视频详情 view/detail ──► raw/issues/{期数}/videos/{BV}.json
    ├─ 分区 tid_v2 → B站 v2 分区表
    ├─ 播放/点赞/投币/收藏/评论/弹幕/转发
    └─ UP 主已有标签
AI 标签（数量不设上限）──► cache/tags/{content_hash}.json
    └─ 清洗、去重、分区名/UP 名/泛词过滤
processed/*.csv ──► 标签频次 / 分区统计 / 期数趋势 / 加权榜单 / UP 月榜
output/*.xlsx|csv|json|md
```

### 目录

```text
D:\下载转移\bilibili视频数据反馈\
├─ app.py                      Streamlit 应用
├─ launcher.py                 端口复用与自动启动
├─ src\                        数据加载、清洗、AI 打标、分析、交互组件、导出
├─ scripts\                    命令行运行、重新导出、重新打包
├─ assets\                     B站 v2 分区参考表
├─ data\raw\                   原始 JSON（按期数和视频保存）
├─ data\processed\             清洗后的 CSV 与 UP 月榜缓存
├─ data\output\                标签频次、分区统计、榜单、个性化、词云、Excel、报告
├─ data\cache\tags\            AI 标签缓存
├─ dist\                       可分发 ZIP
└─ logs\                       运行日志
```

所有数据子目录由 `os.makedirs(..., exist_ok=True)` 自动创建。

## 核心字段

- `videos.csv`：去重视频，一行一条，包含分区、UP 主、播放/互动、AI 标签、标签来源与延迟。
- `appearances.csv`：按期数的上榜记录，同一条视频跨期出现会保留多条。
- `video_tags.csv`：视频 × 标签的长表。
- `tag_frequency.csv`：标签覆盖视频数、占比、中位播放、跨分区数、示例视频。
- `category_stats.csv` / `subcategory_stats.csv`：主分区/子分区统计。
- `ranking.csv`：综合加权分、排名和 B 站链接。
- `personalized_default.json`：默认偏好画像与推荐理由。
- `chat_history.json`：底部数据问答的历史对话（保存在 processed 目录）。
- `evaluation.json`：标签覆盖率、AI 覆盖率、词汇丰富度、接口成功率、延迟等。

## 命令行

```powershell
# 最新一期
python scripts\run_pipeline.py --mode latest

# 指定一期
python scripts\run_pipeline.py --mode issue --issue 397

# 时间范围
python scripts\run_pipeline.py --mode range --start 2026-10-09 --end 2026-10-29

# 仅用已有 processed 数据重新生成 output 和安装包（不调用接口）
python scripts\rebuild_outputs.py

# API 余额不足时，用本地标签缓存恢复 AI 标签（不调用模型）
python scripts\rehydrate_from_cache.py

# 重新打包应用
python scripts\build_package.py
```

## 方法与边界

- 分区使用 B 站 v2 分区表（`tid_v2`）；旧版 `tid` 作为兜底。
- 标签是模型对公开元数据的归纳，不等同于人工审片。标签会经去重、分区名和 UP 名过滤，数量不设硬上限，但仍可能存在语义偏差。
- 播放、点赞等为抓取时点快照，后续会变化。
- B 站 web 详情接口可能返回 `-352` 风控；应用自动切换到 app 详情接口，并把实际来源写进 raw 的 meta JSON 与分析报告。
- 单次 8 期上限是为了控制接口压力和 AI 成本，不代表接口的理论上限。
- UP 主候选只来自已抓取到的每周必看数据；历史月份按每周结束日期归档。

## 产物

- `data\output\tag_frequency.csv`
- `data\output\category_stats.csv`
- `data\output\subcategory_stats.csv`
- `data\output\issue_stats.csv`
- `data\output\ranking.csv`
- `data\output\videos_with_tags.csv`
- `data\output\personalized_default.json`
- `data\output\tag_wordcloud.png`（静态报告预览；应用内使用可旋转词云组件）
- `data\output\evaluation.json`
- `data\output\analysis_report.md`
- `data\output\bilibili_weekly_analytics.xlsx`
- `dist\bilibili_weekly_analytics_YYYYMMDD.zip`
