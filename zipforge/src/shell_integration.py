# -*- coding: utf-8 -*-
"""
shell_integration.py — 在 Windows 资源管理器右键菜单注册 ZipForge 入口。

设计目标：像 7-Zip 那样，把常用操作**直接摊开成一级子菜单**，选中即执行，
不必先进主界面再点按钮。

菜单结构（三类场景共用同一套级联子菜单）：

    ZipForge  ▸ ┌ 解压到当前文件夹          （仅归档可见）
               │ 解压到同名文件夹          （仅归档可见）
               │ 解压到…                  （仅归档可见）
               │ 添加到压缩包…
               │ 压缩并发送邮件…
               │ 快速压缩为 7z
               │ 快速压缩为 ZIP
               │ CRC-32
               │ SHA-256
               └ 全部校验值…

覆盖三类右键场景：
  1. *                      —— 选中一个或多个「文件」右键
  2. Directory              —— 右键一个「文件夹」
  3. Directory\\Background  —— 在文件夹「空白处」右键（拿到的是该文件夹路径）

────────────────────────────────────────────────────────────────────────────
【关于「动态文件名」的说明 —— 为什么标签里没有文件名】
  7-Zip 的菜单能显示「添加到 "vendor.7z"」这种**带真实文件名**的标签，
  那是因为它注册了一个 COM 外壳扩展 DLL（7-zip.dll）实现 IContextMenu，
  由 DLL 在弹出菜单时动态生成文字。

  纯「注册表 + exe」的方案做不到动态标签（这是 Windows 静态 verb 的硬限制）。
  因此本模块用**固定文案**，但**动作在运行时按实际选中的文件自动推导** ——
  例如「快速压缩为 7z」会把 `vendor.txt` 压成 `vendor.7z`，
  行为与 7-Zip 的「添加到 vendor.7z」一致，只是标签不含文件名。
  若确实需要标签带文件名，需要额外写一个外壳扩展 DLL（当前未采用）。
────────────────────────────────────────────────────────────────────────────

【注册表写法要点（踩过的坑）】
  1) 单个静态 verb 的标准结构：
        ...\\shell\\ZipForge\\            (默认值 = 菜单显示文字)
        ...\\shell\\ZipForge\\Icon        (字符串值 = "C:\\...\\ZipForge.exe,0")
        ...\\shell\\ZipForge\\command\\   (默认值 = 完整命令行)
     ✗ `command` 必须是**子键**，不是同名值；写成值 → 菜单出现但点了没反应。
     ✗ winreg.SetValue 没有 3 参数形式，签名是
       SetValue(key, sub_key, type, value) —— 少一个直接抛 TypeError。
     ✓ 写「默认值」用 SetValueEx(k, "", 0, REG_SZ, v)；写子键用 CreateKey(k, name)。

  2) **级联子菜单（踩坑记录，重要）**：
     父键下再放一个名为 `shell` 的子键，其下每个子键就是一个子菜单项
     （同样的 label / command 结构）。要让 Windows 把父键**识别成级联箭头**
     而不是一个「点了要执行 command 的普通 verb」，父键上**必须**满足：
        a) 父键默认值留空（"value not set"）；
        b) 用 `MUIVerb` 字符串值承载菜单显示名（微软推荐写法）；
        c) **必须有 `SubCommands` 字符串值（空串 ""）** —— 这是向 Explorer
           声明「我是级联容器、子项都在我的 `shell` 子键下」的关键标志。
     缺了 `SubCommands` 会发生什么（本项目的真实 bug）：
        Explorer 不把它当级联 → 菜单项**没有展开箭头**；
        父键又**没有** command 子键 → 点击时 Explorer 找不到可执行项 →
        弹「该文件没有与之关联的应用来执行该操作」(SE_ERR_NOASSOC)，
        错误框标题就是你右键的那个文件夹/文件路径。
     教训：**父键不要放 command**，但**必须放 SubCommands**（哪怕是空串）。

  3) `AppliesTo` 可把某个 verb 限制为「只对匹配的文件显示」：
        AppliesTo = System.FileName:="*.7z" OR System.FileName:="*.zip"
     用它把「解压…」类菜单项限制到归档文件上 —— 普通 .docx 右键时不会
     出现一堆无意义的「解压」项。

  4) `Position = Top` 让菜单项尽量靠前显示（与 7-Zip 一致，便于发现）。

  5) 写在 HKCU\\Software\\Classes 而不是 HKCR：每用户注册、不需要管理员权限。
"""
import os
import sys

MENU_NAME = "ZipForge"

