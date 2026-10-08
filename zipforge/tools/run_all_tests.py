# -*- coding: utf-8 -*-
"""一键跑完全部测试（回归套件）。

用法：python tools/run_all_tests.py
      （或双击 tools/跑全部测试.bat）

分层：
  1) qa_engine_test.py      引擎解析层（纯字符串，秒级）
  2) qa_integration_test.py GUI 逻辑层（tk 桩，无显示器）
  3) qa_gui_test.py         归档打开/导航链路（tk 桩 + 真 7z 引擎）
  4) qa_rar_test.py         rar 目录聚合与单文件提取（真 7z 引擎 + 真 rar）
  5) qa_icon_test.py        系统图标真实像素 + 真实窗口渲染（真 Tk，需 tkinter）
  6) qa_registry_test.py    右键菜单注册表读写与清理（真注册表，测完还原）
  7) qa_themes_test.py      11 套外观主题完整性 + 前景/背景对比度（纯逻辑）
  8) qa_iconfile_test.py    程序图标 ICO 结构/尺寸 + 关于窗口 PNG（纯标准库）
  9) qa_dest_test.py        归档「生成到哪里」的放置语义（纯逻辑，含 dir/bg 区分）
 10) zipforge.py ZF_TEST=1  exe/源码内置端到端自检（真引擎；其中 5-7 步需 tkinter）

任何一项失败都会以非 0 退出码结束，并汇总失败清单。
依赖 tkinter 的用例在“找不到任何带 tkinter 的解释器”时会被标记为 [SKIP]
（而非 [FAIL]），避免在无显示环境里给出误导性结果。
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# 依赖真实 Tk 的用例（缺 tkinter 时无法运行）
TK_DEPENDENT = {"系统图标 / 真机渲染", "内置自检"}

SUITE = [
    ("引擎解析层", ["qa_engine_test.py"]),
    ("GUI 逻辑层", ["qa_integration_test.py"]),
    ("归档链路（zip）", ["qa_gui_test.py"]),
    ("归档链路（rar）", ["qa_rar_test.py"]),
    ("系统图标 / 真机渲染", ["qa_icon_test.py"]),
    ("右键菜单注册表", ["qa_registry_test.py"]),
    ("外观主题", ["qa_themes_test.py"]),
    ("程序图标资产", ["qa_iconfile_test.py"]),
    ("归档放置语义", ["qa_dest_test.py"]),
]


def _has_tkinter(py):
    try:
        r = subprocess.run([py, "-c", "import tkinter"],
                           capture_output=True, text=True, timeout=20)
        return r.returncode == 0
    except Exception:
        return False


def _find_tkinter_python():
    """返回第一个能 import tkinter 的 interpreter；找不到则返回 None。"""
    cands = [sys.executable]
    localapp = os.environ.get("LOCALAPPDATA")
    if localapp:
        cands.append(os.path.join(localapp, "Programs", "Python", "Python313", "python.exe"))
    cands += [
        r"C:\Users\82453\AppData\Local\Programs\Python\Python313\python.exe",
        r"C:\Python313\python.exe",
    ]
    seen = set()
    for c in cands:
        if not c or c in seen:
            continue
        seen.add(c)
        if os.path.exists(c) and _has_tkinter(c):
            return c
    return None


def _resolve_python():
    """决定用于运行测试的 interpreter。

    - 若当前解释器自带 tkinter，直接用；
    - 否则若系统里另有带 tkinter 的解释器，优先改用它（非 Tk 用例也能跑）；
    - 否则保留当前解释器（Tk 用例将 SKIP）。
    """
    if _has_tkinter(sys.executable):
        return sys.executable, None
    tk_py = _find_tkinter_python()
    if tk_py:
        return tk_py, sys.executable
    return sys.executable, "no-tk"


PY, TK_FALLBACK = _resolve_python()
HAS_TK = _has_tkinter(PY)


def run(title, script):
    print("=" * 68)
    print(f"▶ {title}   ({script})")
    print("=" * 68)
    if title in TK_DEPENDENT and not HAS_TK:
        print("[SKIP] 该用例依赖 tkinter，当前环境无可用的 tkinter 解释器，跳过。")
        print(f"→ [SKIP] {title}\n")
        return "SKIP"
    p = subprocess.run([PY, os.path.join(HERE, script)],
                       cwd=ROOT, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    out = (p.stdout or "") + (p.stderr or "")
    print(out.rstrip())
    ok = p.returncode == 0
    print(f"→ {'[PASS]' if ok else '[FAIL]'} {title} (exit={p.returncode})\n")
    return "PASS" if ok else "FAIL"


def run_selftest():
    print("=" * 68)
    print("▶ 内置端到端自检   (zipforge.py, ZF_TEST=1)")
    print("=" * 68)
    if not HAS_TK:
        print("[SKIP] 自检中的 5-7 步依赖 tkinter，当前环境无可用的 tkinter 解释器，跳过。")
        print("→ [SKIP] 内置自检\n")
        return "SKIP"
    env = dict(os.environ, ZF_TEST="1")
    p = subprocess.run([PY, "zipforge.py"], cwd=ROOT, env=env,
                       capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    out = (p.stdout or "") + (p.stderr or "")
    print(out.rstrip())
    ok = p.returncode == 0 and "PASS" in out
    print(f"→ {'[PASS]' if ok else '[FAIL]'} 内置自检 (exit={p.returncode})\n")
    return "PASS" if ok else "FAIL"


def main():
    if TK_FALLBACK:
        print(f"[环境] 当前解释器（{TK_FALLBACK}）无 tkinter，"
              f"已改用 {PY} 运行测试。\n")
    results = []
    for title, scripts in SUITE:
        for s in scripts:
            results.append((title, run(title, s)))
    results.append(("内置自检", run_selftest()))

    print("=" * 68)
    print("汇总")
    print("=" * 68)
    for name, st in results:
        print(f"  [{st}]  {name}")
    bad = [n for n, st in results if st == "FAIL"]
    skipped = [n for n, st in results if st == "SKIP"]
    if bad:
        print(f"\n未通过：{bad}")
        return 1
    if skipped:
        print(f"\n跳过（缺 tkinter，非失败）：{skipped}")
    else:
        print("\n全部通过 [PASS]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
