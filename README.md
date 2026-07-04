# anime_daily_report - 日本动漫番剧日报生成与发送系统

自动生成《日本动漫番剧日报》并发送到邮箱与 Telegram 频道。
日报包含多个板块，覆盖新闻、热度排行、黑马潜力、编辑推荐与追番清单。

## 当前结构

anime_daily_report/
├── scripts/
│   └── anime_data_collector.py        # 数据采集
├── templates/
│   └── anime_daily.html.j2            # HTML 模板
├── daily_news/
│   └── anime_data_YYYY-MM-DD.json     # 日报数据
├── files/YYYY-MM-DD/                  # 输出目录
├── generate_anime_report.py           # JSON → HTML
├── send_tg_report.py                  # HTML → Telegram 分段发送
├── send_report_email.py               # HTML 邮件发送
├── anime_daily_cron.sh                # 主流程入口
├── config.ini                          # Telegram / 邮件配置
└── README.md

## 快速开始

```bash
cd /root/anime_daily_report

# 生成报告
python3 generate_anime_report.py 2026-07-04

# 发送到 Telegram
python3 send_tg_report.py files/2026-07-04/动漫日报_2026-07-04.html

# 发送邮件
python3 send_report_email.py files/2026-07-04/动漫日报_2026-07-04.html "日本动漫番剧日报 2026-07-04" --html
```

## 定时任务

```bash
30 11 * * * /root/anime_daily_report/anime_daily_cron.sh >> /root/anime_daily_report/cron.log 2>&1
```

## 配置说明

- Telegram 频道 ID 与邮件配置写在 `config.ini`
- `config.ini` 已加入 `.gitignore`，不提交到版本库

## 许可证

MIT License
