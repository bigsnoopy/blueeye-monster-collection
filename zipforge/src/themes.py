# -*- coding: utf-8 -*-
"""
themes.py — ZipForge 主题系统（零第三方依赖）。

把「一套视觉风格」收敛成 tkinter 能直接用的一组颜色 / 字体 / 浮雕属性，
让 gui.py 通过一个字典即可整体换肤，无需为每种风格写分支代码。

主题清单（共 11 套，可在「工具 → 外观主题…」里切换）：
  0  classic    经典（现有默认外观，中性浅色）
  1  neumorphism 软拟物
  2  brutalism  野兽派
  3  glass      玻璃拟态
  4  terminal   复古绿屏终端
  5  cyberpunk  赛博朋克霓虹
  6  swiss      瑞士极简
  7  skeuo      拟物写实
  8  clay       黏土风
  9  memphis    孟菲斯
 10  vaporwave  蒸汽波
"""

# 每个主题字段说明：
#   bg            应用整体背景（root）
#   panel         列表 / 树 / 面板背景（Treeview fieldbackground、Frame）
#   fg            正文前景色
#   title         标题栏 / 工具栏 / 菜单背景
#   title_fg      标题栏文字
#   accent        强调色（选中高亮、主按钮底色）
#   accent_fg     强调色上的文字（主按钮文字）
#   btn           次按钮底色
#   btn_fg        次按钮文字
#   border        框架 / 分隔线颜色
#   heading_bg    列表表头底色
#   heading_fg    列表表头文字
#   rowline       列表行分隔线
#   sel_bg        选中行底色
#   sel_fg        选中行文字
#   status_bg     状态栏底色
#   muted         次要文字（说明性文字）
#   font          字体族
#   font_size     基准字号
#   relief        框架浮雕：flat / raised / groove / solid(=raised 加粗)
#   borderwidth   框架边框宽度
#   btn_relief    按钮浮雕
#   btn_bw        按钮边框宽度

DEFAULT_THEME = "classic"

