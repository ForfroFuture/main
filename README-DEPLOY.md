# 公网部署与评委体验

推荐 **Streamlit Community Cloud**：不需要服务器，上传一个 GitHub 仓库即可得到 `https://<app-name>.streamlit.app` 链接。若比赛评委主要在中国大陆，或 Streamlit Cloud 访问不稳定，推荐最后一种香港/新加坡 VPS + Docker + Caddy 方案。

本项目的预置数据已经包含在 `data/processed` 和 `data/output`，评委无需重新拉取 B 站数据即可浏览、词云、榜单、个性化、UP 主与数据问答。

## 方案 A：Streamlit Community Cloud（最快）

### 1. 生成部署目录

```powershell
cd D:\下载转移\bilibili视频数据反馈
python scripts\prepare_deploy.py
```

得到：

- `dist\deploy_bundle\`
- `dist\bilibili_weekly_deploy.zip`

部署目录不含 `data/raw`、`data/cache`、`.env`、聊天历史，避免把原始抓取数据和密钥传上公网。

### 2. 推送到 GitHub

在 GitHub 新建仓库，例如 `bili-weekly-analytics`，把 `deploy_bundle` 内的文件放到仓库根目录：

```powershell
cd D:\下载转移\bilibili视频数据反馈\dist\deploy_bundle
git init
git add .
git commit -m "deploy bilibili weekly app"
git branch -M main
git remote add origin https://github.com/<你的账号>/bili-weekly-analytics.git
git push -u origin main
```

也可以在 GitHub 网页里直接上传 `deploy_bundle` 内的文件。

### 3. 创建 Streamlit 应用

1. 打开 <https://share.streamlit.io/>
2. 使用 GitHub 登录
3. New app → 选择仓库和 `main` 分支
4. Main file path 填 `app.py`
5. Python 版本选 3.12
6. 在 Advanced settings → Secrets 粘贴下面的 TOML：

```toml
ANTHROPIC_BASE_URL = "https://api.deepseek.com/anthropic"
ANTHROPIC_AUTH_TOKEN = "换成有余额的 DeepSeek Key"
BILI_AI_MODEL = "deepseek-chat"

APP_USER = "judge"
APP_PASSWORD = "换成一个足够长的评审密码"
DEMO_MODE = "true"
```

`DEMO_MODE = "true"` 会禁用页面里的“重新拉取”，防止评委误触长时间抓取和产生额外模型费用；已预置的 145 条视频、词云、榜单、聊天仍可正常使用。

### 4. 部署并验证

等待构建完成后，会得到类似：

```text
https://bili-weekly-analytics.streamlit.app
```

用无痕窗口打开，确认会先出现登录页，再输入：

- 账号：`judge`
- 密码：你设置的 `APP_PASSWORD`

然后把 **链接 + 账号 + 密码** 填进参赛表单的“智能体”部分。

> Streamlit Community Cloud 免费实例闲置后会休眠，评委第一次打开可能需要等 20–60 秒唤醒。

## 方案 B：Render（Docker，稳定一些）

仓库里已经包含 `Dockerfile`，Render 可以直接识别。

1. 将 `deploy_bundle` 推到 GitHub
2. Render → New → Web Service → 选择仓库
3. Runtime 选择 **Docker**
4. 设置环境变量（与 Secrets 相同，但用环境变量形式）：

```text
ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
ANTHROPIC_AUTH_TOKEN=...
BILI_AI_MODEL=deepseek-chat
APP_USER=judge
APP_PASSWORD=...
DEMO_MODE=true
```

5. 创建服务，Render 会给出 `https://<service>.onrender.com`
6. 无痕窗口测试登录和页面

Render 免费实例也会休眠；对评委来说通常比 Streamlit Cloud 慢一些，但 Docker 环境更可控。

## 方案 C：香港/新加坡 VPS + Docker + Caddy（评委主要在大陆时推荐）

一台 1 核 1G 以上的 Ubuntu VPS 足够。将 `deploy_bundle` 上传后：

```bash
docker build -t bili-weekly .
docker run -d --name bili-weekly --restart unless-stopped \
  -p 127.0.0.1:8501:8501 \
  --env-file .env \
  bili-weekly
```

` .env` 内容与上面的环境变量一致，不要提交到 Git。

用 Caddy 反向代理并自动 HTTPS：

```caddyfile
weekly.example.com {
    reverse_proxy 127.0.0.1:8501
}
```

然后：

```bash
sudo caddy reload --config /etc/caddy/Caddyfile
```

访问 `https://weekly.example.com`。登录页由应用内 `APP_PASSWORD` 保护；如果希望再加一层 HTTP Basic Auth，可以在 Caddy 里加 `basic_auth`。

这个方案没有免费实例休眠，评委打开更快，适合正式评审。

## 方案 D：临时 Cloudflare Tunnel（最后兜底）

如果距离提交只剩几十分钟，可以先在本机保持应用运行，然后：

```powershell
cloudflared tunnel --url http://127.0.0.1:8501
```

会得到一个临时 `https://....trycloudflare.com` 链接。缺点是电脑必须一直开着、链接可能变化、稳定性不适合正式评审，只建议应急演示。

## 提交表单怎么填

- **链接**：`https://<你的公网地址>`
- **账号**：`judge`
- **密码**：`APP_PASSWORD` 的值

不要把 DeepSeek API Key 填进参赛表单，也不要把 `.env`、`data/raw` 上传到公开仓库。

## 部署前自检

- [ ] 预置数据存在：`data/processed/videos.csv`、`data/output/tag_frequency.csv`
- [ ] 无痕窗口能打开登录页
- [ ] 登录后能切换总览 / 分区 / 词云 / 榜单 / 个性化 / UP 主
- [ ] 单条视频分析底部有“本期人话总结”
- [ ] 底部问答能回答“鬼畜区的情况”
- [ ] DeepSeek 综合开关可用；余额不足时能自动回退本地
- [ ] 评委不需要重新拉取数据
- [ ] 链接、账号、密码已经复制到提交表单
