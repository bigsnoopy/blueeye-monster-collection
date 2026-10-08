# -*- coding: utf-8 -*-
"""
cli_verbs.py — 右键菜单动作的「命令行执行层」。

资源管理器点选 ZipForge 子菜单时，会以
    ZipForge.exe --verb <动作> "<选中的路径>"
的形式启动本程序。本模块负责把这些动作**直接执行完**（而不是先进主界面），
这样才符合「选中即执行」的期望。

动作分两类：
  A. 无界面直接执行（本模块完成，带一个轻量进度窗口）
       quick7z / quickzip          快速压缩为 7z / zip（自动命名 + 自动避让重名）
       crc32 / crc64 / sha1 /
       sha256 / sha512 / hash_all  计算校验值并弹窗（可一键复制）
       extract_here / extract_same 解压到当前文件夹 / 同名文件夹
  B. 需要主界面配合（交给 gui.py 弹对话框）
       add / addmail / extract_to / new / test

纯逻辑（路径推导、重名避让、参数解析）刻意与 tkinter 解耦，
便于在没有图形环境的 CI 里直接单元测试。
"""
import os
import sys
import threading
from urllib.parse import quote

import config
import formats
import sevenzip_engine as engine
import shell_integration

# 快速压缩：verb -> 目标格式
QUICK_FORMATS = {"quick7z": "7z", "quickzip": "zip"}

# 校验值：verb -> (7z 算法名, 界面显示名)
HASH_ALGOS = {
    "crc32": ("CRC32", "CRC-32"),
    "crc64": ("CRC64", "CRC-64"),
    "sha1": ("SHA1", "SHA-1"),
    "sha256": ("SHA256", "SHA-256"),
    "sha512": ("SHA512", "SHA-512"),
}


# ---------------------------------------------------------------------------
# 纯逻辑（无 tkinter 依赖，可单测）
# ---------------------------------------------------------------------------
def parse(argv):
    """解析命令行 → {"verb": str|None, "scope": str, "paths": [...]}。

    verb  取 `--verb <name>`；
    scope 取 `--scope <file|dir|bg>`，缺省 "file"（见 quick_dest 的说明）；
    其余非 "--" 开头的参数视为路径。
    """
    verb = None
    scope = None
    paths = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--verb" and i + 1 < len(argv):
            verb = argv[i + 1]
            i += 2
            continue
        if a == "--scope" and i + 1 < len(argv):
            scope = argv[i + 1]
            i += 2
            continue
        if a.startswith("--"):
            i += 1
            continue
        paths.append(a)
        i += 1
    return {"verb": verb.lower() if verb else None,
            "scope": scope.lower() if scope else "file",
            "paths": paths}


def common_dir(paths):
    """选中项「所在目录」的公共路径（用于决定归档生成位置）。

    ⚠ 关键语义（真实 bug 修复点）：**文件夹的所在目录是它的父目录**，
      不是文件夹自身。早期实现把「文件夹」直接当成目标目录，导致
      右键文件夹 → 压缩，归档被塞进了文件夹内部
      （`…\\dist\\dist.zip`），而 7-Zip 的行为是生成在文件夹**旁边**
      （`…\\dist.zip`）。对文件而言 dirname 本就是其所在目录，语义一致。
    """
    dirs = [os.path.dirname(os.path.abspath(p)) for p in paths]
    if not dirs:
        return ""
    try:
        return os.path.commonpath(dirs)
    except ValueError:      # 跨盘符
        return dirs[0]


def archive_base_name(paths):
    """推导归档「基名」（不含扩展名）。

    单选文件 → 文件主干名；单选文件夹 → 文件夹名；多选 → 公共父目录名。
    """
    if len(paths) == 1:
        p = os.path.abspath(paths[0])
        if os.path.isdir(p):
            return os.path.basename(p.rstrip("\\/")) or "archive"
        return os.path.splitext(os.path.basename(p))[0] or "archive"
    d = common_dir(paths)
    return os.path.basename(d.rstrip("\\/")) or "archive"


def unique_path(path):
    """若目标已存在，追加 (2)(3)… 直到不冲突（快速压缩不做覆盖询问）。"""
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    i = 2
    while i < 10000:
        cand = f"{stem} ({i}){ext}"
        if not os.path.exists(cand):
            return cand
        i += 1
    return path


def archive_dir(paths, scope="file"):
    """归档应当生成在哪个目录。

    scope 三态（由右键菜单在命令行里用 `--scope` 传入）：
      • "bg"  —— 在某文件夹的**空白处**右键（命令用 %V，指向该文件夹）。
                 归档放进**该文件夹内部**，与 7-Zip「在文件夹里右键 →
                 Add to "<文件夹名>.7z"」一致。
      • 其它   —— 选中了文件/文件夹（命令用 %1）。归档放进被选中项目的
                 **所在目录**；对文件夹而言即它的**父目录**，
                 即「生成在文件夹旁边」。
    """
    if scope == "bg" and paths:
        p0 = os.path.abspath(paths[0])
        return p0 if os.path.isdir(p0) else os.path.dirname(p0)
    return common_dir(paths)