THEMES = {
    "classic": {
        "name": "经典 Classic",
        "bg": "#eceff4", "panel": "#ffffff", "fg": "#1d2330",
        "title": "#ffffff", "title_fg": "#1d2330",
        "accent": "#2f6fdb", "accent_fg": "#ffffff",
        "btn": "#ffffff", "btn_fg": "#1d2330",
        "border": "#d0d5dd", "heading_bg": "#f4f6fa", "heading_fg": "#6b7689",
        "rowline": "#e3e7ee", "sel_bg": "#d6e4ff", "sel_fg": "#10243f",
        "status_bg": "#f4f6fa", "muted": "#7a8499",
        "font": "Segoe UI", "font_size": 10,
        "relief": "flat", "borderwidth": 1, "btn_relief": "flat", "btn_bw": 1,
    },
    "neumorphism": {
        "name": "软拟物 Neumorphism",
        "bg": "#e0e5ec", "panel": "#e0e5ec", "fg": "#5b6472",
        "title": "#e0e5ec", "title_fg": "#5b6472",
        "accent": "#6d7cff", "accent_fg": "#ffffff",
        "btn": "#e0e5ec", "btn_fg": "#6b7689",
        "border": "#e0e5ec", "heading_bg": "#e0e5ec", "heading_fg": "#7a8499",
        "rowline": "#c5ccd6", "sel_bg": "#cfd3ff", "sel_fg": "#3a4470",
        "status_bg": "#e0e5ec", "muted": "#9aa3b2",
        "font": "Segoe UI", "font_size": 10,
        "relief": "flat", "borderwidth": 0, "btn_relief": "flat", "btn_bw": 0,
    },
    "brutalism": {
        "name": "野兽派 Brutalism",
        "bg": "#ffffff", "panel": "#ffffff", "fg": "#111111",
        "title": "#111111", "title_fg": "#ffffff",
        "accent": "#111111", "accent_fg": "#ffffff",
        "btn": "#ffffff", "btn_fg": "#111111",
        "border": "#111111", "heading_bg": "#111111", "heading_fg": "#ffffff",
        "rowline": "#111111", "sel_bg": "#111111", "sel_fg": "#ffffff",
        "status_bg": "#ffffff", "muted": "#444444",
        "font": "Courier New", "font_size": 10,
        "relief": "raised", "borderwidth": 3, "btn_relief": "raised", "btn_bw": 3,
    },
    "glass": {
        "name": "玻璃拟态 Glassmorphism",
        "bg": "#6a11cb", "panel": "#7a4fc8", "fg": "#ffffff",
        "title": "#b9a0e8", "title_fg": "#2e1466",
        "accent": "#ffffff", "accent_fg": "#3a1a6a",
        "btn": "#7a3fd6", "btn_fg": "#ffffff",
        "border": "#ffffff", "heading_bg": "#5e2bb0", "heading_fg": "#ffffff",
        "rowline": "#d9ccf2", "sel_bg": "#c9b8f0", "sel_fg": "#3a1a6a",
        "status_bg": "#8e6fd0", "muted": "#e9e0fb",
        "font": "Segoe UI", "font_size": 10,
        "relief": "flat", "borderwidth": 1, "btn_relief": "flat", "btn_bw": 1,
    },
    "terminal": {
        "name": "复古绿屏终端 Terminal",
        "bg": "#020a02", "panel": "#020a02", "fg": "#33ff66",
        "title": "#0a1a0a", "title_fg": "#33ff66",
        "accent": "#33ff66", "accent_fg": "#021002",
        "btn": "#021002", "btn_fg": "#33ff66",
        "border": "#1f7a3a", "heading_bg": "#0a1a0a", "heading_fg": "#33ff66",
        "rowline": "#1f7a3a", "sel_bg": "#0d2b16", "sel_fg": "#aaffcc",
        "status_bg": "#041204", "muted": "#1f9a4a",
        "font": "Consolas", "font_size": 10,
        "relief": "flat", "borderwidth": 1, "btn_relief": "flat", "btn_bw": 1,
    },
    "cyberpunk": {
        "name": "赛博朋克 Cyberpunk",
        "bg": "#070710", "panel": "#0c0c1a", "fg": "#cfe9ff",
        "title": "#15001f", "title_fg": "#2bf0ff",
        "accent": "#ff2bd6", "accent_fg": "#ffffff",
        "btn": "#15001f", "btn_fg": "#2bf0ff",
        "border": "#ff2bd6", "heading_bg": "#15001f", "heading_fg": "#2bf0ff",
        "rowline": "#1f5a6a", "sel_bg": "#2a0a2a", "sel_fg": "#ffd6f7",
        "status_bg": "#0a0a16", "muted": "#6f7bb0",
        "font": "Segoe UI", "font_size": 10,
        "relief": "flat", "borderwidth": 1, "btn_relief": "flat", "btn_bw": 1,
    },
    "swiss": {
        "name": "瑞士极简 Swiss",
        "bg": "#ffffff", "panel": "#ffffff", "fg": "#111111",
        "title": "#ffffff", "title_fg": "#111111",
        "accent": "#e4002b", "accent_fg": "#ffffff",
        "btn": "#ffffff", "btn_fg": "#111111",
        "border": "#111111", "heading_bg": "#ffffff", "heading_fg": "#111111",
        "rowline": "#111111", "sel_bg": "#fbe9ec", "sel_fg": "#111111",
        "status_bg": "#ffffff", "muted": "#555555",
        "font": "Helvetica Neue", "font_size": 10,
        "relief": "flat", "borderwidth": 1, "btn_relief": "flat", "btn_bw": 1,
    },
    "skeuo": {
        "name": "拟物写实 Skeuomorphism",
        "bg": "#2b1d12", "panel": "#2e2013", "fg": "#f3e6d0",
        "title": "#b98f4e", "title_fg": "#2b1d12",
        "accent": "#caa15a", "accent_fg": "#2b1d12",
        "btn": "#caa15a", "btn_fg": "#2b1d12",
        "border": "#160d05", "heading_bg": "#3a2818", "heading_fg": "#dcae6e",
        "rowline": "#5a4326", "sel_bg": "#4a3a20", "sel_fg": "#fff4dd",
        "status_bg": "#241608", "muted": "#c2a878",
        "font": "Georgia", "font_size": 10,
        "relief": "raised", "borderwidth": 2, "btn_relief": "raised", "btn_bw": 2,
    },
    "clay": {
        "name": "黏土风 Claymorphism",
        "bg": "#f3f0ff", "panel": "#f3f0ff", "fg": "#5b4b8a",
        "title": "#f3f0ff", "title_fg": "#7a5cff",
        "accent": "#8a6cff", "accent_fg": "#ffffff",
        "btn": "#e9e2ff", "btn_fg": "#6a4cff",
        "border": "#d6cdf2", "heading_bg": "#f3f0ff", "heading_fg": "#7a5cff",
        "rowline": "#d6cdf2", "sel_bg": "#ddd2ff", "sel_fg": "#5b4b8a",
        "status_bg": "#f3f0ff", "muted": "#9b8fc8",
        "font": "Segoe UI", "font_size": 10,
        "relief": "flat", "borderwidth": 0, "btn_relief": "flat", "btn_bw": 0,
    },
    "memphis": {
        "name": "孟菲斯 Memphis",
        "bg": "#fdf6e3", "panel": "#ffffff", "fg": "#111111",
        "title": "#111111", "title_fg": "#ffffff",
        "accent": "#ff3b3b", "accent_fg": "#ffffff",
        "btn": "#ffffff", "btn_fg": "#111111",
        "border": "#111111", "heading_bg": "#111111", "heading_fg": "#ffffff",
        "rowline": "#111111", "sel_bg": "#ffd23b", "sel_fg": "#111111",
        "status_bg": "#ffffff", "muted": "#555555",
        "font": "Trebuchet MS", "font_size": 10,
        "relief": "raised", "borderwidth": 3, "btn_relief": "raised", "btn_bw": 3,
    },
    "vaporwave": {
        "name": "蒸汽波 Vaporwave",
        "bg": "#c774e8", "panel": "#5a3a7a", "fg": "#ffffff",
        "title": "#b54fb0", "title_fg": "#ffffff",
        "accent": "#ff71ce", "accent_fg": "#3a0a3a",
        "btn": "#b54fb0", "btn_fg": "#ffffff",
        "border": "#ff71ce", "heading_bg": "#6a3a86", "heading_fg": "#ffffff",
        "rowline": "#ff71ce", "sel_bg": "#b54fb0", "sel_fg": "#ffffff",
        "status_bg": "#6a3a86", "muted": "#f3c8ef",
        "font": "Segoe UI", "font_size": 10,
        "relief": "flat", "borderwidth": 1, "btn_relief": "flat", "btn_bw": 1,
    },
}

