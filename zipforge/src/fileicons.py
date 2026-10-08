# -*- coding: utf-8 -*-
"""
fileicons.py — 取系统文件类型图标（仅 Windows）。

零第三方依赖：通过 ctypes 调用 shell32 / gdi32 / user32，
用 SHGetFileInfo 拿到 HICON，把它的位图取回成像素，再交给 tkinter 显示。

【为什么不用 base64 + PPM 交给 PhotoImage】
  Tk 8.6.15 实测：`PhotoImage(data=base64(PPM), format="ppm")` 会抛
  TclError: couldn't recognize image data —— Tk 的 -data 只对 GIF/PNG
  的 base64 生效，PPM 走不通（这个坑会让图标"静默消失"）。
  ✓ 本项目改用 `PhotoImage(width, height)` + `put("{#rrggbb ...} ...")`
    + `transparency_set()`：不依赖任何格式解析器，稳定可靠。

【alpha 的两种情况】
  • 现代图标（32bpp）：alpha 通道有效，直接合成到白色底。
  • 老式图标：整张颜色位图 alpha 全为 0，透明度由 AND 掩码位图决定
    （掩码为白 = 透明）。此时代码会自动改读掩码，避免出现黑方块。

对外只暴露 get_file_icon()；任何一步失败都返回 None，绝不抛异常影响主流程。
"""
import sys

# (是否目录, 扩展名) -> tk.PhotoImage
_cache = {}
# 缓存所属的 Tk 根窗口（PhotoImage 与创建它的 Tk 解释器绑定）
_cache_root = None


def _sync_root(tk):
    """确保缓存与当前 Tk 根窗口一致；返回当前根窗口（无根时 None）。

    PhotoImage 属于创建它的那个 Tk 解释器。切换主题会销毁旧根窗口、重建新
    根窗口，旧根上创建的图像在新解释器里**全部失效**，一旦再拿去填进列表
    就会抛：
        TclError: image "pyimageN" doesn't exist
    （这正是「更换主题后启动失败」的成因。）
    因此这里做一次廉价的自愈：发现根窗口换了就整体丢弃缓存。
    """
    global _cache_root
    root = getattr(tk, "_default_root", None)
    if root is not _cache_root:
        _cache.clear()
        _cache_root = root
    return root


def get_file_icon(ext, is_dir=False, large=False):
    """返回 tk.PhotoImage 或 None。

    ext:    不含点的扩展名，如 'docx'；目录时忽略。
    is_dir: True 取文件夹图标。
    large:  True 取 32x32，默认取 16x16（列表行高用）。
    """
    if sys.platform != "win32":
        return None
    try:
        import tkinter as tk
        if _sync_root(tk) is None:
            return None
        key = (bool(is_dir), (ext or "").lower(), bool(large))
        if key in _cache:
            return _cache[key]
        img = _load_icon(ext, is_dir, large)
        _cache[key] = img          # 失败也缓存 None，避免反复尝试
        return img
    except Exception:
        return None


def is_alive(img):
    """图像是否仍属于当前 Tk 解释器（能安全用于控件）。

    切换主题/重建根窗口后，旧图像调用任何方法都会抛异常 —— 借此判定失效。
    只对「看起来是 Tk 图像」的对象（有可调用的 width()）下结论；
    其它对象（测试桩、自定义图标替身）无从判定，一律视为可用，避免误杀。
    """
    if img is None:
        return False
    width = getattr(img, "width", None)
    if not callable(width):
        return True
    try:
        width()
        return True
    except Exception:
        return False


def clear_cache():
    """丢弃全部缓存（下次调用重新从系统取图标）。

    切换主题、重建根窗口时必须调用；此外 get_file_icon() 检测到根窗口变化
    时也会自动清理，双保险。
    """
    global _cache_root
    _cache.clear()
    _cache_root = None


