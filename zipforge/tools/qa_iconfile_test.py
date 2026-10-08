# -*- coding: utf-8 -*-
"""图标资产自检（方案 10「霓虹 ZF」）。

校验：ICO 结构合法、尺寸齐全（含 16/32/48/256）、关于窗口 PNG 尺寸正确、
      与 gui.py 常量及打包脚本保持一致。

纯标准库实现（不依赖 PIL / tkinter），可在任意解释器下运行。
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ICO = os.path.join(ROOT, "assets", "icon_zf_neon.ico")
PNG128 = os.path.join(ROOT, "assets", "icon_zf_neon_128.png")
GUI = os.path.join(ROOT, "src", "gui.py")
BUILD = os.path.join(ROOT, "build_exe.bat")

fails = []


def check(cond, msg):
    print(("  [OK]  " if cond else "  [!!]  ") + msg)
    if not cond:
        fails.append(msg)


def read_ico_sizes(path):
    with open(path, "rb") as f:
        data = f.read()
    reserved, itype, count = struct.unpack_from("<HHH", data, 0)
    if reserved != 0 or itype != 1:
        raise ValueError("不是合法的 ICO 文件")
    sizes = []
    off = 6
    for _ in range(count):
        w, h = struct.unpack_from("<BB", data, off)
        sizes.append((w or 256, h or 256))
        off += 16
    return sizes, len(data), count


def read_png_size(path):
    with open(path, "rb") as f:
        head = f.read(33)
    sig = b"\x89PNG\r\n\x1a\n"
    if head[:8] != sig:
        raise ValueError("不是合法的 PNG 文件")
    w, h = struct.unpack(">II", head[16:24])
    return w, h


def main():
    print("图标资产自检 — %s" % ICO)

    # 1) ICO 存在且结构合法
    check(os.path.isfile(ICO), "ICO 文件存在")
    sizes, nbytes, count = (read_ico_sizes(ICO) if os.path.isfile(ICO)
                            else ([], 0, 0))
    check(count >= 6, "ICO 含 >=6 档尺寸（实际 %d）" % count)
    flat = set(s[0] for s in sizes)
    for need in (16, 32, 48, 256):
        check(need in flat, "含 %d px 档" % need)
    check(nbytes > 5000, "ICO 体积合理（%d 字节）" % nbytes)
    check(all(w == h for w, h in sizes), "各档尺寸为正方形")

    # 2) 关于窗口 PNG
    check(os.path.isfile(PNG128), "关于窗口 PNG 存在")
    if os.path.isfile(PNG128):
        w, h = read_png_size(PNG128)
        check((w, h) == (128, 128), "关于窗口 PNG 为 128x128（实际 %dx%d）" % (w, h))

    # 3) 与代码/脚本一致（纯文本检查，避免导入 tkinter）
    gtxt = open(GUI, encoding="utf-8").read() if os.path.isfile(GUI) else ""
    check('ICON_FILE = "assets/icon_zf_neon.ico"' in gtxt,
          "gui.py 的 ICON_FILE 指向该 ICO")
    check("def _apply_window_icon" in gtxt and "iconbitmap" in gtxt,
          "gui.py 已设置窗口图标（iconbitmap）")
    check("assets/icon_zf_neon_128.png" in gtxt,
          "gui.py 的「关于」窗口引用 128 PNG")
    check("set_app_user_model_id" in gtxt, "gui.py 已设置任务栏 AppUserModelID")

    btxt = open(BUILD, encoding="utf-8").read() if os.path.isfile(BUILD) else ""
    check('--icon "assets\\icon_zf_neon.ico"' in btxt, "打包脚本传入 --icon")
    check('--add-data "assets;assets"' in btxt, "打包脚本随包分发 assets/")

    ztxt = ""
    zpath = os.path.join(ROOT, "zipforge.py")
    if os.path.isfile(zpath):
        ztxt = open(zpath, encoding="utf-8").read()
    check("SetCurrentProcessExplicitAppUserModelID" in ztxt,
          "启动器设置了进程 AppUserModelID")

    print()
    if fails:
        print("图标资产自检未通过：%d 项" % len(fails))
        for m in fails:
            print("  - " + m)
        return 1
    print("图标资产自检全部通过 [PASS]（尺寸：%s）"
          % ", ".join(str(w) for w, _ in sizes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