# 画廊展示顺序（"经典" 排在最前，对应第 0 张）
ORDER = [
    "classic", "neumorphism", "brutalism", "glass", "terminal",
    "cyberpunk", "swiss", "skeuo", "clay", "memphis", "vaporwave",
]


def get_theme(key):
    """返回主题字典；非法 key 回退到 DEFAULT_THEME。"""
    return THEMES.get(key, THEMES[DEFAULT_THEME])


def font_tuple(theme, size_delta=0):
    """构造 tkinter 字体元组。系统没有对应字体时会回退，安全。"""
    size = max(7, theme.get("font_size", 10) + size_delta)
    return (theme["font"], size)


def apply_style(style, theme):
    """把主题应用到 ttk.Style（使用 clam 引擎以获得跨平台一致的配色控制）。"""
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    bg = theme["bg"]
    panel = theme["panel"]
    fg = theme["fg"]
    title = theme["title"]
    title_fg = theme["title_fg"]
    accent = theme["accent"]
    accent_fg = theme["accent_fg"]
    btn = theme["btn"]
    btn_fg = theme["btn_fg"]
    border = theme["border"]
    heading_bg = theme["heading_bg"]
    heading_fg = theme["heading_fg"]
    rowline = theme["rowline"]
    sel_bg = theme["sel_bg"]
    sel_fg = theme["sel_fg"]
    status_bg = theme["status_bg"]
    muted = theme["muted"]
    f = font_tuple(theme)
    relief = theme["relief"]
    bw = theme["borderwidth"]
    btn_relief = theme["btn_relief"]
    btn_bw = theme["btn_bw"]

    # 框架 / 容器
    style.configure("TFrame", background=bg, bordercolor=border,
                    relief=relief, borderwidth=bw)
    style.configure("TPanedwindow", background=bg, bordercolor=border)
    style.configure("TLabel", background=bg, foreground=fg, font=f)
    style.configure("TNotebook", background=bg, bordercolor=border)
    style.configure("TNotebook.Tab", background=panel, foreground=fg, font=f)

    # 工具栏 / 状态栏区域（用 TFrame 承载，颜色随 bg）
    style.configure("StatusBar.TFrame", background=status_bg, bordercolor=border,
                    relief=relief, borderwidth=bw)
    style.configure("ToolBar.TFrame", background=title, bordercolor=border,
                    relief=relief, borderwidth=bw)
    style.configure("Status.TLabel", background=status_bg, foreground=fg, font=f)

    # 按钮：次按钮 + 主按钮（Accent）
    style.configure("TButton", background=btn, foreground=btn_fg,
                    bordercolor=border, relief=btn_relief, borderwidth=btn_bw,
                    font=f, padding=(8, 3))
    style.map("TButton",
              background=[("active", accent)],
              foreground=[("active", accent_fg)])
    style.configure("Accent.TButton", background=accent, foreground=accent_fg,
                    bordercolor=border, relief=btn_relief, borderwidth=btn_bw,
                    font=f, padding=(8, 3))
    style.map("Accent.TButton",
              background=[("active", _shade(accent, -12))],
              foreground=[("active", accent_fg)])

    # 列表 / 树
    style.configure("Treeview", background=panel, foreground=fg,
                    fieldbackground=panel, bordercolor=border,
                    font=font_tuple(theme), rowheight=24, relief=relief,
                    borderwidth=bw)
    style.map("Treeview",
              background=[("selected", sel_bg)],
              foreground=[("selected", sel_fg)],
              bordercolor=[("selected", border)])
    style.configure("Treeview.Heading", background=heading_bg,
                    foreground=heading_fg, bordercolor=border,
                    relief=relief, borderwidth=bw,
                    font=font_tuple(theme, 0))
    style.map("Treeview.Heading",
              background=[("active", _shade(heading_bg, 8))])

    # 输入控件
    style.configure("TEntry", fieldbackground=panel, foreground=fg,
                    bordercolor=border, relief=btn_relief, borderwidth=btn_bw,
                    font=f)
    style.configure("TCombobox", fieldbackground=panel, foreground=fg,
                    bordercolor=border, relief=btn_relief, borderwidth=btn_bw,
                    font=f, arrowcolor=heading_fg)
    style.map("TCombobox",
              fieldbackground=[("readonly", panel)],
              foreground=[("readonly", fg)])
    style.configure("TCheckbutton", background=bg, foreground=fg, font=f)
    style.configure("TRadiobutton", background=bg, foreground=fg, font=f)

    # 滑块 / 进度条 / 分隔线
    style.configure("TScale", background=bg, troughcolor=rowline,
                    bordercolor=border, relief=relief)
    style.configure("TProgressbar", background=accent, troughcolor=rowline,
                    bordercolor=border, relief=relief)
    style.configure("TSeparator", background=border)
    style.configure("Horizontal.TProgressbar", background=accent,
                    troughcolor=rowline, bordercolor=border)

    return {
        "bg": bg, "fg": fg, "title": title, "title_fg": title_fg,
        "border": border, "muted": muted, "status_bg": status_bg,
        "accent": accent, "accent_fg": accent_fg,
    }


