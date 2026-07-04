# anime_daily - 日本动漫番剧日报生成与发送系统

自动生成《日本动漫番剧日报》并发送到邮箱与 Telegram 频道。
日报包含多个板块，覆盖新闻、热度排行、黑马潜力、编辑推荐与追番清单。

## 目录

```
anime_daily/
├── anime_daily.sh                # 主入口：收集数据 → 生成 HTML → 发送邮件 → 发送 TG
├── scripts/
│   └── anime_data_collector.py   # 收集动漫数据并写入 daily_news/*.json
├── generate_anime_daily.py        # 读取 JSON 并渲染模板
├── templates/
│   └── anime_daily.html.j2       # Jinja2 报告模板
├── send_report_email.py           # 发送 HTML 邮件
├── send_tg_report.py              # HTML → Telegram 等宽文本，自动分段并发送
└── config.ini                     # 私密配置，不提交
```

## 本地运行

```bash
bash anime_daily.sh
```

## 调度

使用系统 crontab，每天 11:30 执行：

```bash
30 11 * * * /root/anime_daily/anime_daily.sh >> /root/anime_daily/cron.log 2>&1
```

## 隐私

不把敏感内容提交到 GitHub，`config.ini` 已写入 `.gitignore`。
