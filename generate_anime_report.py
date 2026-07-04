#!/usr/bin/env python3
"""
动漫日报生成脚本 - 读取 daily_news JSON 并渲染模板
"""
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape
except Exception as e:
    raise SystemExit(f"❌ 缺少 jinja2: {e}")

BASE = Path(__file__).resolve().parent
TMPL = BASE / "templates" / "anime_daily.html.j2"


def render(date_str=None):
    if not date_str:
        date_str = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")

    data_path = BASE / "daily_news" / f"anime_data_{date_str}.json"
    if not data_path.exists():
        raise FileNotFoundError(f"缺少数据文件：{data_path}")

    data = json.loads(data_path.read_text(encoding="utf-8"))

    out_dir = BASE / "files" / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"动漫日报_{date_str}.html"

    env = Environment(
        loader=FileSystemLoader(str(TMPL.parent)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    tpl = env.get_template(TMPL.name)
    generated_at = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    html = tpl.render(report=data, date=date_str, generated_at=generated_at)
    out_file.write_text(html, encoding="utf-8")
    print(f"✅ 动漫日报HTML已生成：{out_file}")


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else None
    render(d)
