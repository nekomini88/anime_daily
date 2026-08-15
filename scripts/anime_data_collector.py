#!/usr/bin/env python3
"""动漫日报数据生成脚本
主数据源：AniList GraphQL（稳定，含真实 热度 favourites/popularity、评分、集数、类型、工作室、来源）
备用数据源：Jikan API v4（AniList 失败时回退）
内容类章节（news/quote/editor/hit/sales）由 generate_anime_llm.py 基于真实数据生成，本脚本只负责真实结构化数据。
"""
import json
import sys
import urllib.request
import urllib.parse
import urllib.error
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

ANILIST_URL = "https://graphql.anilist.co"
JIKAN_BASE = "https://api.jikan.moe/v4"


# ---------- 通用请求 ----------
def _post_json(url, payload, headers=None, timeout=25):
    h = {"User-Agent": "anime-daily-report/1.0", "Content-Type": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"❌ POST failed {url}: {e}", file=sys.stderr)
        return {}


def _jikan_get(path, params, max_attempts=2, retry_delay=2):
    qs = urllib.parse.urlencode(params, doseq=True)
    url = f"{JIKAN_BASE}{path}?{qs}"
    for attempt in range(1, max_attempts + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "anime-daily-report/1.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read())
            d = data.get("data") if isinstance(data, dict) else data
            return d if isinstance(d, list) else []
        except Exception as e:
            print(f"[warn] jikan {url} attempt {attempt}: {e}", file=sys.stderr)
            time.sleep(retry_delay * attempt)
    return []


# ----------标题稳定性（保留现有方案）----------
_zh_cache: dict[int, str] = {}


def load_title_overrides() -> dict[str, str]:
    p = Path(__file__).with_name("title_overrides.json")
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in data.items() if v}
    except Exception as e:
        print(f"❌ load title overrides failed: {e}", file=sys.stderr)
        return {}


_TITLE_OVERRIDES = load_title_overrides()


def _normalize_candidate(text: str) -> str:
    text = (text or "")
    # 先替换罗马数字/特殊字符 (lower() 会把 Ⅱ 变成 ⅱ 导致替换失效)
    text = text.replace("Ⅱ", " 2 ").replace("☆", " ")
    text = text.lower()
    text = text.replace("μ'sic", "music").replace("μ", "u")
    text = text.replace("'", "").replace("'", "").replace(":", " ").replace("-", " ")
    text = text.replace("~", " ").replace("  ", " ").strip()
    return text


def _title_candidates(m):
    """从 AniList media 提取候选标题；兼容 Jikan dict/str title"""
    if isinstance(m, dict) and isinstance(m.get("title"), dict):
        t = m["title"]
        return [t.get("romaji"), t.get("english"), t.get("native"), m.get("title_japanese")]
    if isinstance(m.get("title"), str):
        return [m["title"], m.get("title_japanese")]
    return [m.get("title"), m.get("title_japanese")]


def choose_title(m) -> str:
    mal = m.get("idMal") or m.get("mal_id")
    if mal and mal in _zh_cache:
        return _zh_cache[mal]
    candidates = [c for c in _title_candidates(m) if c]
    if not candidates:
        return "未知作品"
    norm_map = {_normalize_candidate(c): c for c in candidates}
    for key, zh in _TITLE_OVERRIDES.items():
        if _normalize_candidate(key) in norm_map:
            return zh
    return candidates[0]


# ---------- AniList 主数据源 ----------
_ANILIST_SEASON = """
query ($per: Int, $season: MediaSeason, $year: Int) {
  Page(page: 1, perPage: $per) {
    media(type: ANIME, status: RELEASING, season: $season, seasonYear: $year, sort: [POPULARITY_DESC]) {
      id idMal
      title { romaji english native }
      averageScore popularity favourites episodes
      source status format
      genres
      studios { nodes { name } }
      description(asHtml: false)
    }
  }
}
"""


def _anilist_media(limit=20):
    now = datetime.now(timezone(timedelta(hours=8)))
    year = now.year
    month = now.month
    season = {1: "WINTER", 2: "WINTER", 3: "WINTER",
              4: "SPRING", 5: "SPRING", 6: "SPRING",
              7: "SUMMER", 8: "SUMMER", 9: "SUMMER",
              10: "FALL", 11: "FALL", 12: "FALL"}.get(month, "SUMMER")
    payload = {"query": _ANILIST_SEASON, "variables": {
        "per": limit, "season": season, "year": year}}
    data = _post_json(ANILIST_URL, payload)
    try:
        return data["data"]["Page"]["media"]
    except Exception as e:
        print(f"❌ anilist season parse failed: {e}", file=sys.stderr)
        return []