# ---------------------------------------------------------------------------
# 内部实现
# ---------------------------------------------------------------------------
def _load_icon(ext, is_dir, large):
    import ctypes
    from ctypes import (c_int, c_uint, c_long, c_short, c_ubyte, c_void_p,
                        c_wchar, c_wchar_p, byref, sizeof, create_string_buffer)
    import tkinter as tk

    shell32 = ctypes.windll.shell32
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    SHGFI_ICON = 0x100
    SHGFI_SMALLICON = 0x1
    SHGFI_LARGEICON = 0x0
    SHGFI_USEFILEATTRIBUTES = 0x10
    FILE_ATTRIBUTE_NORMAL = 0x80
    FILE_ATTRIBUTE_DIRECTORY = 0x10

    class SHFILEINFO(ctypes.Structure):
        _fields_ = [
            ("hIcon", c_void_p),
            ("iIcon", c_int),
            ("dwAttributes", c_uint),
            ("szDisplayName", c_wchar * 260),
            ("szTypeName", c_wchar * 80),
        ]

    class ICONINFO(ctypes.Structure):
        _fields_ = [
            ("fIcon", c_int),        # BOOL，用 c_int 保证 4 字节对齐
            ("xHotspot", c_uint),
            ("yHotspot", c_uint),
            ("hbmMask", c_void_p),
            ("hbmColor", c_void_p),
        ]

    class BITMAP(ctypes.Structure):
        _fields_ = [
            ("bmType", c_long),
            ("bmWidth", c_long),
            ("bmHeight", c_long),
            ("bmWidthBytes", c_long),
            ("bmPlanes", c_short),
            ("bmBitsPixel", c_short),
            ("bmBits", c_void_p),
        ]

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", c_uint),
            ("biWidth", c_long),
            ("biHeight", c_long),
            ("biPlanes", c_short),
            ("biBitCount", c_short),
            ("biCompression", c_uint),
            ("biSizeImage", c_uint),
            ("biXPelsPerMeter", c_long),
            ("biYPelsPerMeter", c_long),
            ("biClrUsed", c_uint),
            ("biClrImportant", c_uint),
        ]

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [("bmiHeader", BITMAPINFOHEADER),
                    ("bmiColors", c_ubyte * 1024)]

    def read_pixels(hbm, w, h):
        """把位图读成 bytes(BGRA)，行序自顶向下；失败返回 None。"""
        buf = create_string_buffer(w * h * 4)
        bmi = BITMAPINFO()
        hdr = bmi.bmiHeader
        hdr.biSize = sizeof(BITMAPINFOHEADER)
        hdr.biWidth = w
        hdr.biHeight = -h            # 负高度 = 自顶向下
        hdr.biPlanes = 1
        hdr.biBitCount = 32          # 统一索取 32bpp（GDI 会自动转换）
        hdr.biCompression = 0        # BI_RGB
        hdc = gdi32.CreateCompatibleDC(0)
        try:
            rows = gdi32.GetDIBits(hdc, c_void_p(hbm), 0, h, buf, byref(bmi), 0)
        finally:
            gdi32.DeleteDC(hdc)
        if not rows:
            return None
        return buf.raw

    # ---- 1. 拿图标句柄（不要求真实文件存在） ----
    sfi = SHFILEINFO()
    if is_dir:
        attrs = FILE_ATTRIBUTE_DIRECTORY | FILE_ATTRIBUTE_NORMAL
        path = "dummy"
    else:
        attrs = FILE_ATTRIBUTE_NORMAL
        path = "." + (ext or "")
    flags = SHGFI_ICON | SHGFI_USEFILEATTRIBUTES | (
        SHGFI_LARGEICON if large else SHGFI_SMALLICON)
    if not shell32.SHGetFileInfoW(c_wchar_p(path), attrs, byref(sfi),
                                  sizeof(sfi), flags):
        return None
    hicon = sfi.hIcon
    if not hicon:
        return None

    try:
        # ---- 2. 拆出颜色位图与掩码位图 ----
        ii = ICONINFO()
        if not user32.GetIconInfo(c_void_p(hicon), byref(ii)):
            return None
        try:
            hbm_color, hbm_mask = ii.hbmColor, ii.hbmMask
            if not hbm_color:
                return None
            bmp = BITMAP()
            if not gdi32.GetObjectW(c_void_p(hbm_color), sizeof(bmp), byref(bmp)):
                return None
            w, h = bmp.bmWidth, abs(bmp.bmHeight)
            if w <= 0 or h <= 0 or w > 256 or h > 256:
                return None
            px = read_pixels(hbm_color, w, h)
            if px is None:
                return None

            alphas = px[3::4]
            has_alpha = any(alphas)

            # 老式图标：颜色位图 alpha 全 0，用掩码判定透明
            transparent = None
            if not has_alpha and hbm_mask:
                mpx = read_pixels(hbm_mask, w, h)
                if mpx:
                    transparent = [mpx[i * 4] > 127 for i in range(w * h)]

            return _to_photoimage(px, w, h, has_alpha, transparent)
        finally:
            if ii.hbmColor:
                gdi32.DeleteObject(c_void_p(ii.hbmColor))
            if ii.hbmMask:
                gdi32.DeleteObject(c_void_p(ii.hbmMask))
    finally:
        user32.DestroyIcon(c_void_p(hicon))


def _to_photoimage(px, w, h, has_alpha, transparent):
    """BGRA 像素 → PhotoImage。

    has_alpha=True：按 alpha 合成到白色（列表底色为白），并对完全透明的
                    像素调用 transparency_set，圆角处不出现白边。
    has_alpha=False：用掩码判定的透明像素单独置透明，其余保持原色。
    """
    import tkinter as tk

    rows = []
    transparent_cells = []
    for y in range(h):
        row = []
        for x in range(w):
            i = (y * w + x) * 4
            b, g, r, a = px[i], px[i + 1], px[i + 2], px[i + 3]
            if transparent is not None and transparent[y * w + x]:
                row.append("#ffffff")           # 先占位，随后整体置透明
                transparent_cells.append((x, y))
                continue
            if has_alpha:
                if a == 0:
                    row.append("#ffffff")
                    transparent_cells.append((x, y))
                    continue
                if a != 255:
                    t = a / 255.0
                    r = int(r * t + 255.0 * (1.0 - t))
                    g = int(g * t + 255.0 * (1.0 - t))
                    b = int(b * t + 255.0 * (1.0 - t))
            row.append("#%02x%02x%02x" % (r & 255, g & 255, b & 255))
        rows.append(row)

    img = tk.PhotoImage(width=w, height=h)
    img.put("{" + "} {".join(" ".join(r) for r in rows) + "}")
    for x, y in transparent_cells:
        try:
            img.transparency_set(x, y, True)
        except Exception:
            pass
    return img