# 三类注册位置（均在 HKCU\\Software\\Classes 之下）
_ROOT_KEYS = {
    "file": r"Software\Classes\*\shell\ZipForge",
    "dir": r"Software\Classes\Directory\shell\ZipForge",
    "bg": r"Software\Classes\Directory\Background\shell\ZipForge",
}

# 兼容旧引用（自检/测试里遍历用）
_KEYS = [_ROOT_KEYS["file"], _ROOT_KEYS["dir"], _ROOT_KEYS["bg"]]

# 需要主界面配合的 verb（弹对话框）；其余为「无界面直接执行」
GUI_VERBS = {"add", "addmail", "extract_to", "new", "test"}
HEADLESS_VERBS = {"quick7z", "quickzip", "crc32", "crc64", "sha1", "sha256",
                  "sha512", "hash_all", "extract_here", "extract_same"}


def _reg():
    """拿 winreg；非 Windows 或缺模块时返回 None。"""
    if sys.platform != "win32":
        return None
    try:
        import winreg
        return winreg
    except Exception:
        return None


def exe_path():
    """当前可执行文件路径。打包后 sys.executable 即真实 exe 所在位置。"""
    try:
        return os.path.abspath(sys.executable)
    except Exception:
        return os.path.abspath(__file__)


def _archive_exts():
    """归档扩展名集合（用于 AppliesTo 过滤）。优先复用 formats 的定义。"""
    exts = set()
    try:
        import formats  # noqa: WPS433 (延迟导入，保持本模块可独立测试)
        for f in formats.CREATE_FORMATS:
            exts.add(formats.default_ext(f))
        for f in formats.READONLY_FORMATS:
            exts.add("." + f)
    except Exception:
        exts |= {".7z", ".zip", ".rar", ".tar", ".gz", ".bz2", ".xz",
                 ".zst", ".cab", ".iso", ".wim", ".arj", ".lzh"}
    # 常见复合扩展名
    exts |= {".tgz", ".tbz2", ".txz", ".tzst", ".tar.gz", ".tar.bz2",
             ".tar.xz", ".tar.zst", ".tar.zst"}
    exts.discard("")
    return sorted(exts)


def archive_applies_to():
    """生成 AppliesTo 查询串：只对归档类文件显示（用于「解压…」项）。"""
    return " OR ".join(f'System.FileName:="*{e}"' for e in _archive_exts())


# ---------------------------------------------------------------------------
# 菜单项定义： (子键名, 显示文字, verb, 是否仅归档可见)
#
# ⚠ 子键名必须带**两位数字前缀**：资源管理器对静态级联子菜单是按 key 名
#   **字母序**排列的，不保留写入顺序。实测不前缀时顺序被打乱成
#   add / addmail / crc32 / extract_here / … ，「解压」项会跑到中间，
#   完全不是想要的「先解压、再压缩、最后校验」。
#   加 10_/20_/… 前缀后，字母序 == 期望顺序。
# ---------------------------------------------------------------------------
def menu_items(scope):
    """返回某场景(scope: file/dir/bg)下的级联子菜单项列表。"""
    if scope == "bg":
        # 空白处右键：只做「建归档 / 压缩当前文件夹」，与 7-Zip 一致
        return [
            ("10_new", "在此新建归档…", "new", False),
            ("20_quick7z", "把本文件夹压缩为 7z", "quick7z", False),
            ("30_quickzip", "把本文件夹压缩为 ZIP", "quickzip", False),
            ("40_add", "添加到压缩包…", "add", False),
        ]
    return [
        # —— 解压组（仅归档可见）——
        ("10_extract_here", "解压到当前文件夹", "extract_here", True),
        ("20_extract_same", "解压到同名文件夹", "extract_same", True),
        ("30_extract_to", "解压到…", "extract_to", True),
        # —— 压缩组 ——
        ("40_add", "添加到压缩包…", "add", False),
        ("50_addmail", "压缩并发送邮件…", "addmail", False),
        ("60_quick7z", "快速压缩为 7z", "quick7z", False),
        ("70_quickzip", "快速压缩为 ZIP", "quickzip", False),
        # —— 校验组 ——
        ("80_crc32", "CRC-32", "crc32", False),
        ("90_sha256", "SHA-256", "sha256", False),
        ("99_hash_all", "全部校验值…", "hash_all", False),
    ]


# ---------------------------------------------------------------------------
# 写入 / 读取 / 删除
# ---------------------------------------------------------------------------
def _write_command(wr, parent_key, cmd):
    """在 parent_key 下建 command 子键并写入命令行（默认值）。"""
    ck = wr.CreateKey(parent_key, "command")
    try:
        wr.SetValueEx(ck, "", 0, wr.REG_SZ, cmd)
    finally:
        wr.CloseKey(ck)


