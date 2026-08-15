# -*- coding: utf-8 -*-
"""generate_anime_llm.py 纯逻辑测试：
API Key 加载、_call_zen 请求/响应解析、generate_content 数据→提示词组装。
LLM 联网调用全部 monkeypatch，不触网不调真模型。"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import generate_anime_llm as gen


def _make_path_stubs(exists=True, content=""):
    """构造 _load_api_key 所需的 Path/BASE 桩：固定路径文件全部指向同一 FakeFile"""

    class FakeFile:
        def __init__(s):
            s._exists = exists
            s._content = content

        def exists(s):
            return s._exists

        def read_text(s, encoding="utf-8"):
            return s._content

        def expanduser(s):
            return s

    f = FakeFile()

    class FakePath:
        def __init__(s, *a):
            pass

        def __call__(s, *a):
            return f

        def exists(s):
            return f.exists()

        def read_text(s, encoding="utf-8"):
            return f.read_text(encoding=encoding)

        def expanduser(s):
            return s

    class FakeBase:
        def __truediv__(s, other):
            return f

    return FakePath, FakeBase


class TestLoadApiKey:
    """API Key 读取：.env 文件解析 / 环境变量回退 / 无 Key"""

    def test_env_fallback(self, monkeypatch):
        fake_path, fake_base = _make_path_stubs(exists=False)
        monkeypatch.setattr(gen, "Path", fake_path)
        monkeypatch.setattr(gen, "BASE", fake_base())
        monkeypatch.setenv("OPENCODE_ZEN_API_KEY", "env-key-123")
        assert gen._load_api_key() == "env-key-123"

    def test_env_missing_returns_none(self, monkeypatch):
        fake_path, fake_base = _make_path_stubs(exists=False)
        monkeypatch.setattr(gen, "Path", fake_path)
        monkeypatch.setattr(gen, "BASE", fake_base())
        monkeypatch.delenv("OPENCODE_ZEN_API_KEY", raising=False)
        assert gen._load_api_key() is None

    def test_reads_key_from_env_file(self, monkeypatch):
        content = 'FOO=1\nOPENCODE_ZEN_API_KEY="quoted-key"\nBAR=2\n'
        fake_path, fake_base = _make_path_stubs(exists=True, content=content)
        monkeypatch.setattr(gen, "Path", fake_path)
        monkeypatch.setattr(gen, "BASE", fake_base())
        monkeypatch.delenv("OPENCODE_ZEN_API_KEY", raising=False)
        assert gen._load_api_key() == "quoted-key"  # 双引号被剥离

    def test_ignores_unrelated_lines(self, monkeypatch):
        fake_path, fake_base = _make_path_stubs(exists=True, content="SOME_OTHER=1\n")
        monkeypatch.setattr(gen, "Path", fake_path)
        monkeypatch.setattr(gen, "BASE", fake_base())
        monkeypatch.delenv("OPENCODE_ZEN_API_KEY", raising=False)
        assert gen._load_api_key() is None


class TestCallZen:
    """LLM 调用（requests 打桩）：正常返回 / reasoning 回退 / 缺 Key / 网络异常"""

    def test_success_returns_content(self, monkeypatch):
        monkeypatch.setattr(gen, "_load_api_key", lambda: "k")

        class FakeResp:
            def raise_for_status(s):
                pass

            def json(s):
                return {"choices": [{"message": {"content": '{"ok": 1}'}}]}

        monkeypatch.setattr(gen.requests, "post", lambda *a, **k: FakeResp())
        assert gen._call_zen("sys", "user") == '{"ok": 1}'

    def test_falls_back_to_reasoning_content(self, monkeypatch):
        monkeypatch.setattr(gen, "_load_api_key", lambda: "k")

        class FakeResp:
            def raise_for_status(s):
                pass

            def json(s):
                return {"choices": [{"message": {"content": "",
                                                 "reasoning_content": '{"r": 2}'}}]}

        monkeypatch.setattr(gen.requests, "post", lambda *a, **k: FakeResp())
        assert gen._call_zen("sys", "user") == '{"r": 2}'

    def test_missing_key_raises(self, monkeypatch):
        monkeypatch.setattr(gen, "_load_api_key", lambda: None)
        with pytest.raises(RuntimeError):
            gen._call_zen("sys", "user")

    def test_network_error_propagates(self, monkeypatch):
        monkeypatch.setattr(gen, "_load_api_key", lambda: "k")

        def boom(*a, **k):
            raise ConnectionError("net down")

        monkeypatch.setattr(gen.requests, "post", boom)
        with pytest.raises(ConnectionError):
            gen._call_zen("sys", "user")


DATA = {
    "ranking": [
        {"rank": 1, "title": "榜首番", "genre": "Action", "score": 85.0, "heat": 70.0,
         "episodes": 12, "studio": "Studio A", "all_genres": ["Action", "Fantasy"]},
        {"rank": 2, "title": "第二名", "genre": "Comedy", "score": 80.0, "heat": 60.0,
         "episodes": 24, "studio": "Studio B", "all_genres": ["Comedy"]},
    ],
    "studios": ["Studio A", "Studio B"],
}


class TestGenerateContent:
    """generate_content：真实数据 → 提示词组装 → JSON 解析（_call_zen 打桩）"""

    def test_prompt_built_from_real_data(self, monkeypatch):
        captured = {}

        def fake_call(system, user, max_tokens=4000, temperature=0.7):
            captured["system"] = system
            captured["user"] = user
            return json.dumps({"news": [], "quote": {}, "editor": {}})

        monkeypatch.setattr(gen, "_call_zen", fake_call)
        out = gen.generate_content(DATA, "2026-08-15")

        assert out == {"news": [], "quote": {}, "editor": {}}
        assert "2026-08-15" in captured["user"]       # 日期写入提示词
        assert "榜首番" in captured["user"]            # 榜单真实标题
        assert "Studio A" in captured["user"]          # 制作公司
        assert "Studio B" in captured["user"]
        assert "Action" in captured["user"]            # 类型
        assert "专业的日本动漫行业日报编辑" in captured["system"]

    def test_llm_garbage_raises(self, monkeypatch):
        monkeypatch.setattr(gen, "_call_zen", lambda *a, **k: "not json at all")
        with pytest.raises(ValueError):
            gen.generate_content(DATA, "2026-08-15")

    def test_empty_data_does_not_crash(self, monkeypatch):
        monkeypatch.setattr(gen, "_call_zen", lambda *a, **k: '{"news": []}')
        out = gen.generate_content({}, "2026-08-15")
        assert out == {"news": []}
