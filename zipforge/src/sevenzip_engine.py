# -*- coding: utf-8 -*-
"""
sevenzip_engine.py
================================================================================
ZipForge 的核心引擎层。
调用 GitHub 开源项目 mcmilk/7-Zip-zstd 的预编译 7z.exe / 7z.dll 作为底层压缩内核。
7-Zip-ZS 相比官方 7-Zip 额外整合了 Zstandard / Brotli / LZ4 / LZ5 / Lizard /
Fast-LZMA2 等编解码器，使本软件在「功能像 7-Zip 一样强大」之外更进一步。

本模块只做三件事：
  1. 定位引擎 (locate_engine)
  2. 解析 7z 的结构化输出 (list_archive / test_archive)
  3. 以子进程方式驱动 7z 完成 解压 / 压缩 / 更新，并把实时进度回调给 UI

所有接口均为同步函数；需要后台执行时由上层在独立线程中调用。
"""
import os
import re
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from shutil import which

HERE = Path(__file__).resolve().parent


def _engine_candidates():
    """引擎可能所在的位置：打包后单文件/单目录、源码布局、系统安装。"""
    cands = []
    try:
        cands.append(Path(sys.executable).resolve().parent / "vendor" / "engine-x64")
    except Exception:
        pass
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        cands.append(Path(meipass) / "vendor" / "engine-x64")
    cands.append(HERE.parent / "vendor" / "engine-x64")
    return cands


ENGINE_DIR = HERE.parent / "vendor" / "engine-x64"  # 源码布局下的默认位置
# 临时清单/工作目录：固定在项目内，避免依赖系统 TEMP（中文路径/沙箱不可写）
ZF_TMP = HERE.parent / "tools" / "_zftmp"
try:
    ZF_TMP.mkdir(parents=True, exist_ok=True)
except Exception:
    # 极端情况下回退到用户主目录下的隐藏目录
    ZF_TMP = Path.home() / ".zipforge_tmp"
    try:
        ZF_TMP.mkdir(parents=True, exist_ok=True)
    except Exception:
        ZF_TMP = Path(tempfile.gettempdir())


def _zf_tmp() -> str:
    try:
        ZF_TMP.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return str(ZF_TMP)


def new_temp_dir(prefix: str = "zf_open_") -> str:
    """在引擎自管的工作目录下创建一个临时目录并返回路径。

    用于「双击归档内文件 → 提取到临时目录再用系统程序打开」这类场景。
    刻意不使用系统 TEMP：中文用户名路径 / 受限环境可能导致写入失败。
    """
    import uuid
    d = Path(_zf_tmp()) / (prefix + uuid.uuid4().hex[:8])
    d.mkdir(parents=True, exist_ok=True)
    return str(d)


def purge_temp_dirs(max_age_hours: int = 24) -> int:
    """清理历史遗留的临时提取目录（默认只删 24 小时前的，避免删掉正在被
    外部程序打开的文件）。返回删除的目录数。"""
    import shutil
    import time
    removed = 0
    base = Path(_zf_tmp())
    cutoff = time.time() - max_age_hours * 3600
    try:
        for p in base.iterdir():
            if not p.is_dir():
                continue
            if not p.name.startswith(("zf_open_", "zf_selftest")):
                continue
            try:
                if p.stat().st_mtime < cutoff:
                    shutil.rmtree(p, ignore_errors=True)
                    removed += 1
            except OSError:
                pass
    except OSError:
        pass
    return removed
SYS_7Z_PATHS = [
    r"C:\Program Files\7-Zip\7z.exe",
    r"C:\Program Files (x86)\7-Zip\7z.exe",
]

CREATE_NO_WINDOW = 0x08000000  # Windows：不弹黑色控制台窗口


class EngineError(Exception):
    """引擎执行层面的错误（非 0 退出码、找不到引擎等）。"""


class EngineNotFoundError(EngineError):
    """没有可用的 7z 引擎。"""


