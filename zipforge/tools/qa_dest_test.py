# -*- coding: utf-8 -*-
"""
qa_dest_test.py — 「归档生成到哪里」的回归测试（纯逻辑，不需要图形环境）。

为什么需要它（真实 bug）：
  用户在资源管理器里**选中一个文件夹**右键 → 快速压缩，结果归档被塞进了
  **该文件夹内部**（`…\\dist\\dist.zip`）；而 7-Zip 的行为是生成在文件夹
  **旁边**（`…\\dist.zip`）。

  根因：旧 `common_dir()` 把「文件夹」本身当成了目标目录。

  三种右键场景（由命令行 `--scope` 传入）的正确语义：
    • 选中文件           → 归档放在该文件**所在目录**
    • 选中文件夹 (dir)   → 归档放在该文件夹的**父目录**（即旁边）
    • 文件夹空白处 (bg)  → 归档放在该文件夹**内部**（%V 指向该文件夹）

退出码 0 = 全部通过。
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
os.environ.setdefault("ZF_NO_CTX", "1")

import cli_verbs as cv  # noqa: E402

FAILED = []


def check(name, cond, extra=""):
    print(("  [PASS] " if cond else "  [FAIL] ") + name
          + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAILED.append(name)


def _same(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def main():
    root = tempfile.mkdtemp(prefix="zf_dest_qa_")
    try:
        # 目录布局：
        #   root/                <- 父目录
        #     dist/              <- 被选中的文件夹
        #     a.txt, b.txt       <- 被选中的文件
        #     proj/              <- 多选文件夹
        #     proj2/
        dist = os.path.join(root, "dist")
        os.makedirs(dist)
        proj = os.path.join(root, "proj"); os.makedirs(proj)
        proj2 = os.path.join(root, "proj2"); os.makedirs(proj2)
        fa = os.path.join(root, "a.txt")
        fb = os.path.join(root, "b.txt")
        for f in (fa, fb):
            with open(f, "w", encoding="utf-8") as fh:
                fh.write("x")

        print("== 1. 命令行解析（--scope） ==")
        sp = cv.parse(["--verb", "quickzip", "--scope", "bg", r"C:\x"])
        check("verb 解析正确", sp["verb"] == "quickzip", sp["verb"])
        check("scope 解析正确 (bg)", sp["scope"] == "bg", sp["scope"])
        check("路径解析正确", sp["paths"] == [r"C:\x"], sp["paths"])
        sp2 = cv.parse(["--verb", "quick7z", r"C:\x"])
        check("未给 --scope 时缺省为 file", sp2["scope"] == "file", sp2["scope"])

        print("== 2. 单个文件 → 归档在旁边 ==")
        d = cv.quick_dest([fa], "7z", "file")
        check("归档在同目录", _same(os.path.dirname(d), root), d)
        check("归档名为 a.7z", os.path.basename(d) == "a.7z", os.path.basename(d))

        print("== 3. 选中文件夹 (dir) → 归档在旁边（父目录），不是里面！ ==")
        d = cv.quick_dest([dist], "zip", "dir")
        check("归档在文件夹的父目录（旁边）", _same(os.path.dirname(d), root), d)
        check("归档名为 dist.zip", os.path.basename(d) == "dist.zip", os.path.basename(d))
        check("★ 未被放进被选中的文件夹内部",
              not _same(os.path.dirname(d), dist), d)

        print("== 4. 文件夹空白处 (bg) → 归档在文件夹内部 ==")
        d = cv.quick_dest([dist], "zip", "bg")
        check("归档在该文件夹内部", _same(os.path.dirname(d), dist), d)
        check("归档名为 dist.zip", os.path.basename(d) == "dist.zip", os.path.basename(d))

        print("== 5. 多选文件 → 归档在公共目录，名为目录名 ==")
        d = cv.quick_dest([fa, fb], "7z", "file")
        check("归档在公共目录", _same(os.path.dirname(d), root), d)
        check("归档名为目录名", os.path.basename(d) == os.path.basename(root) + ".7z",
              os.path.basename(d))

        print("== 6. 多选文件夹 → 归档在它们的公共父目录 ==")
        d = cv.quick_dest([proj, proj2], "zip", "dir")
        check("归档在公共父目录", _same(os.path.dirname(d), root), d)

        print("== 7. 重名避让（不再覆盖） ==")
        with open(os.path.join(root, "dist.zip"), "w", encoding="utf-8") as fh:
            fh.write("occupied")
        d = cv.quick_dest([dist], "zip", "dir")
        check("重名时追加 (2)", os.path.basename(d) == "dist (2).zip", os.path.basename(d))
        check("避让后仍在旁边", _same(os.path.dirname(d), root), d)

        print("== 8. 回归：旧 bug 的具体形态必须消失 ==")
        # 旧实现会把 dist 文件夹自身当目标目录 → dist\dist.zip
        d = cv.quick_dest([dist], "zip", "dir")
        bug_path = os.path.join(dist, "dist.zip")
        check("不再产生 <文件夹>\\<文件夹>.zip", not _same(d, bug_path), d)

        print()
        if FAILED:
            print(f"结果：{len(FAILED)} 项未通过 -> {FAILED}")
            return 1
        print("结果：全部通过")
        return 0
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
