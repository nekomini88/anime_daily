#!/usr/bin/env python3
"""动漫日报 LLM 内容生成器
读取采集器输出的真实数据快照，用 OpenCode Zen(longcat) 基于当日真实数据生成 9 章内容结论，
替代硬编码假数据。复用 stock_daily 的 requests 调用模式。
"""
import json
import os
import sys
import re
import requests
from pathlib import Path

BASE = Path(__file__).resolve().parent
DEFAULT_KEY = "/root/.hermes/.env"
ZEN_URL = "https://opencode.ai/zen/v1/chat/completions"
MODEL = "longcat-2.0-free"


def _load_api_key():
    for p in ["/root/.hermes/.env", BASE / ".env", Path("~/.hermes/.env").expanduser()]:
        if Path(p).exists():
            for line in Path(p).read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("OPENCODE_ZEN_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return os.environ.get("OPENCODE_ZEN_API_KEY")


def _call_zen(system, user, max_tokens=2400, temperature=0.7):
    key = _load_api_key()
    if not key:
        raise RuntimeError("缺少 OPENCODE_ZEN_API_KEY")
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    try:
        r = requests.post(
            ZEN_URL,
            json=payload,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            timeout=180,
        )
        r.raise_for_status()
        body = r.json()
        msg = (body.get("choices") or [{}])[0].get("message", {}) or {}
        content = (msg.get("content") or "").strip()
        if not content:
            content = (msg.get("reasoning_content") or "").strip()
        return content
    except Exception as e:
        print(f"❌ LLM 调用失败: {e}", file=sys.stderr)
        raise


def generate_content(data: dict, date_str: str) -> dict:
    """基于真实数据生成 9 章文字内容，返回 {news, quote, editor, hit, sales_analysis, market_comment}"""
    ranking = data.get("ranking") or []
    studios = data.get("studios") or []
    top_titles = [r["title"] for r in ranking[:10]]
    top_with_score = [
        {"rank": r["rank"], "title": r["title"], "genre": r.get("genre"), "score": r.get("score"),
         "heat": r.get("heat"), "episodes": r.get("episodes"), "studio": r.get("studio")}
        for r in ranking[:10]
    ]
    top_genres = sorted({g for r in ranking[:10] for g in (r.get("all_genres") or [])})[:10]

    prompt = f"""今天是 {date_str}。以下是本季日本动漫在播作品的真实数据快照（来自 AniList/Jikan）：

热门作品 TOP10（已按热度降序排列，rank=名次，heat=热度值）:
{json.dumps(top_with_score, ensure_ascii=False, indent=1)}

本季主要类型: {', '.join(top_genres)}
本季活跃制作公司: {', '.join(studios) if studios else '（数据暂缺）'}

请严格基于以上真实数据，生成今日动漫日报的内容类章节，输出 JSON，字段如下：
{{
  "news": [
    {{"title":"今日动漫圈重要新闻1","tags":["标签1","标签2"],"content":"基于真实数据的客观描述","impact":"影响分析"}},
    {{"title":"...","tags":[...],"content":"...","impact":"..."}}
  ]，
  "rank_reason": {{"1":"榜首(真实作品名)热度的客观理由","2":"...","3":"..."}},
  "hit":[{{"title":"本周口碑黑马(从真实榜单选)", "reason":"基于真实评分/数据的原因"}}],
  "sales":[{{"category":"商业数据类别","content":"基于真实在播作品与类型的数据化描述","trend":"up/down/flat"}}],
  "quote": {{"source":"今日动漫日报","character":"编辑","line":"一句原创动漫金句","meaning":"金句含义"}},
  "editor": {{"title":"编辑最推荐作品","reason":"真实理由","audience":"适合人群","similar":["类似作品1","类似作品2"]}}
}}

要求：
1. news 必须 2-3 条，content 必须基于上述真实作品的类型/评分/公司，禁止编造不存在的事实
2. rank_reason 必须严格按榜单给出的 rank 顺序写第 n 名的理由（"1"对应榜单 rank=1 的榜首，以此类推），理由基于该名次真实作品的评分/热度/公司
3. 热度黑马/编辑推荐必须从真实 TOP10 中选取，引用真实评分与类型
4. 若无相关数据，字段如实写"暂无可用数据"，绝不编造数字
5. 全部用简体中文
只输出 JSON，不要多余文字。"""
    system = "你是专业的日本动漫行业日报编辑，只根据提供的真实数据写分析，绝不编造事实。输出 JSON。"
    out = _call_zen(system, prompt)
    return _parse_json(out)


def _parse_json(content: str) -> dict:
    """从 LLM 输出中提取 JSON（兼容 markdown 包裹 / 思考文本残留）"""
    content = (content or "").strip()
    if content.startswith("```"):
        m = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL)
        if m:
            content = m.group(1).strip()
    try:
        return json.loads(content)
    except Exception:
        m = re.search(r"\{.*\}", content, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
        print(f"❌ LLM 输出非 JSON: {content[:200]}", file=sys.stderr)
        raise ValueError("LLM 输出无法解析为 JSON")


def main(date_str=None):
    from datetime import datetime, timezone, timedelta
    if not date_str:
        date_str = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    src = BASE / "daily_news" / f"anime_data_{date_str}.json"
    data = json.loads(src.read_text(encoding="utf-8"))
    content = generate_content(data, date_str)
    # 写入 llm 结论文档
    out_dir = BASE / "llm_data"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / f"anime_llm_{date_str}.json"
    out_file.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ 动漫日报 LLM 内容已生成: {out_file} (news={len(content.get('news', []))})")
    return content


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)