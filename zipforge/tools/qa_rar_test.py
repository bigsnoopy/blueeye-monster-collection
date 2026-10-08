# -*- coding: utf-8 -*-
"""回归测试：归档内含「显式目录条目」时的浏览与打开。

背景（用户实测报障）：
  打开一个 rar，列表里同时出现 "远特结题/" 和 "远特结题" 两行；
  双击后者弹「打开失败：提取后未找到文件。」
根因：
  7z 输出的目录条目 path 不带尾斜杠（Folder=+），而由文件路径又能推断出同一目录，
  原实现未去重、也没给目录条目补 "/"，导致该行被当成文件去提取。
本测试覆盖：
  1) 目录条目与推断目录合并去重、目录名一律带尾斜杠
  2) 双击目录行 -> 进入子目录（而不是当文件提取）
  3) 双击文件行 -> 提取到临时目录并按归档内相对路径精确定位
  4) 真实大归档（存在时）同样通过
用法：python tools/qa_rar_test.py [可选:真实归档路径]
"""
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import qa_gui_test as stub  # 复用无显示器 tk 桩

REAL_RAR = (sys.argv[1] if len(sys.argv) > 1
            else r"D:\00_日常事务\20260506 研究总结报告\远特结题0.rar")


def build_fixture(engine) -> str:
    """造一个含子目录的 7z（7z 会写入不带尾斜杠的显式目录条目，正好复现问题）。"""
    d = os.path.join(engine._zf_tmp(), "qa_fixture")
    tree = os.path.join(d, "远特结题", "电子模块硬件图纸")
    os.makedirs(tree, exist_ok=True)
    open(os.path.join(d, "远特结题", "指标要求.docx"), "w", encoding="utf-8").write("x" * 500)
    open(os.path.join(tree, "接线定义.docx"), "w", encoding="utf-8").write("y" * 300)
    out = os.path.join(d, "fixture.7z")
    if os.path.exists(out):
        os.remove(out)
    r = engine.compress([os.path.join(d, "远特结题")], out, fmt="7z", level=5)
    assert r["ok"], "构造测试归档失败: %s" % r.get("text", "")[-200:]
    return out


def check_archive(app, gui, engine, path, label):
    res = engine.list_archive(path)
    assert res["ok"], "无法读取 %s: %s" % (label, res["error"])
    app.mode = "archive"
    app.archive_path = path
    app.archive_items = res["items"]
    app.archive_all_items = res["items"]
    app.archive_prefix = ""
    app._render_archive()

    rows = [(app._row_name(i), f, app._archive_row_isdir[i])
            for i, f in app._archive_row_full.items()]
    print("[%s] 根目录 %d 行:" % (label, len(rows)))
    for disp, full, isd in rows:
        print("      %-22s is_dir=%s full=%s" % (disp, isd, full))

    # 1) 根目录第一层不应出现同名重复目录（一个带 /、一个不带）
    dirs = [d for d, _, isd in rows if isd]
    stripped = [d.rstrip("/") for d in dirs]
    assert len(stripped) == len(set(stripped)), "存在重复目录行: %s" % dirs
    # 2) 目录显示名必须带尾斜杠
    for d, _, isd in rows:
        if isd:
            assert d.endswith("/"), "目录显示名未带尾斜杠: %r" % d
    # 3) 顶层目录数应为 1（远特结题）
    assert len(dirs) == 1, "顶层目录数异常: %s" % dirs

    # 双击该目录 -> 应进入，而不是弹「提取后未找到文件」
    dir_iid = [i for i, f in app._archive_row_full.items()
               if app._archive_row_isdir[i]][0]
    app.listv.set_selection([dir_iid])
    app.on_list_double(None)
    assert app.archive_prefix == "远特结题/", "双击目录未进入: %r" % app.archive_prefix
    sub = [(app._row_name(i), app._archive_row_isdir[i])
           for i in app._archive_row_full]
    print("[%s] 进入 远特结题/ 后 %d 行" % (label, len(sub)))
    for d, isd in sub[:6]:
        print("      %-28s is_dir=%s" % (d, isd))
    assert any(isd for _, isd in sub), "子目录里没有聚合出下一级文件夹"

    # 双击一个真实文件 -> 提取并精确定位
    file_iid = [i for i in app._archive_row_full if not app._archive_row_isdir[i]]
    if file_iid:
        rel = app._archive_row_full[file_iid[0]]
        dest = engine.new_temp_dir("zf_qa_open_")
        ex = engine.extract_archive(path, dest, items=[rel])
        assert ex["ok"], "提取单个文件失败: %s" % ex.get("error")
        cand = os.path.join(dest, *[p for p in rel.replace("\\", "/").split("/") if p])
        assert os.path.isfile(cand), "提取后未按相对路径找到文件: %s" % cand
        print("[%s] 双击文件「%s」提取定位 OK" % (label, os.path.basename(rel)))

    # 多级下钻 -> 逐级返回根目录
    app.archive_prefix = ""
    app._render_archive()
    depth = 0
    while True:
        sub_dirs = [i for i in app._archive_row_full if app._archive_row_isdir[i]]
        if not sub_dirs:
            break
        app.listv.set_selection([sub_dirs[0]])
        app.on_list_double(None)
        depth += 1
        assert app.archive_prefix.count("/") == depth, "下钻层级异常"
        if depth > 8:
            break
    print("[%s] 下钻 %d 级到：%r（该层 %d 行）"
          % (label, depth, app.archive_prefix, len(app._archive_row_full)))
    for _ in range(depth):
        app.go_up()
    assert app.archive_prefix == "", "逐级返回未回到根：%r" % app.archive_prefix
    print("[%s] 逐级返回根目录 OK" % label)
    app.archive_prefix = ""
    return len(rows)


def main():
    tk, ttk = stub.make_stub()
    sys.path.insert(0, os.path.join(HERE, "..", "src"))
    import gui
    import sevenzip_engine as engine

    print("引擎:", engine.engine_version())
    fixture = build_fixture(engine)
    check_archive(gui.ZipForgeApp(tk.Tk()), gui, engine, fixture, "7z夹具")

    if os.path.exists(REAL_RAR):
        check_archive(gui.ZipForgeApp(tk.Tk()), gui, engine, REAL_RAR, "真实rar")
    else:
        print("[真实rar] 未找到，跳过：%s" % REAL_RAR)

    print("\n归档目录导航回归: 全部通过 [PASS]")


if __name__ == "__main__":
    main()