def quick_dest(paths, fmt, scope="file"):
    """快速压缩的目标路径：自动命名 + 自动避让重名（不做覆盖询问）。"""
    name = archive_base_name(paths) + formats.default_ext(fmt)
    return unique_path(os.path.join(archive_dir(paths, scope), name))


def extract_same_dir(archive_path):
    """「解压到同名文件夹」的目标目录：<所在目录>/<归档主干名>。"""
    ap = os.path.abspath(archive_path)
    stem = os.path.basename(ap)
    # 去掉复合扩展名（.tar.gz 这类）
    low = stem.lower()
    for compound in (".tar.gz", ".tar.bz2", ".tar.xz", ".tar.zst"):
        if low.endswith(compound):
            stem = stem[: -len(compound)]
            break
    else:
        stem = os.path.splitext(stem)[0]
    return os.path.join(os.path.dirname(ap), stem or "extracted")


def archives_of(paths):
    """从选中项里挑出真正的归档文件。"""
    return [p for p in paths if os.path.isfile(p) and formats.is_archive(p)]


def hash_rows(paths, verb):
    """计算校验值，返回可直接展示的文本行列表。

    verb == "hash_all" 时用 -scrc* 一次算出全部支持的算法。
    """
    rows = []
    for p in paths:
        ap = os.path.abspath(p)
        if not os.path.exists(ap):
            rows.append(f"[缺失] {p}")
            continue
        rows.append(os.path.basename(ap) if len(paths) > 1 else ap)
        if verb == "hash_all":
            data = engine.hash_all_data(ap)
            if not data:
                rows.append("    计算失败（文件不可读或无权限）")
            else:
                width = max(len(k) for k in data)
                for k in sorted(data):
                    rows.append(f"    {k.ljust(width)}  {data[k]}")
        else:
            algo, label = HASH_ALGOS.get(verb, ("SHA256", "SHA-256"))
            val = engine.hash_data(ap, algo)
            rows.append(f"    {label:<9}  {val or '计算失败'}")
        rows.append("")
    return rows


# ---------------------------------------------------------------------------
# 轻量界面（延迟导入 tkinter，保证本模块在无图形环境也能被导入/单测）
# ---------------------------------------------------------------------------
def _pick_font():
    return ("Microsoft YaHei UI", 9)


def _center(win, w, h):
    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()
    win.geometry(f"{w}x{h}+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 3)}")


class TaskWindow:
    """「执行中」小窗口：进度条 + 状态文字，禁止中途关闭。"""

    def __init__(self, title, status):
        import tkinter as tk
        import tkinter.ttk as ttk
        self.root = tk.Tk()
        self.root.title(title)
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", lambda: None)
        _center(self.root, 470, 138)
        try:
            self.root.attributes("-topmost", True)
        except Exception:
            pass
        try:
            ttk.Style().configure("TProgressbar", thickness=16)
        except Exception:
            pass
        self.status = tk.StringVar(value=status)
        tk.Label(self.root, textvariable=self.status, anchor="w",
                 font=_pick_font()).pack(fill="x", padx=16, pady=(18, 8))
        self.pb = ttk.Progressbar(self.root, mode="determinate",
                                  maximum=100, length=438)
        self.pb.pack(padx=16)
        self.detail = tk.StringVar(value="")
        tk.Label(self.root, textvariable=self.detail, anchor="w",
                 fg="#5a5a5a", font=_pick_font()).pack(fill="x", padx=16, pady=(6, 0))

    def update(self, pct, line=None):
        try:
            self.pb["value"] = max(self.pb["value"], pct)
        except Exception:
            pass
        if line:
            self.detail.set(line[:110])


def _run_task(title, status, work, on_finish):
    """在后台线程跑 work(progress_cb)，完成后回主线程调 on_finish(result)。

    work 需返回 dict（至少含 ok）。
    """
    win = TaskWindow(title, status)

    def cb(pct, line):
        win.root.after(0, lambda: win.update(pct, line))

    def finish(res):
        try:
            win.root.destroy()
        except Exception:
            pass
        try:
            on_finish(res)
        except Exception:
            pass

    def worker():
        try:
            res = work(cb)
        except Exception as e:
            res = {"ok": False, "error": f"{type(e).__name__}: {e}", "text": ""}
        win.root.after(0, lambda: finish(res))

    threading.Thread(target=worker, daemon=True).start()
    win.root.mainloop()


def _info(title, msg):
    import tkinter.messagebox as mb
    mb.showinfo(title, msg)


