# -*- coding: utf-8 -*-
"""send_report_email.py 纯逻辑测试：
send_email 邮件组装/主题推导（SMTP 打桩，不真发信）、load_email_config 配置解析（路径重定向）。"""
import os
import sys
from email import message_from_string
from email.header import decode_header

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import send_report_email as sre

BASIC_CFG = {
    "smtp_server": "smtp.test.com", "smtp_port": 465,
    "sender_email": "a@b.c", "sender_pass": "pw",
    "recipient": "r@b.c", "sender_name": "测试机器人",
}


class FakeSMTP:
    """模拟 smtplib.SMTP_SSL，捕获 login / sendmail 参数"""
    instances = []

    def __init__(self, server, port):
        self.server = server
        self.port = port
        self.login_args = None
        self.sent = None
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, user, pw):
        self.login_args = (user, pw)

    def sendmail(self, sender, to, msg):
        self.sent = (sender, to, msg)


def _parse_msg(raw):
    """把 MIME 原文解析为 email.message，自动解码 RFC2047 头/base64 body"""
    return message_from_string(raw)


def _part_text(msg, subtype):
    """取 multipart/alternative 中指定子类型的正文"""
    for part in msg.get_payload():
        if part.get_content_type() == f"text/{subtype}":
            return part.get_payload(decode=True).decode("utf-8")
    return ""


def _decoded(value):
    """解码 RFC2047 编码的邮件头（如 Subject/From）"""
    return "".join(
        part.decode(enc or "utf-8") if isinstance(part, bytes) else part
        for part, enc in decode_header(value)
    )


class TestSendEmail:
    """SMTP 打桩验证：主题推导、From 头、HTML 标志、失败回退"""

    def test_subject_from_first_line(self, monkeypatch):
        FakeSMTP.instances.clear()
        monkeypatch.setattr(sre.smtplib, "SMTP_SSL", FakeSMTP)

        ok = sre.send_email("第一行标题\n正文内容", config=BASIC_CFG)

        assert ok is True
        inst = FakeSMTP.instances[-1]
        assert inst.server == "smtp.test.com" and inst.port == 465
        assert inst.login_args == ("a@b.c", "pw")
        sender, to, msg = inst.sent
        assert to == "r@b.c"
        parsed = _parse_msg(msg)
        assert _decoded(parsed["Subject"]) == "第一行标题"  # 主题取正文首行
        assert _decoded(parsed["From"]) == "测试机器人 <a@b.c>"  # formataddr
        assert "正文内容" in _part_text(parsed, "plain")

    def test_html_flag_sets_content_type(self, monkeypatch):
        FakeSMTP.instances.clear()
        monkeypatch.setattr(sre.smtplib, "SMTP_SSL", FakeSMTP)
        cfg = dict(BASIC_CFG, sender_name="")

        sre.send_email("<p>html</p>", subject="主题", is_html=True, config=cfg)

        msg = FakeSMTP.instances[-1].sent[2]
        parsed = _parse_msg(msg)
        assert _decoded(parsed["Subject"]) == "主题"
        assert "<p>html</p>" in _part_text(parsed, "html")

    def test_plain_default_content_type(self, monkeypatch):
        FakeSMTP.instances.clear()
        monkeypatch.setattr(sre.smtplib, "SMTP_SSL", FakeSMTP)

        sre.send_email("纯文本", config=BASIC_CFG)

        msg = FakeSMTP.instances[-1].sent[2]
        parsed = _parse_msg(msg)
        assert "纯文本" in _part_text(parsed, "plain")

    def test_default_subject_when_first_line_empty(self, monkeypatch):
        FakeSMTP.instances.clear()
        monkeypatch.setattr(sre.smtplib, "SMTP_SSL", FakeSMTP)

        sre.send_email("\n\n", config=BASIC_CFG)

        msg = FakeSMTP.instances[-1].sent[2]
        parsed = _parse_msg(msg)
        assert _decoded(parsed["Subject"]) == "📊 美股收盘日报"  # 首行空白→默认

    def test_send_failure_returns_false(self, monkeypatch):
        class FailingSMTP(FakeSMTP):
            def login(self, user, pw):
                raise OSError("auth failed")

        monkeypatch.setattr(sre.smtplib, "SMTP_SSL", FailingSMTP)
        assert sre.send_email("内容", config=BASIC_CFG) is False


class TestLoadEmailConfig:
    """配置解析：从重定向的临时 config.ini 读取（不碰真实配置/密钥）"""

    def test_parses_config(self, monkeypatch, redirect_project_paths):
        tmp = redirect_project_paths(sre)
        (tmp / "config.ini").write_text(
            "[email]\n"
            "smtp_server = smtp.qq.com\n"
            "smtp_port = 465\n"
            "sender_email = me@qq.com\n"
            "sender_pass = secret\n"
            "recipient = you@x.com\n"
            "sender_name = Bot\n",
            encoding="utf-8")

        cfg = sre.load_email_config()

        assert cfg["smtp_server"] == "smtp.qq.com"
        assert cfg["smtp_port"] == 465
        assert cfg["sender_email"] == "me@qq.com"
        assert cfg["recipient"] == "you@x.com"
        assert cfg["sender_name"] == "Bot"

    def test_missing_sender_name_fallback(self, monkeypatch, redirect_project_paths):
        tmp = redirect_project_paths(sre)
        (tmp / "config.ini").write_text(
            "[email]\n"
            "smtp_server = s\nsmtp_port = 587\n"
            "sender_email = e@x.com\nsender_pass = p\nrecipient = r@x.com\n",
            encoding="utf-8")

        cfg = sre.load_email_config()

        assert cfg["smtp_port"] == 587
        assert cfg["sender_name"] == ""
