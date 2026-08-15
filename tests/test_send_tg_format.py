# -*- coding: utf-8 -*-
"""send_tg_report.py 报告格式化纯函数测试：
表格生成（<pre> 等宽块 + | 分隔）、HTML 清洗（body 截取/去重/实体解码）、
split_chunks 分块边界与字数限制（不联网，纯字符串处理）"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from send_tg_report import CHUNK_LIMIT, html_to_tg, split_chunks


class TestHtmlToTgTable:
    """表格 → <pre> 等宽块（报告格式化的核心能力）"""

    def test_table_rows_joined_with_pipe(self):
        html = ("<table><tr><th>排名</th><th>作品</th></tr>"
                "<tr><td>1</td><td>芙莉莲</td></tr></table>")
        out = html_to_tg(html)
        assert "<pre>" in out and "</pre>" in out
        assert "排名 | 作品" in out
        assert "1 | 芙莉莲" in out

    def test_table_cell_tags_stripped(self):
        html = '<table><tr><td><b>1</b></td><td><a href="x">链接</a></td></tr></table>'
        out = html_to_tg(html)
        assert "<b>1</b>" not in out
        assert "<a" not in out
        assert "链接" in out

    def test_table_entities_decoded(self):
        html = "<table><tr><td>A&amp;B &lt;C&gt;</td></tr></table>"
        out = html_to_tg(html)
        assert "A&B <C>" in out


class TestHtmlToTgClean:
    """清洗：body 截取、标题去重、script/style 移除、实体解码、空行折叠"""

    def test_only_body_kept(self):
        html = ("<html><head><title>日本动漫番剧日报</title></head>"
                "<body><p>正文内容</p></body></html>")
        out = html_to_tg(html)
        # <head> 里的 <title> 不进入正文，最终只保留 header 一处标题
        assert out.count("日本动漫番剧日报") == 1
        assert "正文内容" in out

    def test_content_before_title_mark_dropped(self):
        html = "<body>杂项文字 日本动漫番剧日报 <p>真正内容</p></body>"
        out = html_to_tg(html)
        assert "杂项文字" not in out
        assert "真正内容" in out

    def test_style_removed(self):
        out = html_to_tg("<body><style>body{color:red}</style><p>正文</p></body>")
        assert "color:red" not in out

    def test_entity_and_percent_decode(self):
        out = html_to_tg("<body><p>50%% &amp; &nbsp; &lt;x&gt;</p></body>")
        assert "50%" in out
        assert "&amp;" not in out

    def test_blank_lines_collapsed(self):
        out = html_to_tg("<body><p>第一段</p>\n\n\n\n\n<p>第二段</p></body>")
        assert "\n\n\n" not in out

    def test_header_and_footer_wrapped(self):
        out = html_to_tg("<body>日本动漫番剧日报\n<p>内容</p></body>")
        assert out.startswith("<b>📺 日本动漫番剧日报</b>")
        assert "数据源" in out

    def test_char_count_sanity(self):
        # 字数统计口径（len）：大量标签清洗后，输出应显著短于原始 HTML
        html = "<body>日本动漫番剧日报\n" + \
               "".join(f"<p>第{i}段 &amp; 内容</p><br>" for i in range(200)) + "</body>"
        out = html_to_tg(html)
        assert len(out) < len(html)
        assert len(out) > 100


class TestSplitChunks:
    """分块：长度上限、续段前缀、按段落/加粗边界切分"""

    def test_within_limit_single_chunk(self):
        text = "短文本" * 100
        chunks = split_chunks(text)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_hard_cut_no_newline(self):
        # 没有任何换行/加粗边界 → 硬切到 CHUNK_LIMIT
        text = "x" * (CHUNK_LIMIT * 2 + 100)
        chunks = split_chunks(text)
        assert len(chunks) == 3
        assert chunks[0] == "x" * CHUNK_LIMIT
        assert chunks[-1] == "x" * 100

    def test_split_at_blank_line(self):
        # 有段落边界（\n\n）则优先在段落处切
        text = "a" * 3000 + "\n\n" + "b" * 3000
        chunks = split_chunks(text)
        assert len(chunks) == 2
        assert chunks[0] == "a" * 3000
        assert "b" not in chunks[0]
        assert chunks[1].strip() == "b" * 3000

    def test_split_prefers_bold_boundary(self):
        # 存在 \n\n<b> 加粗边界时优先按它切（保住下一段标题）
        text = "a" * 2000 + "\n\n<b>标题B</b>\n\n" + "b" * 2000
        chunks = split_chunks(text)
        assert len(chunks) == 2
        assert chunks[0] == "a" * 2000
        assert "<b>标题B</b>" in chunks[1]

    def test_continuation_prefix(self):
        # 非首段带"（续）"前缀，且每段不超过上限+前缀长度
        text = "p" * CHUNK_LIMIT + "\n\n" + "q" * CHUNK_LIMIT
        chunks = split_chunks(text)
        assert len(chunks) == 3
        assert "（续）" not in chunks[0]
        assert chunks[1].startswith("<b>📺 日本动漫番剧日报（续）</b>")
        assert chunks[2] == "qq"

    def test_each_chunk_within_char_limit(self):
        # 字数上限：所有分块 ≤ CHUNK_LIMIT + 续段前缀（约 22 字符，留 40 余量）
        text = ("段落甲\n\n<b>标题</b>\n\n" + "长" * 800) * 30
        chunks = split_chunks(text)
        assert len(chunks) >= 2
        for c in chunks:
            assert len(c) <= CHUNK_LIMIT + 40
            assert c.strip()