def _warn(title, msg):
    import tkinter.messagebox as mb
    mb.showwarning(title, msg)


def _err(title, msg):
    import tkinter.messagebox as mb
    mb.showerror(title, msg)


def _reveal(path):
    """在资源管理器中打开并选中该文件。"""
    try:
        import subprocess
        subprocess.Popen(["explorer", "/select,", os.path.abspath(path)])
    except Exception:
        pass


def _mailto_handler_exists():
    """本机是否配置了 mailto: 协议的处理程序（即默认邮件客户端）。

    没有的话，os.startfile("mailto:") 会让 Windows 弹出
    「该文件没有与之关联的应用来执行该操作」的报错框（与右键菜单
    那个 bug 是同一类系统弹窗）。所以先探测，缺失时走友好降级。
    """
    if sys.platform != "win32":
        return False
    try:
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for root in (r"Software\Classes\mailto\shell\open\command",
                         r"Software\Classes\mailto\shell\open"):
                try:
                    k = winreg.OpenKey(hive, root)
                    winreg.CloseKey(k)
                    return True
                except OSError:
                    continue
    except Exception:
        pass
    return False


def try_open_mailto(subject, body, dest=None):
    """起草含主题/正文的邮件。

    返回 True 表示已唤起邮件客户端；False 表示本机没有默认邮件客户端，
    此时会在资源管理器中选中 dest（若给了路径）方便用户手动拖入附件，
    并由调用方给出友好提示。绝不把系统报错框甩给用户。
    """
    if _mailto_handler_exists():
        try:
            os.startfile("mailto:?subject=" + quote(subject) + "&body=" + quote(body))
            return True
        except Exception:
            pass
    if dest:
        _reveal(dest)
    return False


def _error_line(res):
    text = res.get("text", "") or ""
    for ln in text.splitlines():
        if "Error" in ln or "error" in ln or "错误" in ln or "Cannot" in ln:
            return ln.strip()
    return res.get("error") or "未知错误"


# ---------------------------------------------------------------------------
# 动作实现
# ---------------------------------------------------------------------------
def _quick_compress(paths, fmt, scope="file"):
    sources = [os.path.abspath(p) for p in paths if os.path.exists(p)]
    if not sources:
        _warn("ZipForge", "未找到要压缩的文件或文件夹。")
        return
    if formats.is_single_stream(fmt) and any(os.path.isdir(s) for s in sources):
        _warn("ZipForge", f"{fmt.upper()} 不能压缩文件夹，请改用 7z 或 ZIP。")
        return
    dest = quick_dest(sources, fmt, scope)
    prefs = config.load_prefs()
    level = int(prefs.get("default_level", 5))
    solid = bool(prefs.get("solid", True))

    def work(cb):
        return engine.compress(sources, dest, fmt=fmt, level=level,
                               threads=0, solid=solid, on_progress=cb)

    def finish(res):
        if res.get("ok"):
            _info("压缩完成",
                  f"已生成：\n{dest}\n\n"
                  f"（格式 {fmt.upper()}，压缩级别 {level}）")
            _reveal(dest)
        else:
            _err("压缩失败", _error_line(res))

    _run_task(f"ZipForge — 压缩为 {fmt.upper()}",
              f"正在压缩 {len(sources)} 项…", work, finish)


def _quick_extract(paths, same_folder):
    arcs = archives_of(paths)
    if not arcs:
        _warn("ZipForge", "选中的项目里没有可解压的归档文件。")
        return
    dests = [(a, extract_same_dir(a) if same_folder else os.path.dirname(os.path.abspath(a)))
             for a in arcs]

    def work(cb):
        last = {"ok": True, "text": ""}
        for i, (arc, dest) in enumerate(dests):
            cb(int(i * 100 / len(dests)), f"正在解压 {os.path.basename(arc)} …")
            last = engine.extract_archive(arc, dest, on_progress=None)
            if not last.get("ok"):
                return last
        return last

    def finish(res):
        if res.get("ok"):
            lines = "\n".join(f"  {os.path.basename(a)}  →  {d}" for a, d in dests)
            _info("解压完成", "已解压：\n" + lines)
            if len(dests) == 1:
                _reveal(dests[0][1])
        else:
            _err("解压失败", _error_line(res))

    label = "同名文件夹" if same_folder else "当前文件夹"
    _run_task(f"ZipForge — 解压到{label}",
              f"正在解压 {len(arcs)} 个归档…", work, finish)


