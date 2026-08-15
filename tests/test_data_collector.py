# -*- coding: utf-8 -*-
"""scripts/anime_data_collector.py 纯逻辑测试：
标题清洗/候选/选择、评分热度归一化、季度映射、build_report 归一化与排序。
联网函数（_post_json/_jikan_get/_anilist_media/_jikan_media）全部打桩，不触网。"""
import json
import os
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scripts.anime_data_collector as ac


class TestNormalizeCandidate:
    """标题清洗纯函数"""

    def test_lowercase_and_mu(self):
        assert ac._normalize_candidate("μ'sic") == "music"

    def test_punctuation_to_space(self):
        assert ac._normalize_candidate("A:B-C~D") == "a b c d"

    def test_roman_numeral_2(self):
        # 已知缺陷：源码先 lower() 再 replace("Ⅱ")，U+2161 已被 lower 成
        # 小写 ⅱ(U+2171)，replace 永远不命中 → 锁定当前真实输出
        assert ac._normalize_candidate("AttackⅡ") == "attackⅱ"

    def test_collapse_and_strip_spaces(self):
        # replace("  "," ") 只做一次：3 个连续空格只塌缩到 2 个
        assert ac._normalize_candidate("  A  B  ") == "a b"
        assert ac._normalize_candidate("  A   B  ") == "a  b"

    def test_empty_and_none(self):
        assert ac._normalize_candidate("") == ""
        assert ac._normalize_candidate(None) == ""


class TestTitleCandidates:
    """AniList dict 标题 / Jikan str 标题兼容"""

    def test_anilist_dict_title(self):
        m = {"title": {"romaji": "A", "english": "B", "native": "C"}}
        assert ac._title_candidates(m) == ["A", "B", "C", None]

    def test_jikan_str_title(self):
        m = {"title": "A", "title_japanese": "B"}
        assert ac._title_candidates(m) == ["A", "B"]

    def test_no_title(self):
        assert ac._title_candidates({}) == [None, None]


class TestChooseTitle:
    """标题选择：缓存命中 > 中文覆盖表 > 首个候选 > 未知兜底"""

    def test_override_applied(self, monkeypatch):
        monkeypatch.setattr(ac, "_zh_cache", {})
        monkeypatch.setattr(ac, "_TITLE_OVERRIDES", {"Youjo Senki II": "幼女战记 II"})
        m = {"idMal": 9, "title": {"romaji": "Youjo Senki II", "english": None,
                                   "native": "幼女戦記 II"}}
        assert ac.choose_title(m) == "幼女战记 II"

    def test_fallback_first_candidate(self, monkeypatch):
        monkeypatch.setattr(ac, "_zh_cache", {})
        monkeypatch.setattr(ac, "_TITLE_OVERRIDES", {})
        m = {"idMal": 9, "title": {"romaji": "Alpha", "english": "Alpha EN",
                                   "native": "アルファ"}}
        assert ac.choose_title(m) == "Alpha"

    def test_cache_hit(self, monkeypatch):
        monkeypatch.setattr(ac, "_zh_cache", {10: "已缓存名"})
        m = {"idMal": 10, "title": {"romaji": "Whatever"}}
        assert ac.choose_title(m) == "已缓存名"

    def test_no_title_raises_stopiteration(self, monkeypatch):
        # 已知缺陷：candidates 为空时 next(iter([])) 抛 StopIteration，
        # 并不会走到"未知作品"兜底（未修源码，测试锁定当前行为）
        monkeypatch.setattr(ac, "_zh_cache", {})
        monkeypatch.setattr(ac, "_TITLE_OVERRIDES", {})
        with pytest.raises(StopIteration):
            ac.choose_title({"idMal": 1})


class TestNormScore:
    """评分归一化：None→0、字符串、四舍五入、非法值兜底"""

    def test_none_to_zero(self):
        assert ac._norm_score(None) == 0.0

    def test_round_to_one_decimal(self):
        assert ac._norm_score(85.66) == 85.7

    def test_numeric_string(self):
        assert ac._norm_score("90") == 90.0

    def test_invalid_to_zero(self):
        assert ac._norm_score("abc") == 0.0


