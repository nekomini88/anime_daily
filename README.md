# anime_daily — 日本动漫番剧日报生成与投递系统

自动生成《日本动漫番剧日报》并发送到邮箱与 Telegram 频道。日报基于**当日真实数据**（AniList 主 / Jikan 备用）采集热度、评分、类型、制作公司等，由 **LLM（OpenCode Zen）基于真实数据生成内容章节**（新闻/推荐/黑马/销量/金句），彻底消除硬编码假数据。

## 🏗 架构

```text
AniList GraphQL（主） / Jikan API v4（备）
      │  scripts/anime_data_collector.py
      ▼
daily_news/anime_data_YYYY-MM-DD.json   ← 真实数据快照（热度/评分/类型/公司/集数）
      │
      ├─► generate_anime_llm.py  ──►  llm_data/anime_llm_YYYY-MM-DD.json（9章内容：新闻/推荐/黑马/销量/金句）
      │      OpenCode Zen (longcat-2.0-free)
      │
      ▼
generate_anime_daily.py  (合并真实数据 + LLM 内容，渲染 Jinja2)
      │
      ▼
files/YYYY-MM-DD/动漫日报_YYYY-MM-DD.html
      │
      ├─► send_report_email.py   ──► Email
      ├─► send_tg_report.py      ──► Telegram（等宽文本自动分段）
      └─► index/index.html       （Docker Caddy 静态站点）
```

## 📁 目录结构

```
anime_daily/
├── anime_daily.sh                # 主入口：收集→LLM→生成HTML→邮件→TG→红线审查
├── scripts/
│   ├── anime_data_collector.py   # AniList 主/Jikan 备采集，输出真实 JSON
│   └── title_overrides.json      # 本地中文标题映射（英文/罗马音/日文→官方中文）
├── generate_anime_llm.py         # LLM 生成 9 章内容（OpenCode Zen，基于真实数据）
├── generate_anime_daily.py       # 合并真实数据+LLM内容，渲染 HTML
├── templates/
│   └── anime_daily.html.j2       # Jinja2 报告模板
├── send_report_email.py          # 发送 HTML 邮件
├── send_tg_report.py             # HTML → Telegram 等宽文本，自动分段并发送
├── docker-compose.yml / Caddyfile  # Docker 静态部署
└── config.ini                    # 私密配置，不提交
```

## 🔧 报告板块

| 板块 | 数据来源 |
|------|---------|
| 📰 今日动漫圈重要新闻 | LLM（基于真实在播作品） |
| 🔥 本季新番热度排行榜 TOP10 | 真实（热度=关注度+收藏加权，评分/类型/公司真实） |
| ✨ 今日编辑推荐 | LLM（从真实 TOP10 选取） |
| 🌱 本周口碑黑马 | LLM（真实评分/数据） |
| 📦 销量与商业数据 | LLM（基于真实在播题材） |
| 🏢 活跃动画制作公司 | 真实（AniList studios） |
| 🎨 本季题材分布 | 真实（genres 聚合） |
| 💬 今日动漫金句 | LLM |

**数据真实性原则**：数字（评分/热度/收藏/播放量/集数/公司）一律来自当日真实采集；文字类内容由 LLM 基于真实数据生成，缺失数据如实标"暂无可用数据"，绝不编造。

## 🚀 本地运行

```bash
bash anime_daily.sh
```

分步：
```bash
# 1. 采集真实数据
python3 scripts/anime_data_collector.py 2026-08-06
# 2. LLM 生成内容（失败自动用兜底文字）
python3 generate_anime_llm.py 2026-08-06
# 3. 生成 HTML
python3 generate_anime_daily.py 2026-08-06
# 4. 发送
python3 send_tg_report.py "files/2026-08-06/动漫日报_2026-08-06.html"
python3 send_report_email.py "files/2026-08-06/动漫日报_2026-08-06.html" "日本动漫番剧日报 2026-08-06" --html
```

## ⏰ 调度

系统 crontab，每天 11:30 执行：
```bash
30 11 * * * /root/anime_daily/anime_daily.sh >> /root/anime_daily/cron.log 2>&1
```

## 🤖 LLM 接入

- Endpoint：`https://opencode.ai/zen/v1/chat/completions`
- Model：`longcat-2.0-free`
- Key：`OPENCODE_ZEN_API_KEY`（`/root/.hermes/.env`）
- ⚠️ 必须用 `requests`（urllib 会被 Cloudflare 拦截 403）
- 解析：content 为空时降级用 `reasoning_content`，兼容 markdown 包裹 JSON

## 📌 标题稳定性方案

外部 API 返回标题不稳定（英文/罗马音/日文），AniList 中文 synonym 不可靠。采用：

1. **本地 `scripts/title_overrides.json`**：常见作品 → 官方中文译名
2. **代码层 `_normalize_candidate` 匹配**：统一小写、去符号（`～`/`Ⅱ`/`☆`/引号/冒号），再做映射
3. 新映射只需向 `title_overrides.json` 追加即可

## 🐳 Docker 静态部署

`docker-compose.yml` 用 Caddy 提供 `index/index.html` 静态站点：
- 访问：http://localhost:9004
- 容器名：`anime_daily`，端口 `9004:80`

## 🔒 隐私

`config.ini`（SMTP/TG 配置）与生成产物（`files/`、`daily_news/`、`llm_data/`、`cron.log`）均不提交 GitHub。