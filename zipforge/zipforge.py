# -*- coding: utf-8 -*-
"""ZipForge 启动器（项目根入口）。

运行方式：
  python zipforge.py                # 直接以源码运行（需本机 Python 3.8+）
  python zipforge.py 文件A 文件夹B   # 带路径启动 → 直接弹出「压缩设置」

资源管理器右键菜单会以命令行动作的方式调用本程序（选中即执行，不进主界面）：
  ZipForge.exe --verb quick7z  "D:\\a\\b.txt"     快速压缩为 b.7z
  ZipForge.exe --verb quickzip "D:\\a\\b.txt"     快速压缩为 b.zip

`--scope file|dir|bg` 说明归档生成到哪里（右键菜单自动带上）：
  file/dir  选中文件或文件夹  → 生成在选中项的**所在目录**
                                  （文件夹 → 生成在它**旁边**，即父目录）
  bg        文件夹**空白处**右键 → 生成在**该文件夹内部**（与 7-Zip 一致）
  ZipForge.exe --verb crc32    "D:\\a\\b.txt"     计算 CRC-32
  ZipForge.exe --verb sha256   "D:\\a\\b.txt"     计算 SHA-256
  ZipForge.exe --verb hash_all "D:\\a\\b.txt"     计算全部校验值
  ZipForge.exe --verb extract_here "D:\\a\\x.zip" 解压到当前文件夹
  ZipForge.exe --verb extract_same "D:\\a\\x.zip" 解压到同名文件夹
  ZipForge.exe --verb add      "D:\\a\\b.txt"     打开压缩对话框
  ZipForge.exe --verb addmail  "D:\\a\\b.txt"     压缩并起草邮件
  ZipForge.exe --verb extract_to "D:\\a\\x.zip"   打开解压对话框
  ZipForge.exe --verb test     "D:\\a\\x.zip"     测试归档完整性

打包为 exe（需先 pip install pyinstaller）：
  pyinstaller zipforge.py --onefile --windowed --name ZipForge \
      --icon "assets/icon_zf_neon.ico" \
      --add-data "vendor/engine-x64;vendor/engine-x64" \
      --add-data "assets;assets"

无界面自检模式（用于验证打包后引擎可用，不弹窗口）：
  ZF_TEST=1 python zipforge.py
  或 Windows:  set ZF_TEST=1 && ZipForge.exe
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "src"))


def _self_test():
    """无界面自检：验证引擎定位、zip 列表/解压、右键菜单、校验值、动作解析。"""
    import sevenzip_engine as engine

    lines = []
    ok_all = True

    def log(s):
        lines.append(s)
        print(s)

    try:
        eng = engine.locate_engine()
        log(f"[1] 引擎路径: {eng}")
        log(f"[1] 引擎版本: {engine.engine_version()}")
    except Exception as e:
        ok_all = False
        log(f"[1] 引擎定位失败: {e}")
        return ok_all, "\n".join(lines)

    # 造一个临时 zip 并打开 + 解压
    import tempfile
    tmp = tempfile.mkdtemp(prefix="zf_selftest_")
    src = os.path.join(tmp, "demo.txt")
    with open(src, "w", encoding="utf-8") as f:
        f.write("ZipForge 自检内容 " + "x" * 3000)
    arc = os.path.join(tmp, "demo.zip")
    r = engine.compress([src], arc, fmt="zip", level=5)
    log(f"[2] 创建 zip: rc={r['rc']} ok={r['ok']}")
    if not r["ok"]:
        ok_all = False

    info = engine.list_archive(arc)
    log(f"[3] 打开 zip 列表: 条目数={len(info['items'])}")
    if len(info["items"]) < 1:
        ok_all = False
        log("    RAW>>> " + info["raw"][:800])

    dest = os.path.join(tmp, "out")
    r2 = engine.extract_archive(arc, dest)
    extracted = os.path.exists(os.path.join(dest, "demo.txt"))
    log(f"[4] 解压 zip: ok={r2['ok']} 文件存在={extracted}")
    if not (r2["ok"] and extracted):
        ok_all = False

    # [5] 含子目录的归档：目录识别与聚合（回归保护）
    #     踩过的坑：目录条目在不同容器里标记方式不同（7z 用属性位 D、rar 用 Folder=+），
    #     且显式目录条目路径不带尾斜杠 —— 曾导致目录被当文件、"双击打开失败"。
    try:
        import gui
        tree = os.path.join(tmp, "树", "子目录")
        os.makedirs(tree, exist_ok=True)
        with open(os.path.join(tree, "内层.txt"), "w", encoding="utf-8") as f:
            f.write("deep")
        with open(os.path.join(tmp, "树", "外层.txt"), "w", encoding="utf-8") as f:
            f.write("outer")
        arc2 = os.path.join(tmp, "tree.7z")
        engine.compress([os.path.join(tmp, "树")], arc2, fmt="7z", level=5)
        info2 = engine.list_archive(arc2)
        rows = gui.filter_archive_items(info2["items"], "")
        dirs = [r for r in rows if r[1]]
        files = [r for r in rows if not r[1]]
        well_formed = all(d[0].endswith("/") for d in dirs)
        log(f"[5] 目录归档: 目录行={len(dirs)} 文件行={len(files)} "
            f"目录名带斜杠={well_formed} 目录={[d[0] for d in dirs]}")
        if len(dirs) != 1 or not well_formed:
            ok_all = False
        # 进入子目录后应能看到下一级
        sub = gui.filter_archive_items(info2["items"], dirs[0][2])
        log(f"[6] 进入 {dirs[0][0]} 后: "
            f"{[r[0] for r in sub]}")
        if len(sub) != 2:
            ok_all = False
        # 单条目提取到自管临时目录并按相对路径定位
        rel = [r[2] for r in sub if not r[1]][0]
        d2 = engine.new_temp_dir("zf_selftest_open_")
        e2 = engine.extract_archive(arc2, d2, items=[rel])
        hit = os.path.isfile(os.path.join(d2, *rel.split("/")))
        log(f"[7] 单条目提取: ok={e2['ok']} 定位命中={hit}")
        if not (e2["ok"] and hit):
            ok_all = False
        # 时间戳归一化（回归保护）：
        #   7z 的 Modified 带纳秒小数、且此前切片 off-by-one 吃掉年份首位，
        #   界面会显示成 "026-04-29 …"。这里直接校验解析结果格式。
        import re as _re
        pat = _re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
        bad_ts = [it.get("modified") for it in info2["items"]
                  if it.get("modified") and not pat.match(it.get("modified"))]
        log(f"[8] 时间戳格式: 异常项={len(bad_ts)} 样例="
            f"{[it.get('modified') for it in info2['items']][:3]}")
        if bad_ts:
            ok_all = False
    except Exception as ex:
        ok_all = False
        log(f"[5-7] 目录归档自检异常: {type(ex).__name__}: {ex}")

    # [9] 右键菜单：级联子菜单的完整往返（写入 → 读回 → 卸载，测完立即还原）。
    try:
        import shell_integration as si
        exe = si.exe_path()
        log(f"[9] 右键菜单目标: {exe}")
        sane = (exe.lower().endswith(".exe") and os.path.isfile(exe)
                and "_mei" not in exe.lower())
        log(f"[9] exe 路径合理(非 PyInstaller 临时目录)={sane}")
        if not sane:
            ok_all = False
        ok, msg = si.register()
        if not ok:
            log(f"[9] 注册失败: {msg}")
            ok_all = False
        else:
            import winreg as _wr
            counts = []
            for scope, base in si._ROOT_KEYS.items():
                rows = si.read_cascade(_wr, base)
                counts.append(f"{scope}={len(rows)}")
                nope = [n for n, _l, cmd in rows
                        if not cmd or "--verb" not in cmd]
                if len(rows) != len(si.menu_items(scope)) or nope:
                    ok_all = False
                    log(f"[9] {scope} 子菜单异常: {len(rows)} 项 / 缺命令行 {nope}")
            log("[9] 级联子菜单写入: " + "  ".join(counts))
            rows = si.read_cascade(_wr, si._ROOT_KEYS["file"])
            log("[9] 文件菜单顺序: " + " | ".join(l for _n, l, _c in rows))
            ok2, _msg2 = si.unregister()
            left = [b for b in si._KEYS if si._read_verb_command(_wr, b)]
            log(f"[9] 卸载={ok2} 残余={left}")
            if not ok2 or left:
                ok_all = False
    except Exception as ex:
        ok_all = False
        log(f"[9] 右键菜单自检异常: {type(ex).__name__}: {ex}")

    # [10] 校验值解析（回归保护）
    #      ⚠ 踩过的坑：旧正则会把 "SHA256 **f**or data:" 的 f 当成结果，
    #        恒返回 "f"；且目录聚合时值尾部带 "-00000001" 必须允许。
    try:
        import re as _re2
        hv = engine.hash_data(src, "SHA256")
        ok_h = bool(_re2.fullmatch(r"[0-9a-fA-F]{64}", hv or ""))
        log(f"[10] SHA256 解析: {(hv or '')[:16]}… 合法={ok_h}")
        if not ok_h:
            ok_all = False
        cz = engine.hash_data(src, "CRC32")
        ok_c = bool(_re2.fullmatch(r"[0-9a-fA-F]{8}", cz or ""))
        log(f"[10] CRC32 解析: {cz} 合法={ok_c}")
        if not ok_c:
            ok_all = False
        # 目录聚合（带 -00000001 后缀）
        hd = engine.hash_data(tmp, "SHA256")
        ok_d = bool(_re2.fullmatch(r"[0-9a-fA-F]{64}(-[0-9a-fA-F]{8})?", hd or ""))
        log(f"[10] 目录 SHA256: {(hd or '')[:24]}… 合法={ok_d}")
        if not ok_d:
            ok_all = False
        # 不存在的文件必须返回空（不能回吐全 0 假哈希）
        miss = engine.hash_data(os.path.join(tmp, "不存在.txt"), "SHA256")
        log(f"[10] 缺失文件返回空={miss == ''}")
        if miss != "":
            ok_all = False
    except Exception as ex:
        ok_all = False
        log(f"[10] 校验值自检异常: {type(ex).__name__}: {ex}")

    # [11] 右键动作参数解析与目标路径推导（纯逻辑）
    try:
        import cli_verbs as cv
        spec = cv.parse(["--verb", "quick7z", r"C:\a\b.txt", r"C:\a\c.txt"])
        ok_p = (spec["verb"] == "quick7z" and len(spec["paths"]) == 2)
        log(f"[11] 动作解析: verb={spec['verb']} 路径数={len(spec['paths'])} 正确={ok_p}")
        if not ok_p:
            ok_all = False
        spec2 = cv.parse(["--verb", "quickzip", "--scope", "bg", r"C:\a"])
        ok_s = (spec2["verb"] == "quickzip" and spec2["scope"] == "bg"
                and spec2["paths"] == [r"C:\a"])
        log(f"[11] scope 解析: verb={spec2['verb']} scope={spec2['scope']} 正确={ok_s}")
        if not ok_s:
            ok_all = False
        base = cv.archive_base_name([r"C:\a\b.txt"])
        same = cv.extract_same_dir(r"D:\x\远特.rar")
        log(f"[11] 基名={base}（期望 b）  同名目录={os.path.basename(same)}（期望 远特）")
        if base != "b" or os.path.basename(same) != "远特":
            ok_all = False
        dest = cv.quick_dest([os.path.join(tmp, "demo.txt")], "7z")
        log(f"[11] 快速压缩目标: {os.path.basename(dest)}（应避让 demo.7z 重名）")
        if os.path.basename(dest) != "demo (2).7z" and os.path.basename(dest) != "demo.7z":
            ok_all = False
        # [11b] 归档放置语义回归（真实 bug：右键文件夹 → 归档被塞进文件夹内部）
        #   选中文件夹(dir) → 归档生成在**文件夹旁边**（父目录）；
        #   文件夹空白处(bg) → 归档生成在**文件夹内部**。
        folder = os.path.join(tmp, "资料夹")
        os.makedirs(folder, exist_ok=True)
        d_dir = cv.quick_dest([folder], "zip", "dir")
        d_bg = cv.quick_dest([folder], "zip", "bg")
        ok_dir = os.path.normcase(os.path.dirname(d_dir)) == os.path.normcase(tmp)
        ok_bg = os.path.normcase(os.path.dirname(d_bg)) == os.path.normcase(folder)
        log(f"[11b] 文件夹放置: dir→{d_dir}  (旁={ok_dir})  bg→{d_bg}  (里={ok_bg})")
        if not (ok_dir and ok_bg):
            ok_all = False
    except Exception as ex:
        ok_all = False
        log(f"[11] 动作解析自检异常: {type(ex).__name__}: {ex}")

    log("自检结果: " + ("全部通过 [PASS]" if ok_all else "存在失败 [FAIL]"))
    return ok_all, "\n".join(lines)


if __name__ == "__main__":
    # 让 Windows 任务栏/任务切换器使用 exe 自带图标（而非 python 解释器图标）
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("XMSG.ZipForge")
        except Exception:
            pass
    if os.environ.get("ZF_TEST"):
        _self_test()
    else:
        _argv = sys.argv[1:]
        # 右键菜单动作优先：无界面直接执行完就退出，不弹主窗口
        try:
            import cli_verbs
            if cli_verbs.try_handle(_argv):
                sys.exit(0)
        except SystemExit:
            raise
        except Exception:
            pass
        from gui import main
        main(_argv)
