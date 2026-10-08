# -*- coding: utf-8 -*-
"""引擎解析层单元测试（不需要 7z 引擎，纯字符串解析）。

重点回归：_parse_list 的字段切片。
  此前 'Modified = ' 被手写成 s[12:]（正确是 11），年份首位 2 被吃掉，
  界面显示成 "026-04-29 …"，看截图才被发现。现统一走 _after_eq()。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import sevenzip_engine as e  # noqa: E402

FAILED = []


def check(name, cond, extra=""):
    print(("  [PASS] " if cond else "  [FAIL] ") + name + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAILED.append(name)


SAMPLE = "\n".join([
    "Path = D:\\x\\远特结题0.rar",
    "Type = Rar",
    "Physical Size = 226904736",
    "Modified = 2026-04-30 17:52:11",
    "",
    "Path = 远特结题",
    "Folder = +",
    "Attributes = D",
    "Modified = 2026-04-29 16:33:30.0780000",
    "",
    "Path = 远特结题\\HH海试.docx",
    "Size = 147456",
    "Packed Size = 1024",
    "Modified = 2026-04-28 18:22:58",
    "Attributes = A",
    "Encrypted = -",
    "Method = m3:Standard",
    "Block = 2",
    "CRC = AB12CD34",
    "",
])


def main():
    print("== 1. 归档块识别 ==")
    items, archive = e._parse_list(SAMPLE)   # 注意返回顺序：items 在前
    check("识别出归档自身属性", archive.get("type") == "Rar", archive)
    check("Physical Size 解析正确（无 off-by-one）",
          archive.get("physical") == 226904736, archive.get("physical"))
    check("归档 Modified 完整（4 位年份）",
          archive.get("modified") == "2026-04-30 17:52:11", archive.get("modified"))

    print("== 2. 条目字段 ==")
    check("条目数 = 2", len(items) == 2, len(items))
    d, f = items[0], items[1]
    check("目录路径原样（不带尾斜杠，由 UI 归一）",
          d.get("path") == "远特结题", d.get("path"))
    check("Folder 标记解析", d.get("folder") is True, d.get("folder"))
    check("目录 Attributes=D", d.get("attr") == "D", d.get("attr"))
    check("目录 Modified 去掉小数秒",
          d.get("modified") == "2026-04-29 16:33:30", d.get("modified"))

    check("文件路径反斜杠归一化为 /",
          f.get("path") == "远特结题/HH海试.docx", f.get("path"))
    check("年份首位未丢失（off-by-one 回归）",
          f.get("modified") == "2026-04-28 18:22:58", f.get("modified"))
    check("Size 解析", f.get("size") == 147456, f.get("size"))
    check("Packed Size 解析", f.get("packed") == 1024, f.get("packed"))
    check("Encrypted='-' → False", f.get("encrypted") is False, f.get("encrypted"))
    check("Method 解析", f.get("method") == "m3:Standard", f.get("method"))
    check("Block 解析", f.get("block") == "2", f.get("block"))
    check("CRC 解析", f.get("crc") == "AB12CD34", f.get("crc"))
    check("文件不带 folder 标记", "folder" not in f or f.get("folder") is not True)

    print("== 3. norm_modified 边界 ==")
    cases = [
        ("2026-04-29 16:33:30.0780000", "2026-04-29 16:33:30"),
        ("2026-04-29 16:33:30", "2026-04-29 16:33:30"),
        ("0000-00-00 00:00:00.0000000", ""),
        ("", ""),
        (None, ""),
        ("  2021-12-31 23:59:59.999999  ", "2021-12-31 23:59:59"),
    ]
    for raw, want in cases:
        got = e.norm_modified(raw)
        check(f"norm_modified({raw!r})", got == want, repr(got))

    print("== 4. 空/畸形输入不崩 ==")
    try:
        i2, a2 = e._parse_list("")
        check("空输入返回空结构", a2 == {} and i2 == [], (a2, i2))
        i3, a3 = e._parse_list("garbage\nno equals sign\n")
        check("垃圾行被忽略且不崩", i3 == [], i3)
        i4, a4 = e._parse_list("Path = a.txt\nSize = abc\n")
        check("非法数字降级为 0", i4 and i4[0].get("size") == 0, i4)
    except Exception as ex:
        check("畸形输入不抛异常", False, f"{type(ex).__name__}: {ex}")

    print()
    if FAILED:
        print(f"结果：{len(FAILED)} 项未通过 -> {FAILED}")
        return 1
    print("结果：全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
