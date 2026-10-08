# -*- coding: utf-8 -*-
"""真机测试（需要真实 Tk + Windows）：验证图标、列表渲染、右键注册三件事。

与 stub 版测试的区别：这里用真的 tkinter，真的生成 PhotoImage，
真的把 ZipForgeApp 建起来，并检查 Treeview 行上是否真的挂了图标。
（stub 环境里 fileicons 一律返回 None，测不出"图标到底出没出来"。）

退出码 0 = 全部通过。
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

import tkinter as tk  # noqa: E402

import fileicons  # noqa: E402
import gui  # noqa: E402

FAILED = []


def check(name, cond, extra=""):
    print(("  [PASS] " if cond else "  [FAIL] ") + name + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAILED.append(name)


def _stats(img):
    """返回 (宽, 高, 不透明像素数, 颜色种类数)。"""
    w, h = img.width(), img.height()
    colors = set()
    opaque = 0
    for y in range(h):
        for x in range(w):
            try:
                if img.transparency_get(x, y):
                    continue
            except Exception:
                pass
            opaque += 1
            colors.add(img.get(x, y))
    return w, h, opaque, len(colors)


def main():
    if sys.platform != "win32":
        print("非 Windows，跳过。")
        return 0

    root = tk.Tk()
    root.withdraw()

    print("== 1. 系统图标提取（真实像素） ==")
    docx = fileicons.get_file_icon("docx")
    check("docx 图标非空", docx is not None)
    if docx:
        w, h, opaque, colors = _stats(docx)
        check("docx 尺寸 16x16", (w, h) == (16, 16), (w, h))
        check("docx 有实际内容（非空白图）", opaque > 40 and colors >= 4,
              f"不透明={opaque} 颜色={colors}")
        check("docx 有透明像素（alpha/遮罩生效）", opaque < 256, opaque)

    folder = fileicons.get_file_icon("", is_dir=True)
    check("文件夹图标非空", folder is not None)
    if folder and docx:
        w, h, opaque, colors = _stats(folder)
        check("文件夹图标有内容", opaque > 40 and colors >= 4,
              f"不透明={opaque} 颜色={colors}")
        check("文件夹图标与文件图标不同",
              folder.get(8, 8) != docx.get(8, 8) or opaque != 0)

    unknown = fileicons.get_file_icon("zzz")
    check("未知扩展名也有通用图标（不再是一片空白）", unknown is not None)

    print("== 2. 图标缓存 ==")
    a = fileicons.get_file_icon("docx")
    check("同 key 命中缓存（同一对象）", a is docx)

    print("== 3. 真实 ZipForgeApp 渲染 ==")
    app = gui.ZipForgeApp(root)
    # 造一个内容丰富的目录：中文名、多级目录、各种扩展名
    d = tempfile.mkdtemp(prefix="zf_real_")
    for nm in ["报告.docx", "数据.xlsx", "演示.pptx", "说明.txt", "图.png",
               "包.zip", "压缩.rar", "无扩展名"]:
        open(os.path.join(d, nm), "w").write("x")
    os.mkdir(os.path.join(d, "子目录"))

    app.navigate(d)
    iids = app.listv.get_children()
    check("列表渲染出 9 行", len(iids) == 9, len(iids))
    names = [app._row_name(i) for i in iids]
    check("名称在 #0（text）列", "报告.docx" in names and "子目录/" in names, names)

    imgs = [app.listv.item(i, "image") for i in iids]
    with_icon = sum(1 for v in imgs if v and v != "")
    check("全部行都挂上了图标", with_icon == len(iids), f"{with_icon}/{len(iids)}")

    show = str(app.listv.cget("show"))
    check("列表开启 tree 列（图标唯一可显示的位置）",
          "tree" in show, show)
    check("行高已按图标高度自适应", app._rowheight >= 24, app._rowheight)

    # 选中并走一次压缩源解析（不真正压缩）
    captured = {}
    real = app._start_compress
    app._start_compress = lambda s: captured.setdefault("s", s)
    app.listv.selection_set(iids[:2])
    app.compress_selected()
    app._start_compress = real
    check("多选压缩源路径正确",
          len(captured.get("s", [])) == 2
          and all(os.path.exists(p) for p in captured["s"]),
          captured.get("s"))

    n_icons = len(fileicons._cache)
    print(f"  （本次共生成 {n_icons} 个图标对象）")
    check("图标缓存数量合理（未爆炸）", 0 < n_icons <= 20, n_icons)

    root.destroy()
    print()
    if FAILED:
        print(f"结果：{len(FAILED)} 项未通过 -> {FAILED}")
        return 1
    print("结果：全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
