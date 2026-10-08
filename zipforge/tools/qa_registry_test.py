# -*- coding: utf-8 -*-
"""
qa_registry_test.py — 右键菜单（**级联子菜单**）注册表回归测试（仅 Windows）。

为什么需要它：
  右键菜单是「注册表驱动」的功能，靠读代码看不出对错 —— 必须真的写进去、
  再读回来比对结构，最后清理干净。本脚本就是干这个的。

覆盖：
  1. 历史残留清理。
  2. 级联结构：父键默认值/Icon/Position/MultiSelectModel + `shell` 子键下
     每个子项都有 label 与 command 子键，且命令行带 `--verb`。
     ★ 重点反例：command 必须是**子键**，不能是名为 command 的字符串值
       （后者会让菜单出现但点了没反应 —— 这是真实踩过的坑）。
  3. AppliesTo 只挂在「解压」类菜单项上（这样普通 .docx 右键不会出现解压项）。
  4. 真实 register() → is_registered() → 逐项读回 → unregister() → 无残留。
     使用假的 exe 路径，测完立即卸载，不干扰用户环境。

退出码 0 = 全部通过。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
os.environ.setdefault("ZF_NO_CTX", "1")   # 本测试自己控制注册表，禁止 gui 自动安装

import shell_integration as si  # noqa: E402

FAILED = []


def check(name, cond, extra=""):
    print(("  [PASS] " if cond else "  [FAIL] ") + name
          + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAILED.append(name)


def _value_names(wr, base):
    names = []
    try:
        k = wr.OpenKey(wr.HKEY_CURRENT_USER, base)
    except OSError:
        return names
    try:
        i = 0
        while True:
            try:
                names.append(wr.EnumValue(k, i)[0])
                i += 1
            except OSError:
                break
    finally:
        wr.CloseKey(k)
    return names


def main():
    if sys.platform != "win32":
        print("非 Windows，跳过。")
        return 0
    import winreg as wr

    print("== 1. 清理历史残留 ==")
    for base in si._KEYS:
        existed = si._delete_tree(wr, base)
        print(f"  cleaned={existed}  {base}")

    print("== 2. 级联子菜单结构（写入 / 读回） ==")
    scratch = r"Software\Classes\_ZipForgeQATest_DeleteMe\shell\ZipForge"
    root_scratch = r"Software\Classes\_ZipForgeQATest_DeleteMe"
    try:
        si._write_cascade(wr, scratch, "ZipForge", '"C:\\Fake\\ZipForge.exe"',
                          "C:\\Fake\\ZipForge.exe,0", "file")
        k = wr.OpenKey(wr.HKEY_CURRENT_USER, scratch)
        label, _ = wr.QueryValueEx(k, "MUIVerb")
        icon, _ = wr.QueryValueEx(k, "Icon")
        pos, _ = wr.QueryValueEx(k, "Position")
        msm, _ = wr.QueryValueEx(k, "MultiSelectModel")
        subc, _ = wr.QueryValueEx(k, "SubCommands")   # ★ 级联声明（关键修复）
        default, _ = wr.QueryValueEx(k, "")
        wr.CloseKey(k)
        check("MUIVerb = 菜单文字", label == "ZipForge", repr(label))
        check("父键默认值已清空（避免被当成普通 verb）", default == "", repr(default))
        check("Icon 值正确", icon.endswith("ZipForge.exe,0"), repr(icon))
        check("Position=Top（菜单靠前显示）", pos == "Top", repr(pos))
        check("MultiSelectModel=Player（多选只启动一次）", msm == "Player", repr(msm))
        check("SubCommands 存在且为空串（声明级联容器）", subc == "", repr(subc))

        names = _value_names(wr, scratch)
        check("command 未污染成值名（必须是子键）", "command" not in names, names)

        rows = si.read_cascade(wr, scratch)
        expect = si.menu_items("file")
        check("子菜单项数量与定义一致",
              len(rows) == len(expect), f"实得 {len(rows)} 期望 {len(expect)}")
        check("子项名称/顺序与定义一致",
              [r[0] for r in rows] == [e[0] for e in expect],
              [r[0] for r in rows])
        check("每项都有 label", all(l for _n, l, _c in rows))
        check("每项命令行都带 --verb",
              all("--verb" in c for _n, _l, c in rows),
              [n for n, _l, c in rows if "--verb" not in c])
        check("每项命令行都带 --scope（区分文件夹/空白处放置）",
              all("--scope" in c for _n, _l, c in rows),
              [n for n, _l, c in rows if "--scope" not in c])
        check("命令指向传入的 exe",
              all("Fake\\\\ZipForge.exe" in c or "Fake\\ZipForge.exe" in c
                  for _n, _l, c in rows))

        # AppliesTo：只应出现在「解压」类项上
        arc_keys = {e[0] for e in expect if e[3]}
        mis_filtered = []
        mis_unfiltered = []
        for n, _l, _c in rows:
            v = si._read_value(wr, scratch + "\\shell\\" + n, "AppliesTo")
            if n in arc_keys:
                if not (v and "System.FileName" in v):
                    mis_filtered.append(n)
            else:
                if v is not None:
                    mis_unfiltered.append(n)
        check("解压类项都带 AppliesTo 过滤", not mis_filtered, mis_filtered)
        check("非解压类项不带 AppliesTo（始终可见）", not mis_unfiltered, mis_unfiltered)
        # AppliesTo 串确实覆盖常见归档扩展名
        applies = si.archive_applies_to()
        check("AppliesTo 覆盖 7z/zip/rar",
              all(f'"*{e}"' in applies for e in (".7z", ".zip", ".rar")),
              applies[:80] + " …")
    finally:
        si._delete_tree(wr, scratch)
        si._delete_tree(wr, root_scratch)
    try:
        wr.OpenKey(wr.HKEY_CURRENT_USER, scratch)
        leftover = True
    except OSError:
        leftover = False
    check("_delete_tree 递归删除干净", not leftover)

    print("== 3. 真实 register / unregister 全流程 ==")
    fake = r"C:\FakePath\ZipForge.exe"
    ok, msg = si.register(exe=fake)
    check("register() 返回成功", ok, msg.splitlines()[0] if msg else "")
    check("自检信息里包含 exe 路径", fake in msg)
    check("is_registered() 为真", si.is_registered())

    total = 0
    for scope, base in si._ROOT_KEYS.items():
        rows = si.read_cascade(wr, base)
        total += len(rows)
        check(f"{scope} 场景子菜单项数正确",
              len(rows) == len(si.menu_items(scope)),
              f"{len(rows)} vs {len(si.menu_items(scope))}")
        bad = [n for n, _l, c in rows if not c or fake not in c]
        check(f"{scope} 各项命令行均指向目标 exe", not bad, bad)
        bad_scope = [n for n, _l, c in rows if f"--scope {scope}" not in c]
        check(f"{scope} 各项命令行带正确 --scope", not bad_scope, bad_scope)
    check("三场景合计菜单项 > 10（确实是富菜单）", total > 10, total)

    ok2, msg2 = si.unregister()
    check("unregister() 返回成功", ok2, msg2)
    check("is_registered() 为假", not si.is_registered())
    for base in si._KEYS:
        check(f"无残留 {base}", si._read_verb_command(wr, base) is None)
        try:
            wr.OpenKey(wr.HKEY_CURRENT_USER, base)
            still = True
        except OSError:
            still = False
        check(f"根键已删除 {base}", not still)

    print()
    if FAILED:
        print(f"结果：{len(FAILED)} 项未通过 -> {FAILED}")
        return 1
    print("结果：全部通过（注册表无残留，用户环境已复原）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
