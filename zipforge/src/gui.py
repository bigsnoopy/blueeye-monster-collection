# -*- coding: utf-8 -*-
"""
gui.py — ZipForge 主界面（tkinter，零第三方依赖）。

设计目标：无广告、纯本地、功能向 7-Zip 看齐。
布局：菜单 + 工具栏 + 左目录树 / 右内容区（本地文件或归档内容）+ 状态栏/进度条。
所有耗时操作（压缩/解压/测试）在后台线程执行，避免界面卡死。
"""
import os
import sys
import threading
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.filedialog as fd
import tkinter.messagebox as mb
import tkinter.simpledialog as sd

import config
import formats
import sevenzip_engine as engine
import fileicons
import shell_integration
import themes


# 程序图标（方案 10「霓虹 ZF」），随包分发的相对路径
ICON_FILE = "assets/icon_zf_neon.ico"


def asset_path(rel):
    """定位随程序分发的资源：打包后从 _MEIPASS 取，源码运行则从项目根取。"""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        p = os.path.join(base, rel)
        if os.path.exists(p):
            return p
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (os.path.join(here, rel), os.path.join(os.path.dirname(here), rel)):
        if os.path.exists(cand):
            return cand
    return os.path.join(os.path.dirname(here), rel)


def set_app_user_model_id(appid="XMSG.ZipForge"):
    """让 Windows 任务栏使用 exe 自带图标与独立分组（而非 python 图标）。"""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(appid)
    except Exception:
        pass


# ----------------------------------------------------------------------------
# 后台任务框架：把引擎调用放到线程里跑，进度/结果通过队列回传主线程
# ----------------------------------------------------------------------------
class Worker(threading.Thread):
    def __init__(self, task, args, on_progress, on_done):
        super().__init__(daemon=True)
        self.task = task
        self.args = args
        self.on_progress = on_progress
        self.on_done = on_done
        self.result = None

    def run(self):
        try:
            self.result = self.task(*self.args)
        except Exception as e:
            self.result = {"ok": False, "error": str(e),
                           "text": getattr(e, "text", "")}
        if self.on_done:
            self.on_done(self.result)


