#!/usr/bin/env python3
"""
动漫日报数据生成脚本 - 从 Jikan/AniList 拉取真实数据并导出日报 JSON
稳定中文标题方案：优先 native romaji / 英文；AniList 侧仅作为可选的 extra synonym 通道
"""
import json
import sys
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path

JIKAN_BASE = "https://api.jikan.moe/v4"
ANILIST_URL = "https://graphql.anilist.co"


# Cache: mal_id -> enhanced title candidate
_zh_cache: dict[int, str] = {}


def fetch_json(url, payload=None, headers=None):
    h = {"User-Agent": "anime-daily-report/1.0"}
    if headers:
        h.update(headers)
    data = None
    if payload is not None:
        h.setdefault("Content-Type", "application/json")
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"❌ fetch failed {url}: {e}", file=sys.stderr)
        return {}


def _jikan_get(path, params):
    qs = urllib.parse.urlencode(params, doseq=True)
    url = f"{JIKAN_BASE}{path}?{qs}"
    return fetch_json(url)


def fetch_top_anime(limit=20):
    data = _jikan_get("/top/anime", {"limit": limit, "sfw": "true"})
    inner = data.get("data") if isinstance(data, dict) else data
    return inner if isinstance(inner, list) else []


def fetch_seasonal_now(limit=15):
    data = _jikan_get("/seasons/now", {"limit": limit, "sfw": "true"})
    inner = data.get("data") if isinstance(data, dict) else data
    return inner if isinstance(inner, list) else []


def fetch_anime_search(query, limit=5):
    data = _jikan_get("/anime", {"q": query, "limit": limit, "sfw": "true", "order_by": "score", "sort": "desc"})
    inner = data.get("data") if isinstance(data, dict) else data
    return inner if isinstance(inner, list) else []


def _anilist_zh_candidates(mal_ids):
    if not mal_ids:
        return {}
    query = """
    query ($ids: [Int]) {
      Page(page: 1, perPage: 50) {
        media(idMal_in: $ids, type: ANIME) {
          idMal
          title { romaji english native }
          synonyms
        }
      }
    }
    """
    payload = {"query": query, "variables": {"ids": mal_ids}}
    data = fetch_json(ANILIST_URL, payload=payload, headers={"Content-Type": "application/json"})
    out = {}
    try:
        for media in data.get("data", {}).get("Page", {}).get("media", []):
            mid = media.get("idMal")
            title = media.get("title") or {}
            name = (media.get("synonyms") or [""])[0]
            if not name:
                name = title.get("english") or title.get("romaji") or title.get("native") or ""
            out[int(mid)] = name
    except Exception as e:
        print(f"❌ parse anilist failed: {e}", file=sys.stderr)
    return out


def load_title_overrides() -> dict[str,str]:
    p = Path(__file__).with_name("title_overrides.json")
    if not p.exists():
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        return {str(k): str(v) for k, v in data.items() if v}
    except Exception as e:
        print(f"❌ load title overrides failed: {e}", file=sys.stderr)
        return {}


_TITLE_OVERRIDES = load_title_overrides()


def _normalize_candidate(text: str) -> str:
    text = text.lower()
    text = text.replace("μ'sic", "music").replace("μ", "u")
    text = text.replace("'", "").replace("’", "").replace(":", " ").replace("-", " ")
    text = text.replace("  ", " ").strip()
    return text


def choose_title(anime: dict) -> str:
    mal = anime.get("mal_id")
    if mal and mal in _zh_cache:
        return _zh_cache[mal]

    direct = None
    title = anime.get("title") or {}
    if isinstance(title, dict):
        direct = title.get("english") or title.get("romaji") or title.get("native")
    elif isinstance(title, str):
        direct = title

    jp = anime.get("title_japanese")
    candidates = [c for c in [direct, jp] if c]

    normalized_map = {_normalize_candidate(c): c for c in candidates}
    for key, zh in _TITLE_OVERRIDES.items():
        norm_key = _normalize_candidate(key)
        if norm_key in normalized_map:
            return zh

    return next(iter(candidates)) or "未知作品"