class TestNormHeat:
    """热度公式：pop*0.01 + fav*0.5，四舍五入到 1 位小数"""

    def test_formula(self):
        assert ac._norm_heat(1000, 20) == 20.0  # 10 + 10

    def test_none_to_zero(self):
        assert ac._norm_heat(None, None) == 0.0

    def test_rounding(self):
        assert ac._norm_heat(333, 7) == 6.8  # 3.33 + 3.5 = 6.83 → 6.8


# 模拟 AniList 返回的 media 条目（含 Jikan 风格 str title 兼容样例）
ANILIST_FIXTURE = [
    {"id": 1, "idMal": 101, "title": {"romaji": "Alpha", "english": "Alpha EN",
                                      "native": "アルファ"},
     "averageScore": 85, "popularity": 1000, "favourites": 20, "episodes": 12,
     "source": "MANGA", "status": "RELEASING", "format": "TV",
     "genres": ["Action", "Fantasy"], "studios": {"nodes": [{"name": "Studio A"}]}},
    {"id": 2, "idMal": 102, "title": {"romaji": "Beta", "english": None, "native": "ベータ"},
     "averageScore": None, "score": 7.5, "popularity": 500, "favourites": 0, "episodes": None,
     "source": None, "status": "RELEASING", "format": "TV",
     "genres": [], "studios": {"nodes": []}},
    {"id": 3, "mal_id": 103, "title": "Gamma",
     "averageScore": 90, "popularity": 2000, "favourites": 100, "episodes": 24,
     "source": "ORIGINAL", "status": "RELEASING", "format": "TV",
     "genres": ["Comedy"], "studios": {"nodes": [{"name": "Studio C"}]}},
]


class TestAnilistMedia:
    """AniList 请求参数：季度映射（12 个月全覆盖）+ 解析失败兜底"""

    def test_season_mapping_all_months(self, monkeypatch):
        captured = {}

        def fake_post(url, payload, headers=None, timeout=25):
            captured["payload"] = payload
            return {"data": {"Page": {"media": [{"id": 1}]}}}

        monkeypatch.setattr(ac, "_post_json", fake_post)
        expected = {1: "WINTER", 2: "WINTER", 3: "WINTER",
                    4: "SPRING", 5: "SPRING", 6: "SPRING",
                    7: "SUMMER", 8: "SUMMER", 9: "SUMMER",
                    10: "FALL", 11: "FALL", 12: "FALL"}
        for month, season in expected.items():
            class FakeDT:
                @classmethod
                def now(cls, tz, _m=month):
                    return datetime(2026, _m, 1, tzinfo=tz)

            monkeypatch.setattr(ac, "datetime", FakeDT)
            media = ac._anilist_media(limit=5)
            assert media == [{"id": 1}]
            assert captured["payload"]["variables"]["season"] == season
            assert captured["payload"]["variables"]["year"] == 2026
            assert captured["payload"]["variables"]["per"] == 5

    def test_parse_failure_returns_empty(self, monkeypatch):
        monkeypatch.setattr(ac, "_post_json", lambda *a, **k: {})

        class FakeDT:
            @classmethod
            def now(cls, tz):
                return datetime(2026, 8, 1, tzinfo=tz)

        monkeypatch.setattr(ac, "datetime", FakeDT)
        assert ac._anilist_media() == []


class TestJikanMedia:
    """Jikan 备用源：透传列表 / 非列表兜底"""

    def test_returns_list(self, monkeypatch):
        monkeypatch.setattr(ac, "_jikan_get", lambda path, params: [{"title": "X"}])
        assert ac._jikan_media(15) == [{"title": "X"}]

    def test_non_list_returns_empty(self, monkeypatch):
        monkeypatch.setattr(ac, "_jikan_get", lambda path, params: {})
        assert ac._jikan_media() == []


