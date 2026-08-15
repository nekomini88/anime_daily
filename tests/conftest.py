# -*- coding: utf-8 -*-
"""共享 fixture：把被测模块内 hardcode 的 /root/anime_daily 绝对路径重定向到
pytest 的 tmp_path，避免测试把 files/、daily_news/、config.ini 写入真实项目目录。"""
import pathlib

import pytest

ROOT_PREFIX = "/root/anime_daily"


@pytest.fixture
def redirect_project_paths(monkeypatch, tmp_path):
    """monkeypatch 指定模块的 Path，把 /root/anime_daily 前缀映射到 tmp_path。

    用法: tmp = redirect_project_paths(模块对象)   # 返回 tmp_path
    """
    real_path = pathlib.Path

    def _apply(module):
        class RedirectPath:
            def __new__(cls, *args):
                p = real_path(*args)
                s = str(p)
                if s == ROOT_PREFIX or s.startswith(ROOT_PREFIX + "/"):
                    s = str(tmp_path) + s[len(ROOT_PREFIX):]
                    return real_path(s)
                return p

        monkeypatch.setattr(module, "Path", RedirectPath)
        return tmp_path

    return _apply