def locate_engine() -> str:
    """按优先级查找 7z 引擎：
    1. PyInstaller 解压目录 / 与可执行文件同目录的 vendor/engine-x64（打包后）
    2. 项目自带（源码布局 vendor/engine-x64/7z.exe，随 ZipForge 分发）
    3. 系统已安装的 7-Zip
    4. PATH 中的 7z / 7za
    """
    for d in _engine_candidates():
        p = d / "7z.exe"
        if p.exists():
            return str(p)
    for p in SYS_7Z_PATHS:
        if os.path.exists(p):
            return p
    found = which("7z") or which("7za")
    if found:
        return found
    raise EngineNotFoundError(
        "未找到 7-Zip 引擎。请将 7z.exe 放入 vendor/engine-x64/，或安装官方 7-Zip。"
    )


def engine_version() -> str:
    try:
        out = subprocess.run(
            [locate_engine(), "i"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=CREATE_NO_WINDOW, timeout=30,
        )
        raw = (out.stdout or b"") + (out.stderr or b"")
        try:
            txt = raw.decode("utf-8")
        except UnicodeDecodeError:
            txt = raw.decode("gbk", errors="replace")
        m = re.search(r"7-Zip[^\n]*", txt)
        return m.group(0).strip() if m else "未知"
    except Exception:
        return "未知"


# ----------------------------------------------------------------------------
# 列表解析
# ----------------------------------------------------------------------------
_PROGRESS_RE = re.compile(r"^\s*(\d{1,3})%\s*(\d+)\s*([+\-])?\s*(.*)$")
_PCT_RE = re.compile(r"(\d{1,3})%")


def _run(args, password=None, on_progress=None, timeout=86400):
    """通用子进程执行 + 进度解析。返回 (returncode, full_text, ok)。"""
    cmd = [locate_engine()] + args
    if password:
        cmd.append(f"-p{password}")
    # 进度/错误信息输出到 stderr，便于解析
    cmd += ["-bse2", "-bsp2"]
    full = []
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            # 二进制读取：7z 在中文系统上混用 GBK/UTF-8，避免解码崩溃
            creationflags=CREATE_NO_WINDOW,
        )
    except FileNotFoundError as e:
        raise EngineNotFoundError("引擎可执行文件无法启动：" + str(e))

    def _decode(b):
        try:
            return b.decode("utf-8")
        except UnicodeDecodeError:
            try:
                return b.decode("gbk", errors="replace")
            except UnicodeDecodeError:
                return b.decode("utf-8", errors="replace")

    with proc:
        # 逐行读取（按 \n 切分，容忍不完整尾行）
        buf = bytearray()
        while True:
            chunk = proc.stdout.read(1 << 16)
            if not chunk:
                break
            buf.extend(chunk)
            while b"\n" in buf:
                idx = buf.index(b"\n") + 1
                raw = bytes(buf[:idx])
                del buf[:idx]
                line = _decode(raw)
                full.append(line)
                if on_progress:
                    m = _PCT_RE.search(line)
                    if m:
                        on_progress(int(m.group(1)), line.strip())
        if buf:
            line = _decode(bytes(buf))
            full.append(line)
            if on_progress:
                m = _PCT_RE.search(line)
                if m:
                    on_progress(int(m.group(1)), line.strip())
        proc.wait(timeout=timeout)

    text = "".join(full)
    ok = proc.returncode == 0 and "Everything is Ok" in text
    return proc.returncode, text, ok


def list_archive(path: str, password: str = None) -> dict:
    """列出归档内容。

    返回 {archive: {...}, items: [...], raw: str, ok: bool, rc: int, error: str}。
    ok 在以下情况为 True：
      - 引擎返回码 0（正常列出）；
      - 返回码 2（加密归档未给密码，但仍能列出条目与加密标记）。
    其它返回码（如 1=警告、文件损坏等）且未解析到条目时视为失败。
    """
    if not os.path.exists(path):
        raise EngineError(f"文件不存在：{path}")
    args = ["l", "-slt", "-ba", path]
    rc, text, ok = _run(args, password=password)
    items, archive = _parse_list(text)
    # 判定成功：rc=0（正常列出），或 rc=2 但确实解析到了条目（加密归档未给密码时
    # 仍能列出条目与加密标记）。rc=2 但 0 条目 = 文件损坏/不可识别 -> 失败。
    list_ok = (rc == 0) or (rc == 2 and len(items) > 0)
    error = ""
    if not list_ok:
        # 从输出里挑一行最像错误的信息
        for ln in text.splitlines():
            if "Error" in ln or "error" in ln or "错误" in ln or "Cannot" in ln:
                error = ln.strip()
                break
        if not error:
            error = (f"引擎返回码 {rc}，无法读取该归档"
                     f"（可能已损坏、需要密码，或格式不被支持）。")
    return {"archive": archive, "items": items, "raw": text,
            "ok": list_ok, "rc": rc, "error": error}