def _write_cascade(wr, base, label, exe_q, icon, scope):
    """写一个带级联子菜单的静态 verb（父键 + shell 子键 + 各项）。"""
    arg = '"%V"' if scope == "bg" else '"%1"'
    applies = archive_applies_to()

    k = wr.CreateKey(wr.HKEY_CURRENT_USER, base)
    try:
        # ─────────────────────────────────────────────────────────────
        # 微软级联菜单硬性要求（缺了任一 Explorer 都不认它是级联）：
        #   ① 父键默认值留空（"value not set"）—— 否则 Explorer 会把它
        #      当成普通 verb 去要 command，点击就弹「没有关联的应用」。
        #      这里显式写空串，清掉旧版残留的 (Default)=ZipForge。
        #   ② MUIVerb 承载显示名（替代默认值，微软推荐写法）。
        #   ③ SubCommands 空串声明「子项都在我的 shell 子键下」。
        # ─────────────────────────────────────────────────────────────
        wr.SetValueEx(k, "", 0, wr.REG_SZ, "")            # 清空默认值
        wr.SetValueEx(k, "MUIVerb", 0, wr.REG_SZ, label)
        wr.SetValueEx(k, "SubCommands", 0, wr.REG_SZ, "")  # ★ 关键修复
        wr.SetValueEx(k, "Icon", 0, wr.REG_SZ, icon)
        wr.SetValueEx(k, "Position", 0, wr.REG_SZ, "Top")
        if scope in ("file", "dir"):
            # Player 模式：多选时只启动一次，其余选中项作为附加参数追加
            wr.SetValueEx(k, "MultiSelectModel", 0, wr.REG_SZ, "Player")
        sk = wr.CreateKey(k, "shell")                    # 级联子菜单容器
        try:
            for key, lbl, verb, arc_only in menu_items(scope):
                ik = wr.CreateKey(sk, key)
                try:
                    wr.SetValueEx(ik, "", 0, wr.REG_SZ, lbl)
                    if arc_only:
                        wr.SetValueEx(ik, "AppliesTo", 0, wr.REG_SZ, applies)
                    # --scope 让程序区分「选中文件夹」(file/dir → 归档生成在
                    # 文件夹旁边) 与「文件夹空白处右键」(bg → 归档生成在文件夹里),
                    # 因为二者传给程序的路径长得一模一样，只能靠命令行带上标识。
                    _write_command(wr, ik,
                                   f"{exe_q} --verb {verb} --scope {scope} {arg}")
                finally:
                    wr.CloseKey(ik)
        finally:
            wr.CloseKey(sk)
    finally:
        wr.CloseKey(k)


def _read_verb_command(wr, base):
    """读回 command 子键的默认值，用于注册后自检；读不到返回 None。"""
    try:
        k = wr.OpenKey(wr.HKEY_CURRENT_USER, base + r"\command")
    except OSError:
        return None
    try:
        val, _ = wr.QueryValueEx(k, "")
        return val
    except OSError:
        return None
    finally:
        wr.CloseKey(k)


def _read_value(wr, base, name):
    try:
        k = wr.OpenKey(wr.HKEY_CURRENT_USER, base)
    except OSError:
        return None
    try:
        val, _ = wr.QueryValueEx(k, name)
        return val
    except OSError:
        return None
    finally:
        wr.CloseKey(k)


def read_cascade(wr, base):
    """读回级联子菜单：返回 [(子键名, 显示文字, 命令行), ...]。"""
    out = []
    try:
        sk = wr.OpenKey(wr.HKEY_CURRENT_USER, base + r"\shell")
    except OSError:
        return out
    try:
        i = 0
        while True:
            try:
                name = wr.EnumKey(sk, i)
                i += 1
            except OSError:
                break
            lbl = ""
            try:
                ik = wr.OpenKey(sk, name)
                try:
                    lbl, _ = wr.QueryValueEx(ik, "")
                except OSError:
                    lbl = ""
                finally:
                    wr.CloseKey(ik)
            except OSError:
                pass
            cmd = _read_verb_command(wr, base + "\\shell\\" + name) or ""
            out.append((name, lbl, cmd))
    finally:
        wr.CloseKey(sk)
    return out


