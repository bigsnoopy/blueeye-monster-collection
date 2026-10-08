# -*- coding: utf-8 -*-
"""
make_icon.py — 用 Pillow 直接绘制「霓虹 ZF」程序图标（方案 10），
输出多尺寸 .ico（16/32/48/128/256）与一张 1024 预览 PNG。

设计：深紫黑圆角底板 + 青/品红双色发光描边的 ZF 字母 + 底部拉链霓虹线。
纯几何线条绘制，无字体依赖，任意尺寸缩放清晰。
"""
import os
from PIL import Image, ImageDraw, ImageFilter

S = 1024                      # 绘制源分辨率
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
ICO_PATH = os.path.join(OUT_DIR, "icon_zf_neon.ico")
PNG_PATH = os.path.join(OUT_DIR, "icon_zf_neon_preview.png")
SIZES_PATH = os.path.join(OUT_DIR, "icon_zf_neon_sizes.png")
PNG128_PATH = os.path.join(OUT_DIR, "icon_zf_neon_128.png")

# 调色板
BG_TOP = (24, 13, 46)         # 顶部深紫
BG_BOT = (7, 4, 18)           # 底部近黑
CYAN = (0, 240, 255)
MAGENTA = (255, 43, 214)
CYAN_CORE = (180, 255, 255)
MAGENTA_CORE = (255, 180, 245)
WHITE = (255, 255, 255)

W = int(0.050 * S)            # 字母霓虹芯线宽


def vertical_gradient(top, bot, size):
    """垂直渐变背景（无 numpy，借 linear_gradient + composite）。"""
    top_img = Image.new("RGB", (size, size), top)
    bot_img = Image.new("RGB", (size, size), bot)
    grad = Image.linear_gradient("L").resize((1, size)).resize((size, size))
    mask = grad.point(lambda v: 255 - v)        # 顶部亮、底部暗
    return Image.composite(top_img, bot_img, mask)


def rounded_alpha(size, radius):
    m = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(m)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return m


def neon_path(draw_glow, target, path, color, core_color, width, glow_only=False):
    """在 glow 层画粗低透明线（随后整体模糊），在 target 画清晰芯线 + 白色高光。"""
    r, g, b = color
    w = int(width)
    # ---- glow 多层 ----
    draw_glow.line(path, fill=(r, g, b, 38), width=w * 6, joint="curve")
    draw_glow.line(path, fill=(r, g, b, 70), width=w * 3, joint="curve")
    draw_glow.line(path, fill=(r, g, b, 95), width=int(w * 1.7), joint="curve")
    if glow_only:
        return
    cr, cg, cb = core_color
    target.line(path, fill=(cr, cg, cb, 255), width=w, joint="curve")
    target.line(path, fill=(WHITE[0], WHITE[1], WHITE[2], 210), width=max(2, w // 3), joint="curve")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    img = vertical_gradient(BG_TOP, BG_BOT, S).convert("RGBA")
    img.putalpha(rounded_alpha(S, int(0.20 * S)))

    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    d = ImageDraw.Draw(img)

    # 字母几何（归一坐标 → 像素）
    def P(x, y):
        return (int(x * S), int(y * S))

    # Z：上横 → 对角 → 下横（折线）
    z = [P(0.13, 0.33), P(0.43, 0.33), P(0.13, 0.67), P(0.43, 0.67)]
    # F：竖 + 上横 + 中横（右半，与 Z 明确分离，中间留空）
    f_stem = [P(0.57, 0.33), P(0.57, 0.67)]
    f_top = [P(0.57, 0.33), P(0.87, 0.33)]
    f_mid = [P(0.57, 0.50), P(0.78, 0.50)]

    # 先画全部 glow，再整体模糊
    neon_path(gd, d, z, CYAN, CYAN_CORE, W, glow_only=True)
    neon_path(gd, d, f_stem, MAGENTA, MAGENTA_CORE, W, glow_only=True)
    neon_path(gd, d, f_top, MAGENTA, MAGENTA_CORE, W, glow_only=True)
    neon_path(gd, d, f_mid, MAGENTA, MAGENTA_CORE, W, glow_only=True)

    glow = glow.filter(ImageFilter.GaussianBlur(radius=0.020 * S))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=0.009 * S))
    img = Image.alpha_composite(img, glow)
    d = ImageDraw.Draw(img)          # 必须在合成之后重建 Draw（alpha_composite 返回新图）

    # 再画清晰芯线 + 高光（在合成后的图层上）
    neon_path(gd, d, z, CYAN, CYAN_CORE, W)
    neon_path(gd, d, f_stem, MAGENTA, MAGENTA_CORE, W)
    neon_path(gd, d, f_top, MAGENTA, MAGENTA_CORE, W)
    neon_path(gd, d, f_mid, MAGENTA, MAGENTA_CORE, W)

    # 底部密封线（青霓虹短横，象征封存；无细节，缩小后依然干净）
    zip_y = 0.79
    neon_path(gd, d, [P(0.36, zip_y), P(0.64, zip_y)], CYAN, CYAN_CORE, int(W * 0.6))

    # 预览 PNG
    img.save(PNG_PATH)
    # 关于窗口用的 128 位图（Tk 8.6 的 PhotoImage 原生支持 PNG，无需 PIL）
    img.resize((128, 128), Image.LANCZOS).save(PNG128_PATH)

    # 多尺寸对比图（深灰底并排 256/128/64/48/32/16，检查小尺寸可读性）
    probe = [256, 128, 64, 48, 32, 16]
    pad = 18
    tot_w = sum(probe) + pad * (len(probe) + 1)
    maxh = max(probe)
    strip = Image.new("RGB", (tot_w, maxh + pad * 2), (38, 38, 44))
    x = pad
    for s in probe:
        th = img.resize((s, s), Image.LANCZOS)
        strip.paste(th, (x, pad + (maxh - s) // 2), th)
        x += s + pad
    strip.save(SIZES_PATH)
    # 多尺寸 ICO（含 16/32/48/128/256）
    sizes = [(256, 256), (128, 128), (96, 96), (64, 64), (48, 48), (32, 32), (16, 16)]
    img.save(ICO_PATH, format="ICO", sizes=sizes)
    print("written:", ICO_PATH, "|", PNG_PATH)
    print("ico sizes:", sizes)


if __name__ == "__main__":
    main()