# ---------------------------------------------------------------------------
# 配色辅助
# ---------------------------------------------------------------------------
def _shade(hex_color, percent):
    """把十六进制颜色按百分比调亮（正）或调暗（负），容错返回原色。"""
    try:
        h = hex_color.lstrip("#")
        if len(h) != 6:
            return hex_color
        r = int(h[0:2], 16)
        g = int(h[2:4], 16)
        b = int(h[4:6], 16)
        def adj(c):
            c = c + int(round(255 * percent / 100.0))
            return max(0, min(255, c))
        return "#%02x%02x%02x" % (adj(r), adj(g), adj(b))
    except Exception:
        return hex_color


def _lum(hex_color):
    """相对亮度（0~1），供对比度计算。"""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return 0.0
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    def lin(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast(hex_a, hex_b):
    """WCAG 对比度（>=4.5 视为正文可读）。"""
    la, lb = _lum(hex_a), _lum(hex_b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


# 延迟导入，避免循环；tk 仅在 apply_style 内使用
import tkinter as tk  # noqa: E402


# ---------------------------------------------------------------------------
# 自检（供 tools/qa_themes_test.py 调用，不依赖 GUI 渲染）
# ---------------------------------------------------------------------------
REQUIRED_KEYS = [
    "name", "bg", "panel", "fg", "title", "title_fg", "accent", "accent_fg",
    "btn", "btn_fg", "border", "heading_bg", "heading_fg", "rowline",
    "sel_bg", "sel_fg", "status_bg", "muted", "font", "font_size",
    "relief", "borderwidth", "btn_relief", "btn_bw",
]


def self_check():
    """返回 (问题列表, 报告行列表)。空问题列表即全部通过。"""
    problems = []
    report = []
    # 1) 数量与键齐全
    if len(THEMES) != 11:
        problems.append(f"主题数量应为 11，实际 {len(THEMES)}")
    for key, th in THEMES.items():
        for rk in REQUIRED_KEYS:
            if rk not in th:
                problems.append(f"主题 {key} 缺少字段 {rk}")
        if "name" in th and not th["name"]:
            problems.append(f"主题 {key} 名称为空")
    # 2) 每个主题关键对比度（正文、选中、按钮）需可读
    for key, th in THEMES.items():
        pairs = [
            ("正文 fg/panel", th["fg"], th["panel"]),
            ("标题 title_fg/title", th["title_fg"], th["title"]),
            ("按钮 btn_fg/btn", th["btn_fg"], th["btn"]),
            ("主按钮 accent_fg/accent", th["accent_fg"], th["accent"]),
            ("选中 sel_fg/sel_bg", th["sel_fg"], th["sel_bg"]),
        ]
        for label, a, b in pairs:
            c = contrast(a, b)
            if c < 3.0:
                problems.append(
                    f"主题 {key} 对比度不足：{label} = {c:.2f} (<3.0)")
            report.append(f"  {key:12s} {label:22s} 对比度 {c:.2f}")
    # 3) ORDER 与 THEMES 一致
    if set(ORDER) != set(THEMES.keys()):
        problems.append("ORDER 与 THEMES 键集合不一致")
    return problems, report


if __name__ == "__main__":
    probs, rep = self_check()
    print("\n".join(rep))
    if probs:
        print("\n发现问题：")
        print("\n".join(" - " + p for p in probs))
    else:
        print("\n全部主题自检通过 ✅")