# ---------- Jikan 备用数据源 ----------
def _jikan_media(limit=15):
    data = _jikan_get("/seasons/now", {"limit": limit, "sfw": "true"})
    return data if isinstance(data, list) else []


# ---------- 数据归一化 ----------
def _norm_score(v):
    try:
        return round(float(v or 0), 1)
    except (TypeError, ValueError):
        return 0.0


def _norm_heat(popularity, favourites):
    """热度 = 关注度(权重) + 收藏数，归一化。无数据给 0。"""
    pop = int(popularity or 0)
    fav = int(favourites or 0)
    heat = pop * 0.01 + fav * 0.5
    return round(heat, 1)


def build_report(date_str=None):
    if not date_str:
        date_str = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")

    # 1. 主源 AniList，备用 Jikan
    media = _anilist_media(limit=20)
    source_name = "AniList"
    if not media:
        print("[warn] AniList unavailable, fallback to Jikan", file=sys.stderr)
        media = _jikan_media(limit=15)
        source_name = "Jikan"
    if not media:
        print("⚠️ 两数据源均不可用，本次不生成", file=sys.stderr)
        return None

    # 2. 归一化真实数据 → ranking（真实热度值，无编造）
    ranking = []
    for a in media:
        title = a.get("title") or {}
        if isinstance(title, dict):
            native = title.get("native") or ""
        else:
            native = ""
        genres = [g for g in (a.get("genres") or []) if g]
        # 主制作公司（AniList: nodes[0]; Jikan: 字符串数组）——兼容两种结构
        main_studio = ""
        studios_raw = a.get("studios")
        if isinstance(studios_raw, dict):
            nodes = studios_raw.get("nodes") or []
            if nodes and isinstance(nodes[0], dict):
                main_studio = (nodes[0].get("name") or "").strip()
        elif isinstance(studios_raw, list) and studios_raw:
            main_studio = str(studios_raw[0]).strip()
        score = _norm_score(a.get("averageScore") if a.get("averageScore") is not None else a.get("score"))
        popularity = int(a.get("popularity") or 0)
        favourites = int(a.get("favourites") or 0)
        ranking.append({
            "mal_id": a.get("idMal") or a.get("mal_id"),
            "title": choose_title(a),
            "raw_title": (a.get("title") or {}).get("romaji") if isinstance(a.get("title"), dict) else "",
            "title_japanese": native,
            "genre": (genres[0] if genres else "综合"),
            "all_genres": genres,
            "score": score,
            "heat": _norm_heat(popularity, favourites),
            "popularity": popularity,
            "favourites": favourites,
            "episodes": a.get("episodes"),
            "studio": main_studio,
            "source_media": a.get("source"),
            "status": a.get("status"),
            "trend": "flat",
            "recommend": "",
        })

    # 按热度降序排序
    ranking.sort(key=lambda r: r["heat"], reverse=True)
    for i, r in enumerate(ranking, 1):
        r["rank"] = i

    # 3. studios 列表（真实）
    studios_seen = set()
    studios = []
    for r in ranking:
        s = r["studio"]
        if s and s not in studios_seen:
            studios_seen.add(s)
            studios.append(s)
        if len(studios) >= 8:
            break

    # 4. 组装报告（数字用真实，文字类由 LLM 覆盖）
    report = {
        "date": date_str,
        "source": source_name,
        "ranking": ranking[:10],
        "all_ranking": ranking,
        "studios": studios,
        "genres": sorted({g for r in ranking for g in (r.get("all_genres") or [])})[:12],
    }

    out_dir = Path("/root/anime_daily/files") / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    src_dir = Path("/root/anime_daily/daily_news")
    src_dir.mkdir(parents=True, exist_ok=True)

    blob = json.dumps(report, ensure_ascii=False, indent=2)
    (src_dir / f"anime_data_{date_str}.json").write_text(blob, encoding="utf-8")
    print(f"✅ 动漫日报数据已生成: {src_dir / f'anime_data_{date_str}.json'} (来源 {source_name})")
    for r in ranking[:10]:
        print(f"  {r['rank']}. {r['title']} score={r['score']} heat={r['heat']}")
    return report


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else None
    build_report(d)