class ZipForgeApp:
    APP_NAME = "ZipForge"
    TAGLINE = "无广告 · 本地优先 · 功能向 7-Zip 看齐"

    def __init__(self, root: tk.Tk, pending_sources=None, pending=None):
        self.root = root
        self.root.title(f"{self.APP_NAME}  —  {self.TAGLINE}")
        self._apply_window_icon()
        self.prefs = config.load_prefs()
        self.root.geometry(self.prefs.get("window_geometry", "1100x720"))
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.mode = "fs"            # 'fs' 本地文件 | 'archive' 归档浏览
        self.fs_path = os.path.abspath(os.path.expanduser("~"))
        self.archive_path = None
        self.archive_items = []     # 兼容字段（= archive_all_items）
        self.archive_all_items = [] # 归档内全部条目（用于按目录过滤）
        self.archive_prefix = ""     # 当前所在的归档内子目录（如 "资料/"）
        self._archive_row_full = {}  # 列表行 iid -> 条目在归档内的完整路径
        self._archive_row_isdir = {} # 列表行 iid -> 是否目录（双击行为依据）
        self._icon_cache = {}        # (扩展名, 是否目录) -> tk.PhotoImage（防止被 GC）
        self._rowheight = 24         # 列表行高，随系统图标实际高度自适应
        self.selected = []
        self._restart = False  # 切换主题后置位，main() 据此重建主窗口

        # 当前主题（从偏好读取；非法值回退到经典）
        self.theme = themes.get_theme(self.prefs.get("ui_theme"))

        # 启动后要立即执行的动作（由右键菜单 verb 传入）
        if pending is None and pending_sources:
            pending = {"action": "add", "paths": list(pending_sources)}
        self.pending = pending

        self._busy = False
        self._build_style()
        self._build_menubar()
        self._build_toolbar()
        self._build_main()
        self._build_statusbar()
        self._apply_prefs_dir()
        self.navigate(self.fs_path)
        # 清理历史临时提取目录（仅删 24 小时前的，避免影响正在被打开的文件）
        try:
            engine.purge_temp_dirs(24)
        except Exception:
            pass

        # 首次启动即自动集成右键菜单（无需用户手动点「集成」）
        self._auto_install_context()
        self.refresh_context_status()

        # 右键菜单入口：带文件/动作参数启动 exe 时，直接执行对应动作
        if self.pending:
            self.root.after(80, self._run_pending)

    # ---- 窗口图标（方案 10「霓虹 ZF」） ----
    def _apply_window_icon(self):
        try:
            p = asset_path(ICON_FILE)
            if os.path.exists(p):
                # default= 让所有子窗口（对话框）也继承该图标
                self.root.iconbitmap(default=p)
        except Exception:
            pass

    # ---- 样式 ----
    def _build_style(self):
        style = ttk.Style()
        # 把当前主题应用到 ttk 全局样式，并返回一组常用颜色
        self._colors = themes.apply_style(style, self.theme)
        # 应用整体背景
        self.root.configure(bg=self._colors["bg"])

    def _menu_opts(self):
        """tk.Menu 配色选项（受主题约束；Windows 原生菜单可能部分忽略）。"""
        return dict(
            bg=self.theme["title"], fg=self.theme["title_fg"],
            activebackground=self.theme["accent"],
            activeforeground=self.theme["accent_fg"],
            relief="flat", borderwidth=0)

    # ---- 菜单 ----
    def _build_menubar(self):
        mo = self._menu_opts()
        menubar = tk.Menu(self.root, **mo)
        f = tk.Menu(menubar, tearoff=0, **mo)
        f.add_command(label="打开归档…", command=self.open_archive)
        f.add_command(label="浏览本地目录…", command=self.browse_dir)
        f.add_separator()
        f.add_command(label="压缩所选…", command=self.compress_selected)
        f.add_command(label="解压…", command=self.extract_current)
        f.add_command(label="测试完整性", command=self.test_current)
        f.add_separator()
        f.add_command(label="退出", command=self.on_close)
        menubar.add_cascade(label="文件", menu=f)

        t = tk.Menu(menubar, tearoff=0, **mo)
        t.add_command(label="默认压缩设置…", command=self.open_settings)
        t.add_separator()
        # 外观主题切换
        t.add_command(label="外观主题…", command=self.open_theme_dialog)
        t.add_separator()
        # 右键菜单管理：安装是启动时自动完成的，这里提供「修复 / 移除」两个入口
        ctx = tk.Menu(t, tearoff=0, **mo)
        ctx.add_command(label="重新安装 / 修复右键菜单", command=self.install_context)
        ctx.add_command(label="移除右键菜单", command=self.remove_context)
        ctx.add_separator()
        ctx.add_command(label="状态：检查中…", command=self.refresh_context_status)
        self._ctx_menu = ctx
        self._ctx_status_idx = 3
        t.add_cascade(label="资源管理器右键菜单", menu=ctx)
        menubar.add_cascade(label="工具", menu=t)

        h = tk.Menu(menubar, tearoff=0, **mo)
        h.add_command(label="关于 ZipForge", command=self.show_about)
        h.add_command(label="开源组件 / 许可证", command=self.show_licenses)
        menubar.add_cascade(label="帮助", menu=h)
        self.root.config(menu=menubar)

    # ---- 工具栏 ----
    def _build_toolbar(self):
        bar = ttk.Frame(self.root, style="ToolBar.TFrame")
        bar.pack(side=tk.TOP, fill=tk.X, padx=4, pady=4)
        btns = [
            ("📂 打开", self.open_archive),
            ("⬆ 上级", self.go_up),
            ("🗜 压缩", self.compress_selected),
            ("📤 解压", self.extract_current),
            ("🔍 测试", self.test_current),
            ("⚙ 设置", self.open_settings),
        ]
        for label, cmd in btns:
            b = ttk.Button(bar, text=label, command=cmd, style="Accent.TButton")
            b.pack(side=tk.LEFT, padx=2)
        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, padx=6, fill=tk.Y)
        self.path_var = tk.StringVar()
        self.path_entry = ttk.Entry(bar, textvariable=self.path_var)
        self.path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        self.path_entry.bind("<Return>", lambda e: self.navigate(self.path_var.get()))

    # ---- 主区域：左树 + 右列表 ----
    def _build_main(self):
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=4, pady=2)

        # 左：目录树（本地磁盘 + 收藏）
        left = ttk.Frame(paned)
        self.tree = ttk.Treeview(left, show="tree", selectmode="browse")
        self.tree.heading("#0", text="本地磁盘")
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<<TreeviewOpen>>", self.on_tree_expand)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        paned.add(left, weight=1)

        # 右：内容列表
        right = ttk.Frame(paned)
        # ⚠ 关键：Treeview 的图标**只能**画在 #0（tree 列）里。
        #   之前用 show="headings" 把 #0 隐藏了，item(image=...) 写进去也完全
        #   不可见 —— 这就是"里面的文件都没有显示系统图标"的根因。
        #   现改为 show="tree headings"：名称+图标放 #0，其余列照旧。
        cols = ("size", "type", "mtime", "attr")
        self.listv = ttk.Treeview(right, columns=cols, show="tree headings",
                                  selectmode="extended")
        self.listv.heading("#0", text="名称")
        self.listv.heading("size", text="大小")
        self.listv.heading("type", text="类型")
        self.listv.heading("mtime", text="修改时间")
        self.listv.heading("attr", text="属性")
        self.listv.column("#0", width=320, minwidth=160, stretch=True)
        self.listv.column("size", width=100, anchor=tk.E)
        self.listv.column("type", width=100)
        self.listv.column("mtime", width=150)
        self.listv.column("attr", width=110)
        self.listv.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        vsb = ttk.Scrollbar(right, orient=tk.VERTICAL, command=self.listv.yview)
        self.listv.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.listv.bind("<Double-1>", self.on_list_double)
        self.listv.bind("<Button-3>", self.on_list_right)
        paned.add(right, weight=3)

        self._init_tree()

    # ---- 状态栏 ----
    def _build_statusbar(self):
        self.status = ttk.Frame(self.root, style="StatusBar.TFrame")
        self.status.pack(side=tk.BOTTOM, fill=tk.X)
        self.status_text = tk.StringVar(value="就绪")
        ttk.Label(self.status, textvariable=self.status_text,
                  anchor=tk.W, style="Status.TLabel").pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        self.progress = ttk.Progressbar(self.status, length=220,
                                        mode="determinate", maximum=100)
        self.progress.pack(side=tk.RIGHT, padx=4, pady=2)

    # ---- 目录树 ----
    def _init_tree(self):
        self.tree.delete(*self.tree.get_children())
        # 磁盘根
        for d in self._drives():
            self.tree.insert("", tk.END, text=d, values=[d], open=False,
                             tags=("drive",))
        # 收藏：主目录
        self.tree.insert("", tk.END, text="🏠 主目录", values=[os.path.expanduser("~")],
                         open=False)
        self.tree.insert("", tk.END, text="🖥 桌面",
                         values=[os.path.join(os.path.expanduser("~"), "Desktop")],
                         open=False)

    @staticmethod
    def _drives():
        drives = []
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            p = letter + ":\\"
            if os.path.isdir(p):
                drives.append(p)
        return drives

    def on_tree_expand(self, event):
        item = self.tree.focus()
        if not item:
            return
        path = self.tree.item(item, "values")
        if not path:
            return
        path = path[0]
        # 已展开的标记
        if self.tree.get_children(item):
            return
        try:
            for name in sorted(os.listdir(path)):
                full = os.path.join(path, name)
                if os.path.isdir(full):
                    self.tree.insert(item, tk.END, text=name, values=[full])
        except Exception:
            pass

    def on_tree_select(self, event):
        item = self.tree.focus()
        if not item:
            return
        vals = self.tree.item(item, "values")
        if vals:
            self.navigate(vals[0])

    # ---- 导航（本地文件） ----
    def navigate(self, path):
        if not path or not os.path.isdir(path):
            return
        self.mode = "fs"
        self.fs_path = os.path.abspath(path)
        self.path_var.set(self.fs_path)
        self.prefs["last_dir"] = self.fs_path
        config.save_prefs(self.prefs)
        self.listv.delete(*self.listv.get_children())
        try:
            entries = sorted(os.scandir(self.fs_path),
                            key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            mb.showerror("无法访问", f"没有权限访问：{path}")
            return
        for e in entries:
            is_dir = e.is_dir()
            sz = "" if is_dir else config.fmt_size(e.stat().st_size)
            mtime = _fmt_time(e.stat().st_mtime)
            kw = dict(text=e.name + ("/" if is_dir else ""),
                      values=(sz, "文件夹" if is_dir else _ext_type(e.name),
                              mtime, ""),
                      tags=("dir" if is_dir else "file",))
            icon = self._icon_for(e.name, is_dir)
            if icon is not None:
                kw["image"] = icon
            self.listv.insert("", tk.END, **kw)
        self.status_text.set(f"{path}  —  {len(entries)} 项")

    def go_up(self):
        if self.mode == "fs":
            parent = os.path.dirname(self.fs_path)
            if parent and parent != self.fs_path:
                self.navigate(parent)
        elif self.mode == "archive":
            self._archive_up()

    def browse_dir(self):
        d = fd.askdirectory(initialdir=self.fs_path)
        if d:
            self.navigate(d)

    # ---- 列表行辅助 ----
    def _row_name(self, iid):
        """取某行的显示名（目录带尾斜杠）。

        名称放在 #0 列（text），不在 values 里 —— 因为图标必须跟着 #0 走。
        所有"从选中行反推文件名"的地方都必须走这个方法。
        """
        try:
            return self.listv.item(iid, "text")
        except Exception:
            return ""

    def _icon_for(self, name, is_dir):
        """取系统图标；顺带按图标真实高度调整行高后返回 PhotoImage。

        高分屏下系统小图标可能是 20/24px，固定 rowheight=24 会把图标裁掉，
        因此这里按实际高度自适应（下限 24）。
        """
        ext = "" if is_dir else _ext(name)
        icon = fileicons.get_file_icon(ext, is_dir)
        if icon is None:
            return None
        self._icon_cache[(ext, is_dir)] = icon   # 持有引用，防止被 GC
        try:
            need = max(24, icon.height() + 6)
            if need != self._rowheight:
                self._rowheight = need
                ttk.Style().configure("Treeview", rowheight=need)
        except Exception:
            pass
        return icon

    def on_list_double(self, event):
        sel = self.listv.selection()
        if not sel:
            return
        iid = sel[0]
        name = self._row_name(iid)
        if self.mode == "fs":
            full = os.path.join(self.fs_path, name.rstrip("/"))
            if name.endswith("/"):
                self.navigate(full)
            elif os.path.isfile(full) and formats.is_archive(full):
                self.load_archive(full)
            elif os.path.isfile(full):
                self._open_external_file(full)
        else:  # archive 模式
            fullp = self._archive_row_full.get(iid, name)
            # 目录/文件的判定以渲染时记录的标记为准（不靠名字是否带 "/" 猜，
            # 因为归档里的目录条目可能不带尾斜杠 —— 这正是此前"打不开"的根因）
            is_dir = self._archive_row_isdir.get(iid, name.endswith("/"))
            if is_dir:
                self.archive_prefix = fullp if fullp.endswith("/") else fullp + "/"
                self._render_archive()
            else:
                # 双击文件：提取该文件到临时目录并用系统程序打开
                self._extract_and_open(fullp)

    def _open_external_file(self, full):
        try:
            os.startfile(full)
        except Exception as e:
            mb.showerror("打开失败", str(e))

    def _extract_and_open(self, fullp):
        """把归档内的单个条目提取到临时目录，再用系统默认程序打开。"""
        dest = engine.new_temp_dir("zf_open_")
        rel = fullp.replace("\\", "/").lstrip("/")

        def task():
            return engine.extract_archive(
                self.archive_path, dest, items=[rel], password=None)

        def after(res):
            if not res.get("ok"):
                self._show_engine_error("提取失败", res)
                return
            # 优先按归档内相对路径精确定位（最可靠）
            cand = os.path.join(dest, *[p for p in rel.split("/") if p])
            found = cand if os.path.isfile(cand) else None
            if not found:
                # 兜底：在提取结果里按文件名搜索（忽略归档内层级差异）
                base = os.path.basename(rel)
                for root, _, files in os.walk(dest):
                    if base in files:
                        found = os.path.join(root, base)
                        break
            if found:
                self.status_text.set(f"已提取并用系统程序打开：{os.path.basename(found)}")
                self._open_external_file(found)
            else:
                name = os.path.basename(rel) or rel
                mb.showerror(
                    "打开失败",
                    f"未能从归档中提取出「{name}」。\n\n"
                    "可能原因：\n"
                    "  • 该条目在归档里是一个文件夹（请双击进入浏览，而不是当文件打开）\n"
                    "  • 归档已加密，需要密码\n"
                    "  • 归档有分卷缺失导致该条目无法还原")
        self.run_with_progress("正在提取…", task, after)

    def on_list_right(self, event):
        sel = self.listv.selection()
        if not sel:
            return
        menu = tk.Menu(self.root, tearoff=0, **self._menu_opts())
        if self.mode == "archive":
            menu.add_command(label="解压所选到…", command=self.extract_selected)
            menu.add_command(label="测试归档", command=self.test_current)
        else:
            menu.add_command(label="压缩所选…", command=self.compress_selected)
        menu.tk_popup(event.x_root, event.y_root)

    # ---- 打开归档 ----
    def open_archive(self):
        path = fd.askopenfilename(
            title="选择归档文件",
            filetypes=[("归档文件", "*.7z *.zip *.rar *.tar *.gz *.bz2 *.xz "
                        "*.zst *.br *.lz4 *.lz5 *.liz *.wim *.iso *.cab *.arj "
                        "*.lzh *.chm *.msi *.deb *.rpm *.cpio *.tzst *.tgz *.txz"),
                       ("所有文件", "*.*")])
        if not path:
            return
        self.load_archive(path)

    def load_archive(self, path, password=None):
        self.set_busy(True)
        self.status_text.set(f"正在读取：{os.path.basename(path)} …")

        def task():
            return engine.list_archive(path, password=password)

        def done(res):
            self.set_busy(False)
            if res.get("error"):
                mb.showerror("打开失败", res["error"])
                return
            if not res.get("ok") and not res.get("items"):
                mb.showerror("打开失败",
                             "无法读取该归档，可能已损坏、需要密码，或格式不被支持。")
                return
            self.mode = "archive"
            self.archive_path = path
            self.archive_items = res.get("items", [])
            self.archive_all_items = res.get("items", [])
            self.archive_prefix = ""
            self.path_var.set(path)
            self._render_archive()

        # ⚠ 必须在主线程里更新界面：Worker 的回调运行在后台线程，
        #   直接在回调里碰 Tk（渲染列表、建 PhotoImage、弹窗）属于跨线程调用，
        #   会随机抛 "main thread is not in main loop" 或让界面卡死。
        #   这里统一改走 root.after(0, ...) 回到主线程 —— 与 run_with_progress 一致。
        Worker(task, (), None, lambda r: self.root.after(0, lambda: done(r))).start()

    # ---- 归档内目录导航渲染 ----
    def _render_archive(self):
        """按当前子目录 self.archive_prefix 过滤并渲染归档内容。"""
        self.listv.delete(*self.listv.get_children())
        self._archive_row_full = {}
        self._archive_row_isdir = {}
        # 条目索引：同时登记带/不带尾斜杠的路径，便于取元信息
        by_path = {}
        for it in self.archive_all_items:
            p = (it.get("path") or "").replace("\\", "/")
            by_path.setdefault(p, it)
            by_path.setdefault(p.rstrip("/"), it)
        rows = filter_archive_items(self.archive_all_items, self.archive_prefix)
        dir_count = 0
        file_count = 0
        for disp, is_dir, full in rows:
            it = by_path.get(full.rstrip("/") if is_dir else full, {})
            if is_dir:
                sz, typ = "", "文件夹"
                attr = "🔒" if it.get("encrypted") else ""
                mtime = it.get("modified", "")
            else:
                sz = config.fmt_size(it.get("size", 0))
                typ = _ext_type(disp)
                mtime = it.get("modified", "")
                method = (it.get("method") or "").strip()
                attr = (method + ("  🔒" if it.get("encrypted") else "")).strip()
            kw = dict(text=disp, values=(sz, typ, mtime, attr),
                      tags=("dir" if is_dir else "file",))
            icon = self._icon_for(disp, is_dir)
            if icon is not None:
                kw["image"] = icon
            iid = self.listv.insert("", tk.END, **kw)
            self._archive_row_full[iid] = full
            self._archive_row_isdir[iid] = is_dir
            if is_dir:
                dir_count += 1
            else:
                file_count += 1
        self.status_text.set(
            f"{os.path.basename(self.archive_path)}"
            + (f" → {self.archive_prefix.rstrip('/')}" if self.archive_prefix else "")
            + f" — {dir_count} 个文件夹，{file_count} 个文件")

    def _archive_up(self):
        """归档模式下返回上一级目录；已在根目录则关闭归档。"""
        if not self.archive_prefix:
            self.close_archive()
            return
        parts = self.archive_prefix.rstrip("/").split("/")
        parts = parts[:-1]
        self.archive_prefix = ("/".join(parts) + "/") if parts else ""
        self._render_archive()
        self.status_text.set(
            f"{os.path.basename(self.archive_path)}"
            + (f" → {self.archive_prefix.rstrip('/')}" if self.archive_prefix else ""))

    def close_archive(self):
        self.archive_path = None
        self.archive_items = []
        self.archive_all_items = []
        self.archive_prefix = ""
        self._archive_row_full = {}
        self._archive_row_isdir = {}
        self.navigate(self.fs_path)

    # ---- 压缩 ----
    def compress_selected(self):
        if self.mode != "fs":
            mb.showinfo("提示", "请在本地文件视图中选择要压缩的文件或文件夹。")
            return
        sel = self.listv.selection()
        if not sel:
            mb.showinfo("提示", "请先在右侧列表中选择要压缩的文件/文件夹。")
            return
        sources = [os.path.join(self.fs_path, self._row_name(s).rstrip("/"))
                   for s in sel]
        self._start_compress(sources)

    def _start_compress(self, sources, mail=False):
        """弹出压缩设置对话框并执行压缩（本地选择与右键菜单共用）。"""
        sources = [os.path.abspath(s) for s in sources if os.path.exists(s)]
        if not sources:
            mb.showinfo("提示", "没有可压缩的文件或文件夹。")
            return
        dlg = CompressDialog(self.root, self.prefs, sources)
        if not dlg.result:
            return
        opts = dlg.result
        # 单流格式（gz/bz2/xz/zst/br/lz4/lz5）不能直接压缩文件夹 —— 提前拦截，
        # 否则用户只会看到一句引擎报错（官方 7-Zip 同样是失败，但提示不友好）。
        if formats.is_single_stream(opts["fmt"]) and any(os.path.isdir(s) for s in sources):
            mb.showinfo(
                "该格式不能压缩文件夹",
                f"{opts['fmt'].upper()} 属于「单流压缩格式」，一次只能压缩单个文件，"
                "无法直接压缩文件夹。\n\n"
                "请改用：\n"
                "  • 7z  —— 压缩比最高，推荐\n"
                "  • ZIP —— 兼容性最好\n"
                "  • TAR —— 仅打包（不压缩）\n\n"
                "若确实要 .gz/.zst 这类小体积格式，可先打成 TAR 再压缩（如 .tar.gz）。")
            return
        # 目标路径（默认文件名与 7-Zip 一致：单文件=主干名 / 单文件夹=文件夹名 /
        # 多选=所在目录名）
        import cli_verbs as _cv
        default_name = (_safe_name(_cv.archive_base_name(sources))
                        + formats.default_ext(opts["fmt"]))
        dest = fd.asksaveasfilename(
            title="保存归档为", initialdir=self.fs_path,
            initialfile=default_name,
            defaultextension=formats.default_ext(opts["fmt"]),
            filetypes=[(opts["fmt"].upper(), "*" + formats.default_ext(opts["fmt"]))])
        if not dest:
            return

        def task():
            return engine.compress(
                sources, dest, fmt=opts["fmt"], level=opts["level"],
                threads=opts["threads"], solid=opts["solid"],
                password=opts["password"] or None,
                encrypt_header=opts["encrypt_header"], volume=opts["volume"] or None)

        self.run_with_progress("正在压缩…", task,
                               lambda r: self._after_compress(r, dest, mail=mail))

    def _open_compress_for(self, sources, mail=False, scope="file"):
        """右键菜单入口：选中若干文件/文件夹启动 exe 时，先定位到归档应生成的目录，
        再直接弹出压缩设置对话框。

        scope（来自注册表命令行）：
          • "bg" —— 在某文件夹**空白处**右键，归档应生成在**该文件夹内部**；
          • 其它 —— 选中了文件/文件夹，归档生成在**选中项的所在目录**
                    （对文件夹而言就是它的**父目录**，即「生成在文件夹旁边」）。
        """
        sources = [os.path.abspath(s) for s in sources if os.path.exists(s)]
        if not sources:
            mb.showinfo("提示", "未找到可压缩的文件或文件夹。")
            return
        if scope == "bg" and len(sources) == 1:
            # 空白处右键：目标目录就是该文件夹自身（进得去、放里面）
            p0 = sources[0]
            target = p0 if os.path.isdir(p0) else os.path.dirname(p0)
        else:
            # 选中项所在目录的公共路径（跨盘符时退化为首项所在目录）
            try:
                target = (os.path.commonpath([os.path.dirname(s) for s in sources])
                          if len(sources) > 1 else os.path.dirname(sources[0]))
            except ValueError:
                target = os.path.dirname(sources[0])
            if os.path.isfile(target):
                target = os.path.dirname(target)
        if target and os.path.isdir(target):
            self.fs_path = target
            self.mode = "fs"
            self.navigate(target)
        self._start_compress(sources, mail=mail)

    def _after_compress(self, res, dest, mail=False):
        if res.get("ok"):
            if mail:
                self._mail_after_compress(dest)
            else:
                mb.showinfo("完成", f"压缩完成：\n{dest}")
            self.navigate(os.path.dirname(os.path.abspath(dest)))
        else:
            self._show_engine_error("压缩失败", res)

    def _mail_after_compress(self, dest):
        """压缩完成后起草邮件并把压缩包在资源管理器中选中（便于拖入作附件）。"""
        from urllib.parse import quote
        from cli_verbs import try_open_mailto
        subject = os.path.basename(dest)
        body = f"压缩包：{subject}\n（本机路径：{dest}）"
        opened = try_open_mailto(subject, body, dest=dest)
        if opened:
            mb.showinfo("压缩完成，邮件已起草",
                        f"已生成：\n{dest}\n\n"
                        "已为你唤起邮件客户端，并在资源管理器中选中该压缩包。\n"
                        "请把选中的压缩包拖入邮件作为附件即可发送。")
        else:
            mb.showwarning("未检测到默认邮件客户端",
                           f"已生成压缩包：\n{dest}\n\n"
                           "本机没有设置默认的邮件客户端，无法直接起草邮件。\n"
                           "已在资源管理器中选中该压缩包，请手动拖入邮件作为附件发送。")

    # ---- 解压 ----
    def extract_current(self):
        if self.mode != "archive" or not self.archive_path:
            mb.showinfo("提示", "请先打开一个归档文件。")
            return
        self.extract_selected()

    def extract_selected(self):
        if self.mode != "archive" or not self.archive_path:
            return
        sel = self.listv.selection()
        if sel:
            items = []
            for s in sel:
                full = self._archive_row_full.get(s, self._row_name(s))
                items.append(full.rstrip("/"))
        else:
            items = None
        dlg = ExtractDialog(self.root, self.prefs, has_selection=bool(sel))
        if not dlg.result:
            return
        opts = dlg.result
        if opts.get("dest"):
            dest = opts["dest"]
        else:
            dest = fd.askdirectory(title="选择解压目标目录",
                                  initialdir=self.prefs.get("last_dir") or self.fs_path)
        if not dest:
            return

        def task():
            return engine.extract_archive(
                self.archive_path, dest, items=items,
                password=opts.get("password") or None,
                overwrite=opts.get("overwrite", "ask"))

        self.run_with_progress("正在解压…", task,
                               lambda r: self._after_extract(r, dest))

    def _after_extract(self, res, dest):
        if res.get("ok"):
            mb.showinfo("完成", f"解压完成：\n{dest}")
        else:
            self._show_engine_error("解压失败", res)

    # ---- 测试 ----
    def test_current(self):
        if self.mode != "archive" or not self.archive_path:
            mb.showinfo("提示", "请先打开一个归档文件。")
            return
        dlg = PasswordOnlyDialog(self.root, "测试归档（如已加密请输入密码）")
        pw = dlg.result

        def task():
            return engine.test_archive(self.archive_path, password=pw or None)

        self.run_with_progress("正在测试…", task,
                               lambda r: self._after_test(r))

    def _after_test(self, res):
        if res.get("ok"):
            mb.showinfo("测试通过", "归档完整，无损坏。")
        else:
            self._show_engine_error("测试未通过", res)

    # ---- 通用：带进度的后台执行 ----
    def run_with_progress(self, label, task, on_done):
        if self._busy:
            return
        self.set_busy(True)
        self.progress["value"] = 0
        self.status_text.set(label)
        log_lines = []

        def on_progress(pct, line):
            self.root.after(0, lambda: self._update_progress(pct, line))

        def done(res):
            self.root.after(0, lambda: self._finish_progress())
            self.root.after(0, lambda: on_done(res))

        Worker(task, (), on_progress, done).start()

    def _update_progress(self, pct, line):
        self.progress["value"] = max(self.progress["value"], pct)
        if line:
            self.status_text.set(line[:120])

    def _finish_progress(self):
        self.set_busy(False)
        self.progress["value"] = 100
        # 清掉"正在解压…"之类的过程提示，避免操作结束后面条还停在旧文案上
        self.status_text.set("就绪")

    def _show_engine_error(self, title, res):
        text = res.get("text", "")
        err = res.get("error") or "未知错误"
        # 截取关键错误行
        for ln in text.splitlines():
            if "Error" in ln or "error" in ln or "错误" in ln:
                err = ln.strip()
                break
        mb.showerror(title, err)

    def set_busy(self, b):
        self._busy = b
        state = tk.DISABLED if b else tk.NORMAL
        # 禁用主操作按钮可在此扩展

    # ---- 设置 ----
    def open_settings(self):
        dlg = SettingsDialog(self.root, self.prefs)
        if dlg.result:
            self.prefs.update(dlg.result)
            config.save_prefs(self.prefs)

    def _apply_prefs_dir(self):
        if self.prefs.get("last_dir") and os.path.isdir(self.prefs["last_dir"]):
            self.fs_path = self.prefs["last_dir"]

    # ---- 右键菜单集成 ----
    def _auto_install_context(self):
        """启动时**自动**集成右键菜单（用户无需手动点击「集成」）。

        - 仅 Windows 生效；
        - 若用户曾主动「移除右键菜单」，尊重其选择，不再自动安装；
        - exe 路径变化（换位置 / 从源码切到打包 exe）时自动修复指向。
        """
        if sys.platform != "win32":
            return
        # 测试/自检进程里绝不写真实注册表（ZF_NO_CTX=1）
        if os.environ.get("ZF_NO_CTX"):
            return
        if self.prefs.get("context_menu") == "removed":
            return
        try:
            cur = shell_integration.exe_path()
            reg = shell_integration.registered_exe()
            need = (not shell_integration.is_registered()
                    or os.path.normcase(reg) != os.path.normcase(cur)
                    or self.prefs.get("context_menu_exe") != cur)
            if not need:
                return
            ok, _msg = shell_integration.register()
            if not ok:
                return
            self.prefs["context_menu"] = "auto"
            self.prefs["context_menu_exe"] = cur
            first_time = not self.prefs.get("context_menu_notified")
            if first_time:
                self.prefs["context_menu_notified"] = True
            config.save_prefs(self.prefs)
            if first_time:
                self.root.after(700, self._notify_context_installed)
        except Exception:
            pass

    def _notify_context_installed(self):
        mb.showinfo(
            "右键菜单已自动集成",
            "ZipForge 已自动把常用操作加入资源管理器右键菜单：\n\n"
            "    ZipForge ▸ 解压到当前文件夹 / 解压到同名文件夹\n"
            "              添加到压缩包… / 压缩并发送邮件…\n"
            "              快速压缩为 7z / 快速压缩为 ZIP\n"
            "              CRC-32 / SHA-256 / 全部校验值…\n\n"
            "选中即直接执行，不必先进本程序。\n\n"
            "不想要的话：「工具 → 资源管理器右键菜单 → 移除右键菜单」一键删除。")

    def refresh_context_status(self):
        """刷新「工具」菜单里的集成状态文字，并返回状态字典。"""
        try:
            st = shell_integration.status()
        except Exception:
            st = {"supported": False, "installed": False, "items": 0, "stale": False}
        if not st.get("supported"):
            txt = "状态：当前系统不支持（仅 Windows）"
        elif st.get("installed"):
            txt = f"状态：已集成（{st.get('items', 0)} 个操作）"
            if st.get("stale"):
                txt += "　⚠ 指向已失效，建议修复"
        else:
            txt = "状态：未集成 —— 点击上一项安装"
        try:
            self._ctx_menu.entryconfigure(self._ctx_status_idx, label=txt)
        except Exception:
            pass
        return st

    def install_context(self):
        if sys.platform != "win32":
            mb.showinfo("不支持", "右键菜单集成仅支持 Windows 系统。")
            return
        ok, msg = shell_integration.register()
        if ok:
            self.prefs["context_menu"] = "auto"
            self.prefs["context_menu_exe"] = shell_integration.exe_path()
            config.save_prefs(self.prefs)
        self.refresh_context_status()
        (mb.showinfo if ok else mb.showerror)("完成" if ok else "失败", msg)

    def remove_context(self):
        if sys.platform != "win32":
            mb.showinfo("不支持", "右键菜单集成仅支持 Windows 系统。")
            return
        ok, msg = shell_integration.unregister()
        if ok:
            # 记住「用户不要」，以后启动不再自动安装
            self.prefs["context_menu"] = "removed"
            self.prefs["context_menu_exe"] = None
            config.save_prefs(self.prefs)
            msg += ("\n\n已记住该选择：今后启动不会再自动集成。\n"
                    "如需恢复：工具 → 资源管理器右键菜单 → 重新安装 / 修复。")
        self.refresh_context_status()
        mb.showinfo("结果", msg)

    # ---- 外观主题切换 ----
    def open_theme_dialog(self):
        dlg = ThemeDialog(self.root, self.prefs, self.theme)
        if dlg.result and dlg.result != self.prefs.get("ui_theme"):
            self.prefs["ui_theme"] = dlg.result
            self.prefs["window_geometry"] = self.root.geometry()
            config.save_prefs(self.prefs)
            # 通过重建主窗口让新主题干净生效
            self._restart = True
            self.root.destroy()

    # ---- 启动动作（右键菜单 → 主界面弹窗） ----
    def _navigate_to(self, d):
        if d and os.path.isdir(d):
            self.fs_path = d
            self.mode = "fs"
            self.navigate(d)

    def _run_pending(self):
        """执行启动时携带的动作（add / addmail / extract_to / test / new）。"""
        spec = self.pending or {}
        action = spec.get("action")
        paths = [p for p in (spec.get("paths") or []) if p]
        if not paths:
            return
        try:
            if action in ("extract_to", "test"):
                arc = next((p for p in paths if os.path.isfile(p)), None)
                if not arc:
                    mb.showinfo("提示", "未找到可读取的归档文件。")
                    return
                self._navigate_to(os.path.dirname(os.path.abspath(arc)))
                self._load_archive_then(arc, action)
            else:
                self._open_compress_for(paths, mail=(action == "addmail"),
                                        scope=spec.get("scope", "file"))
        except Exception as e:
            mb.showerror("操作失败", str(e))

    def _load_archive_then(self, path, action):
        """打开归档，随后按 action 继续（extract_to=弹解压对话框 / test=测试）。"""
        self.set_busy(True)
        self.status_text.set(f"正在读取：{os.path.basename(path)} …")

        def task():
            return engine.list_archive(path)

        def done(res):
            self.set_busy(False)
            if not res.get("items"):
                mb.showerror("打开失败",
                             res.get("error") or "无法读取该归档。")
                return
            self.mode = "archive"
            self.archive_path = path
            self.archive_items = res.get("items", [])
            self.archive_all_items = res.get("items", [])
            self.archive_prefix = ""
            self.path_var.set(path)
            self._render_archive()
            if action == "extract_to":
                self.extract_selected()
            elif action == "test":
                self.test_current()

        Worker(task, (), None,
               lambda r: self.root.after(0, lambda: done(r))).start()

    # ---- 关于 / 许可证 ----
    def show_about(self):
        """自定义「关于」窗口：显示程序图标（方案 10「霓虹 ZF」）+ 说明。"""
        c = self._colors
        bg = c.get("bg", "#ffffff")
        fg = c.get("fg", "#111111")
        acc = c.get("accent", "#2f6fdb")
        muted = c.get("muted", "#7a8499")
        fam = self.theme.get("font", "Segoe UI")

        win = tk.Toplevel(self.root)
        win.title("关于 ZipForge")
        win.configure(bg=bg)
        win.resizable(False, False)
        try:
            win.transient(self.root)
        except Exception:
            pass
        try:
            win.iconbitmap(default=asset_path(ICON_FILE))
        except Exception:
            pass

        # 图标（Tk 8.6 直接读 PNG；失败则静默跳过）
        try:
            png = asset_path("assets/icon_zf_neon_128.png")
            if os.path.exists(png):
                photo = tk.PhotoImage(file=png)
                lbl = tk.Label(win, image=photo, bg=bg, bd=0)
                lbl.image = photo          # 防止被 GC
                lbl.pack(pady=(20, 8))
        except Exception:
            pass

        tk.Label(win, text=self.APP_NAME, bg=bg, fg=acc,
                 font=(fam, 18, "bold")).pack()
        tk.Label(win, text=self.TAGLINE, bg=bg, fg=muted,
                 font=(fam, 10)).pack(pady=(2, 12))
        tk.Label(win, justify=tk.LEFT, bg=bg, fg=fg, font=(fam, 10),
                 wraplength=420,
                 text=("一个无广告、纯本地、面向个人使用的压缩管理软件。\n"
                       "压缩内核来自开源项目 7-Zip-ZS（mcmilk），整合了 Zstandard / "
                       "Brotli / LZ4 / Lizard / Fast-LZMA2 等编解码器，"
                       "功能覆盖并超越官方 7-Zip。\n\n"
                       "本软件不联网、不收集任何数据、不推送任何广告。")
                 ).pack(padx=26, pady=(0, 6))

        ttk.Button(win, text="确定", style="Accent.TButton",
                   command=win.destroy).pack(pady=(6, 18))
        try:
            win.grab_set()
        except Exception:
            pass
        win.focus_set()

    def show_licenses(self):
        mb.showinfo("开源组件与许可证",
                    "ZipForge 合并/复用了以下开源项目的能力：\n\n"
                    "• 7-Zip-ZS (mcmilk/7-Zip-zstd)\n"
                    "  LGPL-2.1+ / BSD — 7z 引擎超集（ZSTD/Brotli/LZ4/Lizard/FLZMA2）\n"
                    "• 7-Zip (ip7z/7zip, Igor Pavlov)\n"
                    "  LGPL-2.1+ — 原始压缩算法与格式\n"
                    "• PeaZip (peazip) — GUI/UX 设计参考（LGPL-3.0）\n"
                    "• NanaZip (M2Team) — 现代 Windows 交互参考（MIT）\n\n"
                    "本程序仅作为这些开源引擎的图形外壳，不修改其二进制行为。\n"
                    "详细许可证文本见 vendor/engine-x64/7ZIP-ZS-LICENSE.txt")

    def on_close(self):
        self.prefs["window_geometry"] = self.root.geometry()
        config.save_prefs(self.prefs)
        self.root.destroy()


# ----------------------------------------------------------------------------
# 时间格式化
# ----------------------------------------------------------------------------
def _fmt_time(ts):
    try:
        import datetime
        # 与归档视图的时间格式保持一致（归档侧的 Modified 由引擎归一化到秒）
        return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def _ext_type(name):
    ext = os.path.splitext(name)[1].lower()
    if not ext:
        return "文件"
    return ext[1:].upper() + " 文件"


def _ext(name):
    """返回不含点的小写扩展名；无扩展名返回空串。"""
    return os.path.splitext(name)[1].lstrip(".").lower()


def _safe_name(n):
    n = os.path.splitext(n)[0]
    return n or "archive"


# ----------------------------------------------------------------------------
# 归档内目录过滤（纯函数，便于无界面单元测试）
# ----------------------------------------------------------------------------
def filter_archive_items(items, prefix: str):
    """把归档全部条目按 prefix 子目录过滤，返回当前层级的显示行。

    返回 [(display_name, is_dir, full_path), ...]：
      - 目录：display_name 以 "/" 结尾（供 UI 判断），full_path 为归档内完整路径（带尾 /）
      - 文件：display_name 为相对文件名，full_path 为归档内完整路径

    要点（都是实测踩过的坑）：
      1. 7z 输出的路径在 Windows 上是反斜杠（`远特结题\\a.docx`），此处统一归一化为 "/"。
      2. 归档里**显式目录条目**的 path 不带尾斜杠（如 `远特结题`，Folder=+），
         而由文件路径又能推断出同一个目录（`远特结题/`）。
         两者必须**合并去重**，否则会出现 "远特结题/" 和 "远特结题" 两行，
         且后者因不带尾斜杠会被误判成文件。
      3. 显式目录条目必须补上尾斜杠，保证 UI 一定按"目录"处理。
    """
    dirs = set()
    files = []
    seen_files = set()
    for it in items:
        full = (it.get("path") or "").replace("\\", "/")
        if not full.startswith(prefix):
            continue
        rest = full[len(prefix):].lstrip("/")
        if not rest:
            continue
        rest_clean = rest.rstrip("/")
        if "/" in rest_clean:
            # 更深层的条目：只聚合出它所在的一级目录
            dirs.add(prefix + rest_clean.split("/", 1)[0] + "/")
        elif it.get("folder") or rest.endswith("/"):
            dirs.add(prefix + rest_clean + "/")
        elif full not in seen_files:
            seen_files.add(full)
            files.append((rest_clean, full))

    rows = [(d[len(prefix):], True, d) for d in sorted(dirs, key=lambda s: s.lower())]
    rows += [(n, False, f) for n, f in sorted(files, key=lambda t: t[0].lower())]
    return rows


# ----------------------------------------------------------------------------
# 对话框们
# ----------------------------------------------------------------------------
class CompressDialog(tk.Toplevel):
    def __init__(self, parent, prefs, sources):
        super().__init__(parent)
        self.title("压缩设置")
        self.result = None
        self.transient(parent)
        self.grab_set()
        self.sources = sources

        ttk.Label(self, text=f"将压缩 {len(sources)} 个项目：").grid(
            row=0, column=0, columnspan=2, sticky=tk.W, padx=10, pady=6)
        for s in sources[:3]:
            ttk.Label(self, text="  • " + s, foreground="#555").grid(
                row=0, column=0, columnspan=2, sticky=tk.W, padx=24)
        if len(sources) > 3:
            ttk.Label(self, text=f"  • … 等 {len(sources)} 项",
                      foreground="#555").grid(row=0, column=0, columnspan=2,
                                              sticky=tk.W, padx=24)

        row = 1
        ttk.Label(self, text="格式：").grid(row=row, column=0, sticky=tk.W, padx=10)
        self.fmt = tk.StringVar(value=prefs.get("default_format", "7z"))
        cb = ttk.Combobox(self, textvariable=self.fmt, width=18,
                          values=list(formats.CREATE_FORMATS.keys()),
                          state="readonly")
        cb.grid(row=row, column=1, padx=10, pady=3)

        row += 1
        ttk.Label(self, text="压缩级别：").grid(row=row, column=0, sticky=tk.W, padx=10)
        self.level = tk.IntVar(value=prefs.get("default_level", 5))
        sc = ttk.Scale(self, from_=0, to=9, variable=self.level, orient=tk.HORIZONTAL,
                       length=160, command=lambda v: self._lv.set(f"级别 {int(float(v))}："
                       + formats.LEVEL_PRESETS.get(int(float(v)), "")))
        sc.grid(row=row, column=1, padx=10, pady=3)
        self._lv = tk.StringVar()
        ttk.Label(self, textvariable=self._lv, foreground="#666").grid(
            row=row + 1, column=1, sticky=tk.W, padx=10)
        self._lv.set(f"级别 {self.level.get()}："
                     + formats.LEVEL_PRESETS.get(self.level.get(), ""))
        row += 2

        ttk.Label(self, text="密码（可选）：").grid(row=row, column=0, sticky=tk.W, padx=10)
        self.pw = tk.StringVar()
        ttk.Entry(self, textvariable=self.pw, show="*", width=20).grid(
            row=row, column=1, padx=10, pady=3)

        row += 1
        ttk.Label(self, text="分卷大小（可选）：").grid(row=row, column=0, sticky=tk.W, padx=10)
        self.vol = tk.StringVar()
        ttk.Entry(self, textvariable=self.vol, width=20).grid(
            row=row, column=1, padx=10, pady=3)
        ttk.Label(self, text="例：100m / 2g / 700m", foreground="#888").grid(
            row=row + 1, column=1, sticky=tk.W, padx=10)
        row += 2

        self.solid = tk.BooleanVar(value=prefs.get("solid", True))
        self.mhe = tk.BooleanVar(value=prefs.get("encrypt_header", False))
        ttk.Checkbutton(self, text="固实压缩（更高压缩比）", variable=self.solid).grid(
            row=row, column=0, columnspan=2, sticky=tk.W, padx=10)
        row += 1
        ttk.Checkbutton(self, text="加密文件头（不输密码看不到文件名，仅 7z）",
                        variable=self.mhe).grid(row=row, column=0, columnspan=2,
                                                sticky=tk.W, padx=10)
        row += 1
        self._auto_thread = tk.BooleanVar(value=True)
        ttk.Checkbutton(self, text="使用全部 CPU 线程（多线程加速）",
                        variable=self._auto_thread).grid(
            row=row, column=0, columnspan=2, sticky=tk.W, padx=10)
        row += 2

        bf = ttk.Frame(self)
        bf.grid(row=row, column=0, columnspan=2, pady=10)
        ttk.Button(bf, text="开始压缩", command=self.ok).pack(side=tk.LEFT, padx=8)
        ttk.Button(bf, text="取消", command=self.cancel).pack(side=tk.LEFT, padx=8)
        self.wait_window()

    def ok(self):
        fmt = self.fmt.get()
        if fmt not in formats.CREATE_FORMATS:
            mb.showerror("格式错误", "请选择有效的压缩格式。")
            return
        self.result = {
            "fmt": fmt,
            "level": self.level.get(),
            "password": self.pw.get(),
            "volume": self.vol.get().strip(),
            "solid": self.solid.get(),
            "encrypt_header": self.mhe.get(),
            "threads": 0 if self._auto_thread.get() else 1,
        }
        self.destroy()

    def cancel(self):
        self.destroy()


class ExtractDialog(tk.Toplevel):
    def __init__(self, parent, prefs, has_selection):
        super().__init__(parent)
        self.title("解压设置")
        self.result = None
        self.transient(parent)
        self.grab_set()

        ttk.Label(self, text=("将解压所选条目" if has_selection else "将解压整个归档")
                  ).grid(row=0, column=0, columnspan=2, sticky=tk.W, padx=10, pady=6)

        ttk.Label(self, text="解压到：").grid(row=1, column=0, sticky=tk.W, padx=10)
        self.dest = tk.StringVar()
        ttk.Entry(self, textvariable=self.dest, width=30).grid(row=1, column=1, padx=10, pady=3)
        ttk.Button(self, text="浏览…", command=self._browse).grid(row=1, column=2, padx=4)

        ttk.Label(self, text="覆盖方式：").grid(row=2, column=0, sticky=tk.W, padx=10)
        self.ow = tk.StringVar(value=prefs.get("overwrite", "ask"))
        ttk.Combobox(self, textvariable=self.ow, width=18, state="readonly",
                     values=["ask", "yes", "skip", "fresh", "rename"]).grid(
            row=2, column=1, padx=10, pady=3)
        ttk.Label(self, text="ask=覆盖 / skip=跳过 / fresh=仅新 / rename=改名",
                  foreground="#888").grid(row=3, column=1, sticky=tk.W, padx=10)

        ttk.Label(self, text="密码（可选）：").grid(row=4, column=0, sticky=tk.W, padx=10)
        self.pw = tk.StringVar()
        ttk.Entry(self, textvariable=self.pw, show="*", width=20).grid(
            row=4, column=1, padx=10, pady=3)

        bf = ttk.Frame(self)
        bf.grid(row=5, column=0, columnspan=3, pady=10)
        ttk.Button(bf, text="开始解压", command=self.ok).pack(side=tk.LEFT, padx=8)
        ttk.Button(bf, text="取消", command=self.cancel).pack(side=tk.LEFT, padx=8)
        self.wait_window()

    def _browse(self):
        d = fd.askdirectory()
        if d:
            self.dest.set(d)

    def ok(self):
        self.result = {"dest": self.dest.get().strip(),
                      "overwrite": self.ow.get(), "password": self.pw.get()}
        self.destroy()

    def cancel(self):
        self.destroy()


class PasswordOnlyDialog(tk.Toplevel):
    def __init__(self, parent, title):
        super().__init__(parent)
        self.title(title)
        self.result = None
        self.transient(parent)
        self.grab_set()
        ttk.Label(self, text="密码（若未加密可留空）：").pack(padx=10, pady=6)
        self.pw = tk.StringVar()
        ttk.Entry(self, textvariable=self.pw, show="*", width=24).pack(padx=10, pady=3)
        bf = ttk.Frame(self)
        bf.pack(pady=8)
        ttk.Button(bf, text="确定", command=self.ok).pack(side=tk.LEFT, padx=8)
        ttk.Button(bf, text="取消", command=self.cancel).pack(side=tk.LEFT, padx=8)
        self.wait_window()

    def ok(self):
        self.result = self.pw.get()
        self.destroy()

    def cancel(self):
        self.result = None
        self.destroy()


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, prefs):
        super().__init__(parent)
        self.title("默认压缩设置")
        self.result = None
        self.transient(parent)
        self.grab_set()

        ttk.Label(self, text="默认格式：").grid(row=0, column=0, sticky=tk.W, padx=10)
        self.fmt = tk.StringVar(value=prefs.get("default_format", "7z"))
        ttk.Combobox(self, textvariable=self.fmt, width=18, state="readonly",
                     values=list(formats.CREATE_FORMATS.keys())).grid(
            row=0, column=1, padx=10, pady=3)

        ttk.Label(self, text="默认级别：").grid(row=1, column=0, sticky=tk.W, padx=10)
        self.level = tk.IntVar(value=prefs.get("default_level", 5))
        ttk.Scale(self, from_=0, to=9, variable=self.level, orient=tk.HORIZONTAL,
                  length=160).grid(row=1, column=1, padx=10, pady=3)

        ttk.Label(self, text="默认覆盖方式：").grid(row=2, column=0, sticky=tk.W, padx=10)
        self.ow = tk.StringVar(value=prefs.get("overwrite", "ask"))
        ttk.Combobox(self, textvariable=self.ow, width=18, state="readonly",
                     values=["ask", "yes", "skip", "fresh", "rename"]).grid(
            row=2, column=1, padx=10, pady=3)

        bf = ttk.Frame(self)
        bf.grid(row=3, column=0, columnspan=2, pady=10)
        ttk.Button(bf, text="保存", command=self.ok).pack(side=tk.LEFT, padx=8)
        ttk.Button(bf, text="取消", command=self.cancel).pack(side=tk.LEFT, padx=8)
        self.wait_window()

    def ok(self):
        self.result = {"default_format": self.fmt.get(),
                      "default_level": self.level.get(),
                      "overwrite": self.ow.get()}
        self.destroy()

    def cancel(self):
        self.destroy()


