# -*- coding: utf-8 -*-
"""
formats.py — 格式识别、引擎路由与压缩预设。

ZipForge 支持两类引擎能力：
  A. 7-Zip-ZS 原生读写：7z / zip / gzip / bzip2 / xz / wim / tar
     以及 ZS 扩展的  zstd / brotli / lz4 / lz5 / lizard（读+写）
  B. 7-Zip 只读解压：rar / rar5 / cab / iso / arj / lzh / chm / msi ...
     （几乎覆盖你能遇到的所有归档格式）

本模块负责：
  - 根据扩展名判断归档类型与默认引擎
  - 暴露给 UI 的「压缩格式」与「压缩级别」预设
  - 为每种格式标注可用选项（是否支持加密文件头、固实、分卷等）
"""
from pathlib import Path

# 可创建（压缩）的格式 -> (7z -t 标识, 说明, 是否支持加密文件头, 是否支持固实)
CREATE_FORMATS = {
    "7z":   ("7z", "7-Zip（压缩比最高，推荐）", True, True),
    "zip":  ("zip", "ZIP（兼容性最好）", False, True),
    "zstd": ("zstd", "Zstandard（极快 + 高压缩）", False, False),
    "brotli": ("brotli", "Brotli（Web 友好）", False, False),
    "lz4":  ("lz4", "LZ4（超高速）", False, False),
    "lz5":  ("lz5", "LZ5（LZ4 增强）", False, False),
    "xz":   ("xz", "XZ（类 LZMA2，类 Unix 常用）", False, False),
    "gzip": ("gzip", "GZip（单文件）", False, False),
    "bzip2": ("bzip2", "BZip2（单文件）", False, False),
    "tar":  ("tar", "TAR（仅打包，不压缩）", False, False),
    "wim":  ("wim", "WIM（Windows 镜像）", False, False),
}

# 仅解压（只读）的常见格式
READONLY_FORMATS = {
    "rar", "rar5", "cab", "iso", "img", "arj", "lzh", "lha", "chm", "chi",
    "msi", "msp", "doc", "xls", "ppt", "swf", "nsis", "rpm", "deb", "cpio",
    "z", "taz", "tbz", "tbz2", "tgz", "txz", "tzst", "apfs", "rpm", "udeb",
    "xar", "sit", "dmg", "hfs", "hfsx", "qcow", "qcow2", "vdi", "vmdk",
}

# 压缩级别预设（数字越大越慢、压缩比越高）
LEVEL_PRESETS = {
    0: "存储（不压缩，仅打包）",
    1: "最快",
    3: "较快",
    5: "标准（推荐）",
    7: "较高",
    9: "极限（最慢，压缩比最高）",
}


# 单流（single-stream）格式：一次只能压缩**一个文件**，不能直接压缩文件夹。
# 官方 7-Zip 对这类格式压缩文件夹同样会报错，这里提前拦截并给出可操作提示。
SINGLE_STREAM_FORMATS = {"gzip", "bzip2", "xz", "zstd", "brotli", "lz4", "lz5"}


def is_single_stream(fmt: str) -> bool:
    return fmt in SINGLE_STREAM_FORMATS


def suggest_format(path: str) -> str:
    """根据文件扩展名猜测归档格式标识。"""
    ext = Path(path).suffix.lower().lstrip(".")
    # 复合扩展名
    p = Path(path).name.lower()
    if p.endswith(".tar.gz") or p.endswith(".tgz"):
        return "tar" if False else "gzip"  # 仅解压读取，压缩用 tar
    if p.endswith(".tar.zst") or p.endswith(".tzst"):
        return "zstd"
    if p.endswith(".tar.bz2") or p.endswith(".tbz2"):
        return "bzip2"
    if p.endswith(".tar.xz") or p.endswith(".txz"):
        return "xz"
    if ext in CREATE_FORMATS:
        return ext
    if ext in READONLY_FORMATS:
        return ext
    return ""


def is_archive(path: str) -> bool:
    ext = Path(path).suffix.lower().lstrip(".")
    return ext in CREATE_FORMATS or ext in READONLY_FORMATS


def can_create(fmt: str) -> bool:
    return fmt in CREATE_FORMATS


def format_label(fmt: str) -> str:
    info = CREATE_FORMATS.get(fmt)
    if info:
        return f"{fmt.upper()} — {info[1]}"
    return fmt.upper()


def default_ext(fmt: str) -> str:
    """给定格式标识，返回默认文件扩展名。"""
    mapping = {
        "7z": ".7z", "zip": ".zip", "zstd": ".zst", "brotli": ".br",
        "lz4": ".lz4", "lz5": ".lz5", "lizard": ".liz", "xz": ".xz",
        "gzip": ".gz", "bzip2": ".bz2", "tar": ".tar", "wim": ".wim",
    }
    return mapping.get(fmt, "." + fmt)