def _after_eq(s):
    """取 'Key = value' 中 '=' 之后的内容。

    统一走这个函数而不是手写 s[N:] 切片：'Modified = ' 是 11 个字符，
    之前手写成 s[12:] 会悄悄吃掉年份的第一位（2026 → 026），
    这类 off-by-one 在界面上表现为"时间显示得很怪"，极难排查。
    """
    return s.split("=", 1)[1].strip() if "=" in s else ""


def _as_int(s):
    try:
        return int(s)
    except (TypeError, ValueError):
        return 0


def norm_modified(s):
    """把 7z 输出的时间戳整理成界面能直接显示的 'YYYY-MM-DD HH:MM:SS'。

    7z 的 -slt 输出形如 `2026-04-29 16:33:30.0780000`：
      • 尾部的纳秒精度残留对界面毫无意义，必须去掉；
      • 个别容器会给出全 0 时间（未记录修改时间），此时返回空串，
        让界面显示空白，而不是 "0000-00-00"。
    """
    s = (s or "").strip()
    if not s or s.startswith("0000"):
        return ""
    if "." in s:
        s = s.split(".", 1)[0].strip()
    return s


def _parse_list(text: str):
    """解析 `7z l -slt -ba` 输出。

    -slt 输出中，被空行分隔的若干「块」：第一个块是归档自身的属性，
    其余块是归档内文件/目录的属性。通过是否含 Physical Size 区分两者。
    """
    archive = {}
    items = []
    cur = None
    is_archive = False

    def flush():
        nonlocal cur, is_archive
        if cur is None:
            return
        if is_archive:
            archive.update(cur)
        else:
            items.append(cur)
        cur = None
        is_archive = False

    for line in text.splitlines():
        s = line.strip()
        if not s:
            flush()
            continue
        if s.startswith("Path = "):
            flush()
            # 7z 在 Windows 上输出反斜杠路径，统一归一化为正斜杠，
            # 以便目录聚合、导航与提取逻辑一致。
            cur = {"path": _after_eq(s).replace("\\", "/")}
            continue
        if cur is None:
            # 归档自身可能不以 Path 开头（极少见），忽略
            continue
        if s.startswith("Type = "):
            cur["type"] = _after_eq(s)
            is_archive = True
        elif s.startswith("Physical Size = "):
            cur["physical"] = _as_int(_after_eq(s))
            is_archive = True
        elif s.startswith("Size = "):
            cur["size"] = _as_int(_after_eq(s))
        elif s.startswith("Packed Size = "):
            cur["packed"] = _as_int(_after_eq(s))
        elif s.startswith("Modified = "):
            cur["modified"] = norm_modified(_after_eq(s))
        elif s.startswith("Attributes = "):
            cur["attr"] = _after_eq(s)
            cur["attributes"] = cur["attr"]
        elif s.startswith("CRC = "):
            cur["crc"] = _after_eq(s)
        elif s.startswith("Encrypted = "):
            cur["encrypted"] = (_after_eq(s) == "+")
        elif s.startswith("Method = "):
            cur["method"] = _after_eq(s)
        elif s.startswith("Block = "):
            cur["block"] = _after_eq(s)
        elif s.startswith("Folder = "):
            cur["folder"] = (_after_eq(s) == "+")
        elif s.startswith("Comment = "):
            cur["comment"] = _after_eq(s)
    flush()

    # 目录判定的统一收口（实测踩坑）：
    #   不同容器格式标记目录的方式不同 ——
    #     · rar / tar 等：有 "Folder = +" 行
    #     · 7z  等：没有 Folder 行，而是用 Windows 属性位 "Attributes = D"
    #   早期只认 Folder，导致 7z 归档里的目录条目被当作文件（进而双击时去"提取文件"）。
    for it in items:
        attr = (it.get("attributes") or "").upper()
        is_dir_bit = "D" in re.findall(r"[A-Z]", attr)  # Windows 属性位 D=目录
        if is_dir_bit:
            it["folder"] = True
        it.setdefault("folder", False)
    return items, archive