# ----------------------------------------------------------------------------
class ThemeDialog(tk.Toplevel):
    """外观主题选择器：左侧 11 套列表，右侧实时预览（标题栏 / 列表 / 色板）。"""

    def __init__(self, parent, prefs, current_theme):
        super().__init__(parent)
        self.title("外观主题")
        self.result = None
        self.transient(parent)
        self.grab_set()
        self.current = prefs.get("ui_theme", "classic")

        ttk.Label(self, text="选择 ZipForge 的外观主题（共 11 套，含默认经典）："
                  ).pack(anchor=tk.W, padx=12, pady=(12, 6))

        body = ttk.Frame(self)
        body.pack(fill=tk.BOTH, expand=True, padx=12)

        lb_frame = ttk.Frame(body)
        lb_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        self.lb = tk.Listbox(lb_frame, width=28, height=13, font=("Segoe UI", 10))
        for key in themes.ORDER:
            self.lb.insert(tk.END, themes.THEMES[key]["name"])
        self.lb.pack(side=tk.LEFT, fill=tk.Y)
        self.lb.bind("<<ListboxSelect>>", self._on_select)
        self.lb.bind("<Double-1>", self._on_ok)
        try:
            idx = themes.ORDER.index(self.current)
            self.lb.selection_set(idx)
            self.lb.see(idx)
        except ValueError:
            pass

        self.preview = ttk.Frame(body)
        self.preview.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._preview_key = None
        self._on_select(None)

        bf = ttk.Frame(self)
        bf.pack(fill=tk.X, padx=12, pady=10)
        ttk.Button(bf, text="应用", command=self._on_ok).pack(side=tk.RIGHT, padx=6)
        ttk.Button(bf, text="取消", command=self.cancel).pack(side=tk.RIGHT, padx=6)
        self.wait_window()

    def _on_select(self, _e):
        sel = self.lb.curselection()
        if not sel:
            return
        key = themes.ORDER[sel[0]]
        if key == self._preview_key:
            return
        self._preview_key = key
        th = themes.THEMES[key]
        for w in self.preview.winfo_children():
            w.destroy()
        pv = self.preview

        bar = tk.Frame(pv, bg=th["title"], height=30)
        bar.pack(fill=tk.X)
        tk.Label(bar, text="ZipForge", bg=th["title"], fg=th["title_fg"],
                 font=(th["font"], 11, "bold")).pack(side=tk.LEFT, padx=8, pady=4)

        listbox = tk.Frame(pv, bg=th["panel"])
        listbox.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        sample = [("设计稿/", False), ("报价表V2.xlsx", False),
                  ("report.7z", True), ("预览图.png", False)]
        for name, is_sel in sample:
            bg = th["sel_bg"] if is_sel else th["panel"]
            fg = th["sel_fg"] if is_sel else th["fg"]
            row = tk.Frame(listbox, bg=bg)
            row.pack(fill=tk.X)
            tk.Label(row, text=name, bg=bg, fg=fg,
                     font=(th["font"], 10)).pack(side=tk.LEFT, padx=6, pady=3)

        sw = tk.Frame(pv, bg=th["bg"])
        sw.pack(fill=tk.X, padx=8, pady=(0, 8))
        for ckey in ("bg", "panel", "accent", "title", "fg"):
            tk.Label(sw, text=ckey, bg=th["bg"], fg=th["muted"],
                     font=("Segoe UI", 8)).pack(side=tk.LEFT, padx=(0, 2))
            tk.Label(sw, bg=th[ckey], relief="groove", borderwidth=1,
                     width=4, height=1).pack(side=tk.LEFT, padx=(0, 6))

    def _on_ok(self, _e=None):
        sel = self.lb.curselection()
        if sel:
            self.result = themes.ORDER[sel[0]]
        self.destroy()

    def cancel(self):
        self.result = None
        self.destroy()


