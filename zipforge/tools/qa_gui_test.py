# -*- coding: utf-8 -*-
"""无显示器下的 GUI 链路冒烟测试：
用最小 tk 桩驱动 ZipForgeApp，验证「打开 zip -> 列表 -> 进子目录 -> 返回上级」
这条此前坏掉的核心交互真实可用。
"""
import sys, os, types


class FakeVar:
    def __init__(self, v=None):
        self._v = v
    def get(self): return self._v
    def set(self, v): self._v = v


class FakeTreeview:
    """记录插入行的假 Treeview，支持 item / selection / insert / delete。

    注意：名称存在 #0 列的 text 里（因为图标只能画在 #0），
    不再放在 values[0] —— 桩必须如实模拟这一点，否则测不出真问题。
    """
    def __init__(self, *a, **k):
        self._rows = {}     # iid -> {"text","values","image","tags"}
        self._seq = 0
        self._sel = []
        self.headings = []
        self.options = k
    def heading(self, *a, **k): pass
    def column(self, *a, **k): pass
    def pack(self, *a, **k): pass
    def bind(self, *a, **k): pass
    def configure(self, *a, **k): pass
    def yview(self, *a, **k): pass
    def delete(self, *iids):
        for i in iids:
            self._rows.pop(i, None)
    def get_children(self, *a):
        return list(self._rows.keys())
    def insert(self, parent, index, **k):
        iid = f"i{self._seq}"; self._seq += 1
        self._rows[iid] = {
            "text": k.get("text", ""),
            "values": k.get("values", ()),
            "image": k.get("image"),
            "tags": k.get("tags", ()),
        }
        return iid
    def item(self, iid, key=None):
        row = self._rows.get(iid, {"text": "", "values": (), "image": None,
                                   "tags": ()})
        if key is None:
            return dict(row)
        if key == "values":
            return row["values"]
        return row.get(key, "")
    def selection(self):
        return self._sel
    def set_selection(self, iids):
        self._sel = iids


def make_stub():
    tk = types.ModuleType("tk")
    ttk = types.ModuleType("ttk")
    for name in ["Tk","Toplevel","Menu","Frame","Button","Entry","Label",
                 "Separator","Progressbar","PanedWindow","StringVar","IntVar",
                 "BooleanVar","Variable"]:
        setattr(tk, name, type(name, (), {
            "__init__": lambda self,*a,**k: None,
            "title": lambda self,*a,**k: None,
            "geometry": lambda self,*a,**k: None,
            "protocol": lambda self,*a,**k: None,
            "config": lambda self,*a,**k: None,
            "destroy": lambda self,*a,**k: None,
            "after": lambda self,*a,**k: None,
            "mainloop": lambda self,*a,**k: None,
            "pack": lambda self,*a,**k: None,
            "add_command": lambda self,*a,**k: None,
            "add_cascade": lambda self,*a,**k: None,
            "add_separator": lambda self,*a,**k: None,
            "get": lambda self: None, "set": lambda self,*a,**k: None,
            "bind": lambda self,*a,**k: None,
            "command": lambda self,*a,**k: None,
            "length": 200, "mode": "determinate", "maximum": 100, "value": 0,
        }))
    # Variable 类要支持 get/set 存值
    class _Var:
        def __init__(self, v=None, *a, **k): self._v = v
        def get(self): return self._v
        def set(self, v): self._v = v
    tk.StringVar = _Var; tk.IntVar = _Var; tk.BooleanVar = _Var; tk.Variable = _Var

    class _Style:
        def theme_use(self,*a,**k): pass
        def configure(self,*a,**k): pass
    ttk.Style = _Style
    # 通用带参桩类（Frame/Button/Entry/Label/Separator/Progressbar/PanedWindow）
    class _W:
        def __init__(self, *a, **k): self._items = {}
        def pack(self, *a, **k): pass
        def bind(self, *a, **k): pass
        def configure(self, *a, **k): pass
        def command(self, *a, **k): pass
        def add(self, *a, **k): pass
        def yview(self, *a, **k): pass
        def set(self, *a, **k): pass
        # 让 ttk.Progressbar["value"] = x 这类写法也能跑通（真实 tk 支持 item 赋值）
        def __setitem__(self, k, v): self._items[k] = v
        def __getitem__(self, k): return self._items.get(k, 0)
    ttk.Frame = _W; ttk.Button = _W; ttk.Entry = _W; ttk.Label = _W
    ttk.Separator = _W; ttk.Progressbar = _W; ttk.PanedWindow = _W
    ttk.Scrollbar = _W
    # 用我们自己的 FakeTreeview 替换 Treeview
    ttk.Treeview = FakeTreeview
    sys.modules["tk"] = tk
    sys.modules["tkinter"] = tk
    sys.modules["tkinter.ttk"] = ttk
    tk.ttk = ttk
    tk.__path__ = []  # 让它看起来像包，支持 import tkinter.ttk
    fd = types.ModuleType("filedialog"); mb = types.ModuleType("messagebox")
    sd = types.ModuleType("simpledialog")
    sys.modules["tkinter.filedialog"] = fd; sys.modules["tkinter.messagebox"] = mb
    sys.modules["tkinter.simpledialog"] = sd
    tk.filedialog = fd; tk.messagebox = mb; tk.simpledialog = sd
    # 常用布局常量
    for c in ["TOP","BOTTOM","LEFT","RIGHT","X","Y","BOTH","W","E","N","S",
              "END","DISABLED","NORMAL","VERTICAL","HORIZONTAL","CENTER",
              "RAISED","GROOVE","TclError"]:
        if c == "TclError":
            class TclError(Exception): pass
            tk.TclError = TclError
        else:
            setattr(tk, c, c.lower())
    return tk, ttk


