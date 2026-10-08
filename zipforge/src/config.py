# -*- coding: utf-8 -*-
"""
config.py — 持久化用户偏好（无广告、纯本地、不联网）。

ZipForge 的原则：不收集任何数据、不联网、不弹广告。
偏好仅保存在本机用户目录下的一个 JSON 文件里（压缩默认格式、级别、
线程数等），密码绝不保存明文（仅本次会话内存中可用）。
"""
import json
import os
from pathlib import Path

CONFIG_PATH = Path.home() / ".zipforge" / "prefs.json"

DEFAULTS = {
    "default_format": "7z",
    "default_level": 5,
    "threads": 0,            # 0 = 自动（=CPU 核数）
    "solid": True,
    "encrypt_header": False,
    "overwrite": "ask",
    "last_dir": None,        # 上次浏览的目录
    "window_geometry": "1100x720",
    # —— 外观主题 ——
    # ui_theme: 主题键名（见 src/themes.py），默认 "classic"
    "ui_theme": "classic",
    # —— 右键菜单集成 ——
    # context_menu: "auto"    = 允许自动安装（首次启动即装，可自动修复）
    #                "removed" = 用户主动移除过，不再自动安装
    "context_menu": "auto",
    "context_menu_exe": None,        # 上次安装时指向的 exe；路径变化则自动修复
    "context_menu_notified": False,  # 是否已提示过「已自动集成」
}


def load_prefs() -> dict:
    try:
        if CONFIG_PATH.exists():
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            merged = dict(DEFAULTS)
            merged.update({k: v for k, v in data.items() if k in DEFAULTS})
            return merged
    except Exception:
        pass
    return dict(DEFAULTS)


def save_prefs(prefs: dict):
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        # 只保存已知键，避免堆积垃圾
        safe = {k: prefs.get(k, DEFAULTS[k]) for k in DEFAULTS}
        CONFIG_PATH.write_text(json.dumps(safe, indent=2, ensure_ascii=False),
                               encoding="utf-8")
    except Exception:
        pass


def fmt_size(n) -> str:
    """人类可读的文件大小。"""
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "-"
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    i = 0
    while n >= 1024 and i < len(units) - 1:
        n /= 1024.0
        i += 1
    if i == 0:
        return f"{int(n)} {units[i]}"
    return f"{n:.1f} {units[i]}"


def fmt_attr(attr: str) -> str:
    """把 7z 的 Attributes 字符串转成 D/R 之类简短标记。"""
    if not attr:
        return ""
    out = ""
    if "D" in attr:
        out += "D"  # 目录
    if "R" in attr:
        out += "R"  # 只读
    if "H" in attr:
        out += "H"  # 隐藏
    if "S" in attr:
        out += "S"  # 系统
    if "A" in attr:
        out += "A"  # 存档
    return out