# ----------------------------------------------------------------------------
# 解压 / 测试
# ----------------------------------------------------------------------------
def test_archive(path: str, password: str = None, on_progress=None) -> dict:
    rc, text, ok = _run(["t", path], password=password, on_progress=on_progress)
    return {"ok": ok, "rc": rc, "text": text}


def extract_archive(path: str, dest: str, items=None, password: str = None,
                    on_progress=None, overwrite: str = "ask") -> dict:
    """解压归档。

    items: 可选，归档内相对路径列表；None 表示全部。
    overwrite: ask(默认-y)/yes(覆盖)/skip(跳过已存在)/fresh(仅更新)
    """
    os.makedirs(dest, exist_ok=True)
    args = ["x", path, f"-o{dest}", "-y"]
    ow_map = {"yes": "-aoa", "skip": "-aos", "fresh": "-aou", "rename": "-aot", "ask": "-aoa"}
    args.append(ow_map.get(overwrite, "-ay"))
    if items:
        # 用列表文件指定要提取的条目，避免命令行过长
        fd, listfile = tempfile.mkstemp(prefix="zf_extract_", suffix=".txt", dir=_zf_tmp())
        try:
            with os.fdopen(fd, "w", encoding="utf-8-sig") as f:
                f.write("\n".join(items))
            args.append("@" + listfile)
            rc, text, ok = _run(args, password=password, on_progress=on_progress)
        finally:
            try:
                os.remove(listfile)
            except OSError:
                pass
    else:
        rc, text, ok = _run(args, password=password, on_progress=on_progress)
    return {"ok": ok, "rc": rc, "text": text}


# ----------------------------------------------------------------------------
# 压缩 / 更新
# ----------------------------------------------------------------------------
def compress(sources, dest: str, fmt: str = "7z", level: int = 5,
             threads: int = 0, solid: bool = True, password: str = None,
             encrypt_header: bool = False, dict_size: str = None,
             volume: str = None, on_progress=None, extra_switches=None) -> dict:
    """压缩 sources（文件/目录列表）到 dest。

    fmt: 7z/zip/gzip/bzip2/xz/wim/tar/tar/... 以及 7-Zip-ZS 扩展的
         zstd/brotli/lz4/lz5/lizard
    level: 0(存储)~9(极限)
    threads: 0=自动(=CPU核数), 否则指定
    solid: 是否固实压缩（7z/zip 支持）
    encrypt_header: 仅 7z，加密文件头（不输密码看不到文件名）
    dict_size: 如 64m/128m/1g
    volume: 分卷大小，如 100m/2g/700m
    """
    fd, listfile = tempfile.mkstemp(prefix="zf_compress_", suffix=".txt", dir=_zf_tmp())
    try:
        with os.fdopen(fd, "w", encoding="utf-8-sig") as f:
            f.write("\n".join(os.path.abspath(s) for s in sources))
        args = ["a", dest, f"-t{fmt}", f"-mx{level}", "-y", "@" + listfile]
        if threads:
            args.append(f"-mmt={threads}")
        else:
            args.append("-mmt=on")
        if not solid and fmt in ("7z", "zip"):
            args.append("-ms=off")
        if password:
            if fmt == "7z" and encrypt_header:
                args.append("-mhe=on")
        if dict_size:
            args.append(f"-md={dict_size}")
        if volume:
            args.append(f"-v{volume}")
        if extra_switches:
            args.extend(extra_switches)
        rc, text, ok = _run(args, password=password, on_progress=on_progress)
    finally:
        try:
            os.remove(listfile)
        except OSError:
            pass
    return {"ok": ok, "rc": rc, "text": text, "dest": dest}