def _hash_dialog(title, text):
    import tkinter as tk
    import tkinter.ttk as ttk
    win = tk.Tk()
    win.title(title)
    _center(win, 660, 420)
    tk.Label(win, text=title, anchor="w", font=("Microsoft YaHei UI", 10, "bold")
             ).pack(fill="x", padx=14, pady=(12, 6))
    frame = ttk.Frame(win)
    frame.pack(fill="both", expand=True, padx=14)
    txt = tk.Text(frame, wrap="none", font=("Consolas", 9), height=14)
    txt.pack(side="left", fill="both", expand=True)
    sb = ttk.Scrollbar(frame, orient="vertical", command=txt.yview)
    txt.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y")
    txt.insert("1.0", text)
    txt.configure(state="disabled")

    bar = ttk.Frame(win)
    bar.pack(fill="x", padx=14, pady=10)

    def copy_all():
        win.clipboard_clear()
        win.clipboard_append(text)
        win.title(title + "  —  已复制到剪贴板")

    ttk.Button(bar, text="复制全部", command=copy_all).pack(side="left")
    ttk.Button(bar, text="关闭", command=win.destroy).pack(side="right")
    win.mainloop()


def _do_hash(paths, verb):
    names = [os.path.basename(p) for p in paths]
    title = ("全部校验值" if verb == "hash_all"
             else HASH_ALGOS.get(verb, ("", "SHA-256"))[1])
    label = f"ZipForge — {title}"

    def work(cb):
        cb(0, "正在计算…")
        rows = hash_rows(paths, verb)
        cb(100, "完成")
        return {"ok": True, "rows": rows}

    def finish(res):
        header = "对象：" + ("、".join(names) if len(names) <= 3 else f"{len(names)} 项") + "\n\n"
        _hash_dialog(label, header + "\n".join(res.get("rows", [])))

    _run_task("ZipForge — 计算校验值", "正在计算校验值…", work, finish)


def _compress_and_mail(paths, scope="file"):
    """压缩并在默认邮件客户端里起草一封带说明的新邮件。

    ⚠ 纯 exe 无法把文件「塞进」邮件（那需要 MAPI/COM 外壳扩展）。
      因此这里的做法是：压缩 → 唤起邮件客户端（预填主题/正文）→
      在资源管理器里选中刚生成的压缩包，用户直接拖入邮件即可。
      这是在没有外壳扩展的前提下最接近 7-Zip「压缩并发送邮件」的实现。
    """
    sources = [os.path.abspath(p) for p in paths if os.path.exists(p)]
    if not sources:
        _warn("ZipForge", "未找到要压缩的文件或文件夹。")
        return
    prefs = config.load_prefs()
    fmt = prefs.get("default_format", "7z")
    if fmt not in formats.CREATE_FORMATS:
        fmt = "7z"
    if formats.is_single_stream(fmt) and any(os.path.isdir(s) for s in sources):
        fmt = "7z"
    dest = quick_dest(sources, fmt, scope)
    level = int(prefs.get("default_level", 5))

    def work(cb):
        return engine.compress(sources, dest, fmt=fmt, level=level,
                               threads=0, solid=True, on_progress=cb)

    def finish(res):
        if not res.get("ok"):
            _err("压缩失败", _error_line(res))
            return
        subject = os.path.basename(dest)
        body = f"压缩包：{subject}\n（本机路径：{dest}）"
        opened = try_open_mailto(subject, body, dest=dest)
        if opened:
            _info("压缩完成，邮件已起草",
                  f"已生成：\n{dest}\n\n"
                  "已为你唤起邮件客户端，并在资源管理器中选中该压缩包。\n"
                  "请把选中的压缩包拖进邮件作为附件即可发送。")
        else:
            _warn("未检测到默认邮件客户端",
                  f"已生成压缩包：\n{dest}\n\n"
                  "本机没有设置默认的邮件客户端，无法直接起草邮件。\n"
                  "已在资源管理器中选中该压缩包，请手动拖入邮件作为附件发送。")

    _run_task("ZipForge — 压缩并发送邮件", f"正在压缩 {len(sources)} 项…", work, finish)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def run_headless(verb, paths, scope="file"):
    """执行无需主界面的动作；返回进程退出码。"""
    paths = [p for p in paths if p]
    if not paths:
        _warn("ZipForge", "没有收到要处理的文件路径。")
        return 2
    if verb in QUICK_FORMATS:
        _quick_compress(paths, QUICK_FORMATS[verb], scope)
    elif verb == "extract_here":
        _quick_extract(paths, same_folder=False)
    elif verb == "extract_same":
        _quick_extract(paths, same_folder=True)
    elif verb in HASH_ALGOS or verb == "hash_all":
        _do_hash(paths, verb)
    else:
        _warn("ZipForge", f"未知的右键动作：{verb}")
        return 2
    return 0


def try_handle(argv):
    """若 argv 是一个「无界面动作」，执行并返回 True（调用方应直接退出）。"""
    spec = parse(argv)
    verb = spec["verb"]
    if verb in shell_integration.HEADLESS_VERBS:
        run_headless(verb, spec["paths"], spec.get("scope", "file"))
        return True
    return False
