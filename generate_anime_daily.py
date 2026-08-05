#!/usr/bin/env python3
"""动漫日报生成脚本
读取 daily_news JSON（真实数据）+ llm_data JSON（LLM 内容章节），
合并后渲染模板。
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

    # 合并 LLM 内容章节（若存在）
    llm_path = BASE / "llm_data" / f"anime_llm_{date_str}.json"
    llm = {}
    if llm_path.exists():
        try:
            llm = json.loads(llm_path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"⚠️ LLM 内容解析失败: {e}", file=sys.stderr)

    # 组装模板所需完整结构（数据用真实，文字用 LLM，缺失时诚实兜底）
    ranking = data.get("ranking") or []
    report = {
        "date": date_str,
        "source": data.get("source", ""),
        "ranking": ranking,
        # LLM 章节（缺省给"数据待完善"）
        "news": llm.get("news") or [{
            "title": "今日动漫圈数据概览", "tags": ["数据"],
            "content": f"本季共有 {len(ranking)} 部在播作品进入热度榜单，数据源：{data.get('source','')}。",
            "impact": "基于当日真实数据生成，供追番参考。",
        }],
        "rank_reason": llm.get("rank_reason") or {},
        "hit": llm.get("hit") or [{"title": "敬请关注", "reason": "暂无可用数据"}],
        "sales": llm.get("sales") or [{"category": "综合", "content": "暂无可用数据", "trend": "flat"}],
        "quote": llm.get("quote") or {
            "source": "今日动漫日报", "character": "编辑",
            "line": "追番的乐趣，在于与作品一同成长。", "meaning": "保持对好作品的期待。",
        },
        "editor": llm.get("editor") or {
            "title": ranking[0]["title"] if ranking else "待定",
            "reason": "本季热度榜首位（真实数据）", "audience": "综合观众", "similar": ["敬请期待"],
        },
        "studios": data.get("studios") or [],
        "genres": data.get("genres") or [],
        "overview_note": f"数据源：{data.get('source','')} · 热度=关注度+收藏加权 · 榜单真实采集",
    }

    out_dir = BASE / "files" / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"动漫日报_{date_str}.html"

    env = Environment(
        loader=FileSystemLoader(str(TMPL.parent)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    tpl = env.get_template(TMPL.name)
    generated_at = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    html = tpl.render(report=report, date=date_str, generated_at=generated_at)
    out_file.write_text(html, encoding="utf-8")
    print(f"✅ 动漫日报HTML已生成：{out_file}")
    return report


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else None
    render(d)