def add_to_archive(archive_path: str, sources, password: str = None,
                   level: int = 5, on_progress=None) -> dict:
    """向已有归档追加文件（更新模式）。"""
    fd, listfile = tempfile.mkstemp(prefix="zf_add_", suffix=".txt", dir=_zf_tmp())
    try:
        with os.fdopen(fd, "w", encoding="utf-8-sig") as f:
            f.write("\n".join(os.path.abspath(s) for s in sources))
        args = ["a", archive_path, f"-mx{level}", "-y", "@" + listfile]
        rc, text, ok = _run(args, password=password, on_progress=on_progress)
    finally:
        try:
            os.remove(listfile)
        except OSError:
            pass
    return {"ok": ok, "rc": rc, "text": text}


def delete_from_archive(archive_path: str, items, password: str = None,
                        on_progress=None) -> dict:
    """从归档删除指定条目。"""
    fd, listfile = tempfile.mkstemp(prefix="zf_del_", suffix=".txt", dir=_zf_tmp())
    try:
        with os.fdopen(fd, "w", encoding="utf-8-sig") as f:
            f.write("\n".join(items))
        args = ["d", archive_path, "-y", "@" + listfile]
        rc, text, ok = _run(args, password=password, on_progress=on_progress)
    finally:
        try:
            os.remove(listfile)
        except OSError:
            pass
    return {"ok": ok, "rc": rc, "text": text}


# ----------------------------------------------------------------------------
# 哈希（7z 的 h 命令）
# ----------------------------------------------------------------------------
# 实测 `7z h -scrcSHA256 file` 的稳定输出尾部形如：
#     SHA256 for data:              e301bb63...7085
#     SHA256 for data and names:    52a8ab8e...-00000001   （目录多这一行）
#
# ⚠ 踩过的坑：早先的正则写成 rf"{algo}\s+([0-9a-fA-F]+)"，
#   会在 "SHA256 **f**or data:" 这里把 'f' 当成十六进制匹配下来 ——
#   hash_data() 恒返回 "f"，且因为不做长度校验一直没被发现。
#   现在改为锚定整行 + 要求结尾，彻底避免误匹配。
#   实测：目录 / 多条目聚合时，值尾部还会带一个 "‑<8位>" 的区间计数器，例如
#     SHA256 for data:              1073d1a5...a3b806-00000001
#   因此值的字符集必须允许一个可选的 "-hex" 尾巴（早期只允许纯 hex，
#   导致"对文件夹求哈希恒返回空"）。
_HASH_VAL = r"([0-9a-fA-F]+(?:-[0-9a-fA-F]+)?)"
_HASH_LINE_RE = re.compile(
    rf"^\s*([A-Za-z0-9][A-Za-z0-9\-_]*)\s+for data:\s*{_HASH_VAL}\s*$")
_HASH_NAMES_RE = re.compile(
    rf"^\s*([A-Za-z0-9][A-Za-z0-9\-_]*)\s+for data and names:\s*{_HASH_VAL}\s*$")


def _parse_hash_lines(text: str) -> dict:
    """把 `7z h` 输出解析成 {算法名: 值}。

    同时收录 "for data and names"（目录/多文件时出现，含文件名摘要），
    键名加 " (names)" 后缀以示区别。
    """
    out = {}
    for line in (text or "").splitlines():
        m = _HASH_LINE_RE.match(line)
        if m:
            out[m.group(1).upper()] = m.group(2)
            continue
        m = _HASH_NAMES_RE.match(line)
        if m:
            out[m.group(1).upper() + " (names)"] = m.group(2)
    return out


def hash_data(path: str, algo: str = "SHA256") -> str:
    """计算单个算法哈希，返回十六进制串（失败返回空串）。"""
    rc, text, ok = _run(["h", f"-scrc{algo}", path], timeout=3600)
    # ⚠ 必须判 ok：文件不存在时引擎仍会打印一行全 0 的假哈希，
    #   不校验就会把 000…000 当成真结果返回给用户。
    if not ok:
        return ""
    return _parse_hash_lines(text).get(algo.upper(), "")


def hash_all_data(path: str) -> dict:
    """用 `-scrc*` 一次性算出引擎支持的全部哈希，返回 {算法名: 值}。"""
    rc, text, ok = _run(["h", "-scrc*", path], timeout=3600)
    if not ok:
        return {}
    return _parse_hash_lines(text)


if __name__ == "__main__":
    print("Engine:", locate_engine())
    print("Version:", engine_version())