class TestBuildReport:
    """build_report：归一化、热度排序、rank 分配、写文件、AniList→Jikan 回退"""

    def test_normalize_sort_and_rank(self, monkeypatch, redirect_project_paths):
        redirect_project_paths(ac)
        monkeypatch.setattr(ac, "_zh_cache", {})
        monkeypatch.setattr(ac, "_TITLE_OVERRIDES", {})
        monkeypatch.setattr(ac, "_anilist_media", lambda limit=20: ANILIST_FIXTURE)

        report = ac.build_report("2026-07-01")

        assert report["date"] == "2026-07-01"
        assert report["source"] == "AniList"
        ranking = report["ranking"]
        # 热度降序: Gamma(70.0) > Alpha(20.0) > Beta(5.0)
        assert [r["title"] for r in ranking] == ["Gamma", "Alpha", "Beta"]
        assert [r["rank"] for r in ranking] == [1, 2, 3]
        assert [r["heat"] for r in ranking] == [70.0, 20.0, 5.0]
        # 归一化细节
        assert ranking[1]["score"] == 85.0
        assert ranking[2]["score"] == 7.5      # averageScore 缺失时回退 score
        assert ranking[2]["genre"] == "综合"     # 无类型兜底
        assert ranking[0]["studio"] == "Studio C"
        assert ranking[1]["studio"] == "Studio A"
        assert report["studios"] == ["Studio C", "Studio A"]  # 去重且按热度序
        assert report["genres"] == ["Action", "Comedy", "Fantasy"]
        assert report["all_ranking"] == ranking

    def test_writes_data_file(self, monkeypatch, redirect_project_paths):
        tmp = redirect_project_paths(ac)
        monkeypatch.setattr(ac, "_anilist_media", lambda limit=20: ANILIST_FIXTURE)

        report = ac.build_report("2026-07-02")

        data_file = tmp / "daily_news" / "anime_data_2026-07-02.json"
        assert data_file.exists()
        data = json.loads(data_file.read_text(encoding="utf-8"))
        assert data["date"] == "2026-07-02"
        assert len(data["ranking"]) == 3
        assert (tmp / "files" / "2026-07-02").is_dir()
        assert report["date"] == "2026-07-02"

    def test_fallback_to_jikan(self, monkeypatch, redirect_project_paths):
        redirect_project_paths(ac)
        monkeypatch.setattr(ac, "_anilist_media", lambda limit=20: [])
        monkeypatch.setattr(ac, "_jikan_media", lambda limit=15: [{
            "id": 9, "idMal": 9, "title": {"romaji": "JikanAnime", "english": None,
                                           "native": "ジカン"},
            "averageScore": 80, "popularity": 900, "favourites": 10, "episodes": 12,
            "source": "MANGA", "status": "RELEASING", "format": "TV",
            "genres": ["Action"], "studios": {"nodes": [{"name": "Studio J"}]}}])

        report = ac.build_report("2026-07-03")

        assert report["source"] == "Jikan"
        assert report["ranking"][0]["title"] == "JikanAnime"
        assert report["ranking"][0]["heat"] == 14.0  # 900*0.01 + 10*0.5

    def test_both_sources_empty_returns_none(self, monkeypatch, redirect_project_paths):
        redirect_project_paths(ac)
        monkeypatch.setattr(ac, "_anilist_media", lambda limit=20: [])
        monkeypatch.setattr(ac, "_jikan_media", lambda limit=15: [])
        assert ac.build_report("2026-07-04") is None

    def test_top10_and_studio_limit(self, monkeypatch, redirect_project_paths):
        redirect_project_paths(ac)
        monkeypatch.setattr(ac, "_zh_cache", {})
        monkeypatch.setattr(ac, "_TITLE_OVERRIDES", {})
        media = []
        for i in range(12):
            media.append({"id": i, "idMal": i,
                          "title": {"romaji": f"Title{i}", "english": None, "native": ""},
                          "averageScore": 50 + i, "popularity": 1000 - i, "favourites": 0,
                          "episodes": 12, "source": None, "status": "RELEASING", "format": "TV",
                          "genres": [f"G{i}"],
                          "studios": {"nodes": [{"name": f"Studio{i}"}]}})
        monkeypatch.setattr(ac, "_anilist_media", lambda limit=20: media)

        report = ac.build_report("2026-07-05")

        assert len(report["ranking"]) == 10     # 只保留 TOP10
        assert len(report["all_ranking"]) == 12
        assert report["ranking"][0]["title"] == "Title0"  # 热度 10.0 最高
        assert "Title10" not in [r["title"] for r in report["ranking"]]
        assert len(report["studios"]) == 8      # 工作室去重后最多 8 个
