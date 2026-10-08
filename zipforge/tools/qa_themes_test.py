# -*- coding: utf-8 -*-
"""主题系统自检：11 套主题键齐全、字段齐全、关键对比度可读。

不依赖 GUI 渲染，纯逻辑校验。返回非 0 表示存在问题。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import themes  # noqa: E402


def main():
    problems, report = themes.self_check()
    print("[主题自检]")
    for line in report:
        print("  " + line)
    # 额外断言：数量为 11、ORDER 与键一致
    assert len(themes.THEMES) == 11, "主题数量应为 11"
    assert set(themes.ORDER) == set(themes.THEMES.keys()), "ORDER 与键不一致"
    for key in themes.ORDER:
        assert themes.get_theme(key) is themes.THEMES[key]
    if problems:
        print("\n发现问题：")
        for p in problems:
            print("  - " + p)
        return 1
    print("\n✅ 11 套主题全部通过（字段齐全 + 关键对比度可读）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
