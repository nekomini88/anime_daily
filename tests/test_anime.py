# -*- coding: utf-8 -*-
"""anime_daily 核心逻辑测试：HTML→TG 转换、分块、LLM JSON 解析"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from send_tg_report import html_to_tg, split_chunks
from generate_anime_llm import _parse_json


class TestHtmlToTg:
    """HTML → Telegram 纯文本转换测试"""

    def test_strip_html_tags(self):
        # 通用 HTML 标签（h1/p/i）被剥离
        out = html_to_tg("<h1>标题</h1><p>内容</p>")
        assert "<h1>" not in out and "<p>" not in out
        assert "标题" in out and "内容" in out

    def test_strip_scripts(self):
        out = html_to_tg("正文<script>alert(1)</script>更多")
        assert "script" not in out.lower()

    def test_keep_tg_bold(self):
        # <b> 保留为 Telegram 加粗格式
        out = html_to_tg("<b>加粗</b> 和 <i>斜体</i>")
        assert "<b>" in out

    def test_contains_text(self):
        out = html_to_tg("<h1>标题</h1><p>内容</p>")
        assert "标题" in out
        assert "内容" in out


class TestSplitChunks:
    """分块测试"""

    def test_short_text(self):
        chunks = split_chunks("短文本")
        assert len(chunks) == 1
        assert chunks[0] == "短文本"

    def test_empty(self):
        assert split_chunks("") == []

    def test_long_text_chunked(self):
        long_text = "段落\n\n<b>标题</b>\n\n内容" * 300
        chunks = split_chunks(long_text)
        assert len(chunks) >= 2


class TestParseJson:
    """LLM 输出 JSON 解析测试"""

    def test_parse_valid_json(self):
        assert _parse_json('{"a": 1}') == {"a": 1}

    def test_parse_with_markdown_fence(self):
        assert _parse_json('```json\n{"a": 1}\n```') == {"a": 1}

    def test_parse_with_code_fence(self):
        assert _parse_json('```\n{"b": 2}\n```') == {"b": 2}

    def test_parse_invalid_raises(self):
        import pytest
        with pytest.raises(ValueError):
            _parse_json("不是json")

    def test_parse_extra_text(self):
        result = _parse_json('说明文字\n{"c": 3}')
        assert result is None or result.get("c") == 3