def _parse_pending(argv):
    """把命令行参数转成「启动后立即执行的动作」规格。

    支持 `--verb <动作> [--scope <file|dir|bg>] <路径…>`；
    不带 --verb 的裸路径按旧行为视为「压缩」。
    scope 决定压缩对话框的默认目标目录：bg=文件夹内部，其余=文件夹旁边。
    """
    verb = None
    scope = "file"
    paths = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--verb" and i + 1 < len(argv):
            verb = argv[i + 1].lower()
            i += 2
            continue
        if a == "--scope" and i + 1 < len(argv):
            scope = argv[i + 1].lower()
            i += 2
            continue
        if a.startswith("--"):
            i += 1
            continue
        paths.append(a)
        i += 1
    if not paths:
        return None
    if verb == "addmail":
        return {"action": "addmail", "paths": paths, "scope": scope}
    if verb == "extract_to":
        return {"action": "extract_to", "paths": paths, "scope": scope}
    if verb == "test":
        return {"action": "test", "paths": paths, "scope": scope}
    if verb == "new":
        return {"action": "new", "paths": paths, "scope": scope}
    return {"action": "add", "paths": paths, "scope": scope}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    set_app_user_model_id()
    pending = _parse_pending(argv)
    while True:
        root = tk.Tk()
        try:
            app = ZipForgeApp(root, pending=pending)
            root.mainloop()
        except Exception as e:
            import traceback
            traceback.print_exc()
            mb.showerror("启动失败", str(e))
            break
        # 主题切换会销毁旧窗口并把 _restart 置位 —— 重建一个干净的新窗口
        if not getattr(app, "_restart", False):
            break
        pending = None


if __name__ == "__main__":
    main()