def main():
    tk, ttk = make_stub()
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
    import gui
    import sevenzip_engine as e

    # 造一个含子目录的真实 zip
    import tempfile, zipfile
    tmp = tempfile.mkdtemp(prefix="zf_qa_")
    zp = os.path.join(tmp, "demo.zip")
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("说明.txt", "top file")
        z.writestr("资料/方案.docx", "doc")
        z.writestr("资料/明细.xlsx", "xls")
        z.writestr("图片/风景.png", "png")

    # 构造 App（桩 root）
    app = gui.ZipForgeApp(tk.Tk())

    # 1) 打开归档：直接喂入引擎解析结果，走 done() 里的 _render_archive
    res = e.list_archive(zp)
    app.mode = "archive"
    app.archive_path = zp
    app.archive_items = res["items"]
    app.archive_all_items = res["items"]
    app.archive_prefix = ""
    app._render_archive()

    root_rows = list(app._archive_row_full.items())
    print("[打开zip] 根目录条目数:", len(root_rows))
    for iid, full in root_rows:
        print("    ", app.listv.item(iid, "text"), "->", full)

    # 找到“资料/”这一行，模拟双击进入
    dir_iid = None
    for iid, full in root_rows:
        if app.listv.item(iid, "text") == "资料/":
            dir_iid = iid
            break
    assert dir_iid is not None, "未渲染出 资料/ 目录"
    app.listv.set_selection([dir_iid])
    app.on_list_double(None)   # 双击 -> 进入子目录

    print("[进入 资料/] 当前前缀:", repr(app.archive_prefix))
    sub_rows = [(app.listv.item(i, "text"), f) for i, f in app._archive_row_full.items()]
    print("    子目录条目:", sub_rows)
    assert app.archive_prefix == "资料/", "双击目录未进入子目录"

    # 返回上级
    app.go_up()
    print("[返回上级] 当前前缀:", repr(app.archive_prefix))
    assert app.archive_prefix == "", "返回上级未回到根"

    # 损坏文件走错误分支：模拟 done 里 error 判断
    bad = os.path.join(tmp, "bad.zip")
    open(bad, "wb").write(b"not a zip")
    rbad = e.list_archive(bad)
    print("[损坏文件] ok=", rbad["ok"], "error=", rbad["error"])
    assert not rbad["ok"] and rbad["error"], "损坏文件未触发错误"

    print("\nGUI 链路冒烟: 全部通过 [PASS]")


if __name__ == "__main__":
    main()