def _delete_tree(wr, base):
    """递归删除 base 及其所有子键；返回是否真的删掉了 base。"""
    try:
        k = wr.OpenKey(wr.HKEY_CURRENT_USER, base)
    except OSError:
        return False
    try:
        subs = []
        i = 0
        while True:
            try:
                subs.append(wr.EnumKey(k, i))
                i += 1
            except OSError:
                break
    finally:
        wr.CloseKey(k)
    for s in subs:
        _delete_tree(wr, base + "\\" + s)
    try:
        wr.DeleteKey(wr.HKEY_CURRENT_USER, base)
        return True
    except OSError:
        return False


def _prune_empty_shell(wr, base):
    """删掉 base 之后，若上一级名为 shell 的键已空则一并删掉，避免留空壳。

    只碰叶子名恰好是 "shell" 的父键，且 DeleteKey 在键非空时会抛错 ——
    因此绝不会误删系统自带的 shell 键内容。
    """
    parent = base.rsplit("\\", 1)[0]
    if parent.rsplit("\\", 1)[-1].lower() != "shell":
        return
    try:
        wr.DeleteKey(wr.HKEY_CURRENT_USER, parent)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# 对外 API
# ---------------------------------------------------------------------------
def register(exe=None, scopes=None):
    """安装右键级联菜单。scopes 可选 ["file","dir","bg"]，默认全部。"""
    wr = _reg()
    if wr is None:
        return (False, "当前系统不支持（仅 Windows）或缺少 winreg 模块。")
    exe = os.path.abspath(exe or exe_path())
    exe_q = '"' + exe.replace('"', '') + '"'
    icon = exe + ",0"
    scopes = scopes or list(_ROOT_KEYS.keys())
    try:
        for scope in scopes:
            _write_cascade(wr, _ROOT_KEYS[scope], MENU_NAME, exe_q, icon, scope)

        # 写完读回自检：确保每个根键都能列全子菜单项且命令行非空
        problems = []
        total = 0
        for scope in scopes:
            base = _ROOT_KEYS[scope]
            rows = read_cascade(wr, base)
            total += len(rows)
            expect = len(menu_items(scope))
            if len(rows) != expect:
                problems.append(f"{scope}: 期望 {expect} 项，实得 {len(rows)}")
                continue
            missing = [n for n, _, c in rows if not c]
            if missing:
                problems.append(f"{scope}: 以下项缺少命令行 {missing}")
        if problems:
            return (False, "注册已写入但自检未通过：\n" + "\n".join(problems))
        return (True,
                f"已集成右键菜单（共 {total} 个操作，指向）：\n{exe}\n\n"
                "右键任意文件 / 文件夹 / 空白处即可看到 ZipForge 子菜单，"
                "选中即直接执行。\n"
                "若菜单未立刻出现，重启一次资源管理器即可。")
    except Exception as e:
        return (False, f"注册失败：{type(e).__name__}: {e}")


def unregister():
    wr = _reg()
    if wr is None:
        return (False, "当前系统不支持。")
    removed = 0
    try:
        for base in _KEYS:
            if _delete_tree(wr, base):
                removed += 1
                _prune_empty_shell(wr, base)
        if removed:
            return (True, f"已移除 {removed} 处右键菜单注册。")
        return (True, "未发现已注册的项（无需移除）。")
    except Exception as e:
        return (False, f"移除失败：{type(e).__name__}: {e}")


def is_registered():
    """是否已安装（要求三个根键都在，且至少 file 根有子菜单项）。"""
    wr = _reg()
    if wr is None:
        return False
    try:
        for base in _KEYS:
            k = wr.OpenKey(wr.HKEY_CURRENT_USER, base)
            wr.CloseKey(k)
        return len(read_cascade(wr, _KEYS[0])) > 0
    except OSError:
        return False


def registered_exe():
    """返回已注册菜单指向的 exe（从 file 根下第一项的 command 里解析）。"""
    wr = _reg()
    if wr is None:
        return ""
    rows = read_cascade(wr, _KEYS[0])
    for _, _, cmd in rows:
        if cmd:
            cmd = cmd.strip()
            if cmd.startswith('"'):
                end = cmd.find('"', 1)
                if end > 0:
                    return cmd[1:end]
            return cmd.split(" ", 1)[0]
    return ""


def status():
    """给界面用的集成状态摘要。"""
    wr = _reg()
    info = {"supported": wr is not None, "installed": False,
            "exe": "", "items": 0, "stale": False}
    if wr is None:
        return info
    info["installed"] = is_registered()
    info["exe"] = registered_exe()
    try:
        info["items"] = len(read_cascade(wr, _KEYS[0]))
    except Exception:
        info["items"] = 0
    cur = exe_path()
    info["stale"] = bool(info["exe"]) and os.path.normcase(info["exe"]) != os.path.normcase(cur)
    return info
