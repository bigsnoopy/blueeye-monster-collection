# -*- coding: utf-8 -*-
"""GUI 逻辑层冒烟测试（tk 桩，无需显示器、无需 7z 引擎）。

覆盖本次改动的关键点：
  • 名称存在 #0 列（item(...,"text")），values 里不再有名称 —— 图标才能显示
  • 图标取到时会挂到行上，并让行高自适应图标高度
  • 图标取不到时（非 Windows / 极端情况）渲染照常，不崩
  • 多选后压缩：从选中行反推的源路径必须正确（此前读 values[0]，改动后必须读 text）
  • 右键入口 _start_compress 的空源保护

真机项（真 Tk 渲染 + 真图标像素 + 真注册表读写）不在本文件，见：
  tools/qa_icon_test.py、tools/qa_registry_test.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# 复用 qa_gui_test 的 tk 桩
from qa_gui_test import make_stub, FakeTreeview  # noqa: F401

import fileicons

# 必须先装 tk 桩，再 import gui（gui 顶部 import tkinter）
make_stub()
import tkinter as tk  # noqa: E402  (fake module installed by make_stub)
# 给 fake messagebox/filedialog 补几个 gui 会用到的 no-op 方法
import tkinter.messagebox as _mb
_mb.showinfo = lambda *a, **k: None
_mb.showerror = lambda *a, **k: None
_mb.askyesno = lambda *a, **k: False
import tkinter.filedialog as _fd
_fd.asksaveasfilename = lambda *a, **k: ""
_fd.askdirectory = lambda *a, **k: ""
_fd.askopenfilename = lambda *a, **k: ""
import gui  # noqa: E402


def _make_dir():
    d = tempfile.mkdtemp(prefix="zf_int_")
    open(os.path.join(d, "a.txt"), "w").write("1")
    open(os.path.join(d, "b.txt"), "w").write("2")
    os.mkdir(os.path.join(d, "sub"))
    return d


def test_no_icon_render():
    """图标取不到时（桩环境即如此）列表照常渲染，名称在 text 里。"""
    app = gui.ZipForgeApp(tk.Tk())
    d = _make_dir()
    app.navigate(d)
    rows = {app.listv.item(i, "text"): app.listv.item(i, "values")
            for i in app.listv.get_children()}
    assert "a.txt" in rows and "b.txt" in rows, rows
    assert "sub/" in rows, "目录名必须带尾斜杠（双击判定依赖它）"
    assert rows["a.txt"][0], "大小列应有值"
    assert rows["sub/"][0] == "", "目录不应显示大小"
    assert all(app.listv.item(i, "image") is None
               for i in app.listv.get_children()), "桩环境下不应有图标"
    print("[渲染] 无图标时正常渲染，名称在 #0，OK")


def test_row_name_helper():
    app = gui.ZipForgeApp(tk.Tk())
    d = _make_dir()
    app.navigate(d)
    names = [app._row_name(i) for i in app.listv.get_children()]
    assert "a.txt" in names and "sub/" in names, names
    # 关键：values 里已经没有名称了，_row_name 必须走 text
    for i in app.listv.get_children():
        assert app._row_name(i) not in app.listv.item(i, "values"), \
            "values 里不应再出现名称"
    print("[_row_name] 从 #0 取名称，OK")


def test_icon_attached_and_rowheight():
    """图标可用时：挂到行上 + 行高跟着图标高度自适应。"""
    class FakeIcon:
        def __init__(self, h):
            self._h = h
        def height(self):
            return self._h

    app = gui.ZipForgeApp(tk.Tk())
    real = fileicons.get_file_icon
    try:
        fileicons.get_file_icon = lambda ext, is_dir=False, **k: FakeIcon(20)
        d = _make_dir()
        app.navigate(d)
        assert all(app.listv.item(i, "image") is not None
                   for i in app.listv.get_children()), "图标未挂到行上"
        assert app._rowheight == 26, app._rowheight      # max(24, 20+6)

        fileicons.get_file_icon = lambda ext, is_dir=False, **k: FakeIcon(8)
        app.navigate(d)
        assert app._rowheight == 24, app._rowheight      # 小图标不缩行高
    finally:
        fileicons.get_file_icon = real
    print("[图标] 挂载 + 行高自适应（26/24），OK")


def test_icon_none_is_safe():
    app = gui.ZipForgeApp(tk.Tk())
    real = fileicons.get_file_icon
    try:
        fileicons.get_file_icon = lambda ext, is_dir=False, **k: None
        app.navigate(_make_dir())
        assert app._rowheight == 24
    finally:
        fileicons.get_file_icon = real
    print("[图标] 取不到图标时静默降级，OK")


def test_compress_sources_from_text():
    """多选 -> 压缩源路径必须正确（这是 values[0] → text 改动的回归点）。"""
    app = gui.ZipForgeApp(tk.Tk())
    d = _make_dir()
    app.mode = "fs"
    app.navigate(d)
    captured = {}
    app._start_compress = lambda srcs: captured.setdefault("srcs", srcs)
    iids = app.listv.get_children()
    app.listv.set_selection(iids)
    app.compress_selected()
    srcs = captured.get("srcs")
    assert srcs is not None, "未进入压缩流程"
    assert len(srcs) == 3, srcs
    assert os.path.join(d, "a.txt") in srcs, srcs
    assert os.path.join(d, "b.txt") in srcs, srcs
    assert os.path.join(d, "sub") in srcs, srcs
    assert all(os.path.exists(s) for s in srcs), srcs
    assert not any(s.endswith("/") for s in srcs), "源路径不应带尾斜杠"
    print("[压缩] 多选源路径解析:", [os.path.basename(s) for s in srcs], "OK")


def test_archive_render_and_nav():
    """归档渲染：名称在 text、目录带尾斜杠、可下钻/返回。"""
    app = gui.ZipForgeApp(tk.Tk())
    app.archive_path = os.path.join(tempfile.gettempdir(), "x.7z")
    app.mode = "archive"
    app.archive_all_items = [
        {"path": "报告.docx", "size": 1234, "method": "LZMA2", "encrypted": False},
        {"path": "资料", "folder": True, "encrypted": False},
        {"path": "资料/预算.xlsx", "size": 999, "method": "LZMA2", "encrypted": True},
        {"path": "图片/", "folder": True, "encrypted": False},
        {"path": "图片/1.png", "size": 50, "method": "LZMA2"},
    ]
    app.archive_prefix = ""
    app._render_archive()
    names = [app.listv.item(i, "text") for i in app._archive_row_full]
    print("[归档] 根目录:", names)
    assert "报告.docx" in names
    assert "资料/" in names and "图片/" in names, "目录行必须带尾斜杠且不重复"

    app.archive_prefix = "资料/"
    app._render_archive()
    sub = [app.listv.item(i, "text") for i in app._archive_row_full]
    assert sub == ["预算.xlsx"], sub

    # 双击目录 -> 下钻（回到根，双击「资料/」那一行）
    app.archive_prefix = ""
    app._render_archive()
    dir_iid = [i for i in app._archive_row_full
               if app.listv.item(i, "text") == "资料/"]
    assert dir_iid, "未渲染出 资料/ 目录行"
    app.listv.set_selection(dir_iid)
    app.on_list_double(None)
    assert app.archive_prefix == "资料/", app.archive_prefix
    app.go_up()
    assert app.archive_prefix == "", app.archive_prefix
    print("[归档] 下钻/返回上级，OK")


def test_ext_helper():
    assert gui._ext("a.docx") == "docx"
    assert gui._ext("b.tar.gz") == "gz"
    assert gui._ext("noext") == ""
    assert gui._ext("资料/") == ""
    print("[_ext] 扩展名解析，OK")


def test_empty_source_guard():
    app = gui.ZipForgeApp(tk.Tk())
    app._start_compress(["C:\\不存在\\x.txt"])   # 不应抛异常
    print("[压缩] 空源保护，OK")


def main():
    test_ext_helper()
    test_no_icon_render()
    test_row_name_helper()
    test_icon_attached_and_rowheight()
    test_icon_none_is_safe()
    test_compress_sources_from_text()
    test_archive_render_and_nav()
    test_empty_source_guard()
    print("\nGUI 逻辑冒烟: 全部通过 [PASS]")


if __name__ == "__main__":
    main()