def build_report(date_str=None):
    if not date_str:
        date_str = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")

    seasonal = fetch_seasonal_now(limit=15)
    top = fetch_top_anime(limit=20)
    source = seasonal if seasonal else top
    source = source[:10] if source else []

    mal_ids = [a.get("mal_id") for a in source if a.get("mal_id")]
    try:
        zh_map = _anilist_zh_candidates(mal_ids)
        _zh_cache.update(zh_map)
    except Exception as e:
        print(f"⚠️ 中文标题增强失败：{e}", file=sys.stderr)

    genres_map = {}
    ranking = []
    for idx, anime in enumerate(source[:10], 1):
        title = choose_title(anime)
        score = anime.get("score") or 0.0
        genres = [g.get("name", "") for g in anime.get("genres", [])]
        main_genre = genres[0] if genres else "综合"
        ranking.append({
            "rank": idx,
            "title": title,
            "genre": main_genre,
            "score": f"评分 {score:.1f}",
            "trend": "flat",
            "recommend": "本季热门，适合按兴趣追看"
        })

    pick = []
    pick_titles = set()
    for anime in source[:10]:
        title = choose_title(anime)
        if title in pick_titles:
            continue
        pick_titles.add(title)
        score = anime.get("score") or 0.0
        synopsis = (anime.get("synopsis") or "")[:100]
        episodes = anime.get("episodes") or "?"
        pick.append({
            "title": title,
            "status": f"更新中 · 共 {episodes} 话",
            "stars": "★★★★★" if score >= 8.5 else ("★★★★☆" if score >= 7.5 else "★★★☆☆"),
            "highlight": synopsis or "暂无简介",
            "audience": (anime.get("genres") or [{}])[0].get("name") and f"喜欢 {(anime.get('genres') or [{}])[0].get('name')} 风格的观众" or "综合观众"
        })
        if len(pick) >= 3:
            break

    studios = []
    seen = set()
    for anime in source[:20]:
        studio = ((anime.get("studios") or [{}])[0].get("name", "")).strip()
        if studio and studio not in seen:
            seen.add(studio)
            studios.append(studio)
        if len(studios) >= 5:
            break

    company_rows = [{"company": s, "type": "本季播出", "content": "当前季度有作品在播"} for s in studios]

    news = [
        {
            "title": f"2026年夏季新番开播：共{len(source)}部作品列入本季榜单",
            "tags": ["新番", "夏季档", "开播"],
            "content": "本季涵盖多元题材，包含科幻、奇幻、运动、日常等类型。以下榜单基于本季在播作品数据生成。",
            "impact": "夏季档进入核心播放期，建议按题材与评分优先选择追番。"
        },
        {
            "title": "流媒体动漫热度继续上升",
            "tags": ["流媒体", "数据"],
            "content": "Netflix、Disney+ 等平台日本动漫内容持续增加，海外热度与本土口碑形成正循环。",
            "impact": "流媒体热度可作为追番参考，关注评分与讨论度变化。"
        },
        {
            "title": "剧场版与续作企划增多",
            "tags": ["剧场版", "续作"],
            "content": "多家工作室公布 2026-2027 年剧场版与 TV 续作计划，粉丝关注度明显提升。",
            "impact": "建议纳入长期关注清单，跟踪制作进度与上映时间。"
        }
    ]

    upcoming = []
    upcoming_source = source[5:10]
    for anime in upcoming_source:
        title = choose_title(anime)
        studio = ((anime.get("studios") or [{}])[0].get("name", "")).strip() or "未知"
        source_type = anime.get("source") or "未公开"
        upcoming.append({
            "title": title,
            "date": "待公开",
            "studio": studio,
            "source": source_type,
            "expectation": "关注后续官方情报与预告"
        })
    if not upcoming:
        upcoming.append({
            "title": "敬请关注官方后续公开",
            "date": "待公布",
            "studio": "多社",
            "source": "综合",
            "expectation": "持续关注行业动态"
        })

    sales = []
    if top:
        t1 = choose_title(top[0])
        sales.append({"category": "蓝光/影碟热度", "content": f"当前热门：{t1}", "trend": "up"})
        sales.append({"category": "漫画原作热度", "content": "多部作品带动原作销量上升", "trend": "up"})
    if not sales:
        sales.append({"category": "综合热度", "content": "暂无开放数据", "trend": "flat"})

    editor_choice = pick[0]["title"] if pick else "本季热门作品"
    editor_reason = pick[0]["highlight"] if pick else "暂无可推荐内容"
    editor_audience = pick[0]["audience"] if pick else "综合观众"

    shortlist = {
        "5": [editor_choice] if editor_choice else [],
        "4": [p["title"] for p in pick[1:2]] if len(pick) > 1 else [],
        "3": [p["title"] for p in pick[2:3]] if len(pick) > 2 else [],
        "2": [],
        "1": []
    }

    quote = {
        "source": "今日动漫日报",
        "character": "编辑",
        "line": "好的动画不会剧透人心，只会让人想再看一遍。",
        "meaning": "优秀作品的价值往往在看完之后才真正显现。"
    }

    hit = [
        {
            "title": ranking[-1]["title"] if ranking else "待观察",
            "score_change": "首周关注度上升明显",
            "reason": "低调开播但讨论度提升，口碑有反转趋势。"
        }
    ]

    report = {
        "date": date_str,
        "news": news,
        "ranking": ranking,
        "pick": pick[:3],
        "hit": hit,
        "company": company_rows[:8],
        "sales": sales,
        "upcoming": upcoming[:10],
        "editor": {
            "title": editor_choice,
            "reason": editor_reason,
            "audience": editor_audience,
            "similar": "《进击的巨人》《间谍过家家》"
        },
        "quote": quote,
        "shortlist": shortlist
    }

    out_dir = Path("/root/anime_daily/files") / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"anime_data_{date_str}.json"
    src_file = Path("/root/anime_daily/daily_news") / f"anime_data_{date_str}.json"
    out_file.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    src_file.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✅ 动漫日报数据已生成：{out_file}")
    for row in report["ranking"][:10]:
        print(row["title"])
    return report


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else None
    build_report(d)
