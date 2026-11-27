# -*- coding: utf-8 -*-
"""用 Pillow 绘制程序图标（不依赖任何 GUI/浏览器）。
设计：深绿黑圆角玻璃底 + 荧光绿"扫过"弧线 + 三颗闪星，输出多尺寸 PNG 和 .ico。"""
import math
import os

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "assets")
S = 1024  # 绘制基准，最后缩小到各尺寸
SIZES = [16, 24, 32, 48, 64, 128, 256, 512]


def lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def gradient(size, c1, c2, horizontal=False):
    """双色线性渐变（纯 PIL，无需 numpy）。"""
    w, h = size
    strip = Image.new("RGB", (w, 1) if not horizontal else (1, h))
    px = strip.load()
    n = (w if not horizontal else h) - 1
    for i in range(n + 1):
        c = lerp(c1, c2, i / max(n, 1))
        if horizontal:
            px[0, i] = c
        else:
            px[i, 0] = c
    return strip.resize(size, Image.BICUBIC)


def rounded_mask(size, radius, box=None):
    m = Image.new("L", size, 0)
    d = ImageDraw.Draw(m)
    d.rounded_rectangle(box or (0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return m


def sparkle(size, inner_ratio=0.24):
    """四芒星，用 16 边形近似凹边。"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = cy = size / 2
    R = size / 2 * 0.98
    r = R * inner_ratio
    pts = []
    for i in range(16):
        ang = math.pi / 8 * i - math.pi / 2
        rad = R if i % 4 == 0 else r
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    d.polygon(pts, fill=(240, 255, 200, 255))
    return img


def main():
    os.makedirs(OUT, exist_ok=True)
    pad = 32
    tile_box = (pad, pad, S - pad, S - pad)
    radius = 240

    # 底：深绿黑渐变圆角玻璃
    base = gradient((S, S), (29, 40, 18), (11, 14, 8)).convert("RGBA")
    mask = rounded_mask((S, S), radius, tile_box)
    canvas = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    canvas.paste(base, (0, 0), mask)

    # 内部径向光晕
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((120, 300, 760, 900), fill=(200, 255, 77, 70))
    glow = glow.filter(ImageFilter.GaussianBlur(90))
    canvas = Image.alpha_composite(canvas, Image.composite(glow, Image.new("RGBA", (S, S)), mask))

    # 扫过弧线：两层（外发光 + 主弧），端点用圆头
    arc_layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ad = ImageDraw.Draw(arc_layer)
    bbox = (256, 280, 1012, 1036)
    ad.arc(bbox, start=180, end=270, fill=(200, 255, 77, 255), width=92)
    for ang in (180, 270):
        x = (bbox[0] + bbox[2]) / 2 + (bbox[2] - bbox[0]) / 2 * math.cos(math.radians(ang))
        y = (bbox[1] + bbox[3]) / 2 + (bbox[3] - bbox[1]) / 2 * math.sin(math.radians(ang))
        ad.ellipse((x - 46, y - 46, x + 46, y + 46), fill=(200, 255, 77, 255))
    # 让弧线沿对角线有明暗变化
    diag = gradient((S, S), (127, 212, 38), (240, 255, 192), horizontal=True).convert("RGBA")
    diag.putalpha(arc_layer.split()[3])
    halo = arc_layer.filter(ImageFilter.GaussianBlur(26))
    canvas = Image.alpha_composite(canvas, Image.composite(halo, Image.new("RGBA", (S, S)), mask))
    canvas = Image.alpha_composite(canvas, Image.composite(diag, Image.new("RGBA", (S, S)), mask))

    # 细一点的高光弧
    thin = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    td = ImageDraw.Draw(thin)
    td.arc((300, 330, 990, 1020), start=182, end=266, fill=(234, 255, 171, 150), width=22)
    canvas = Image.alpha_composite(canvas, Image.composite(thin, Image.new("RGBA", (S, S)), mask))

    # 三颗闪星
    for size, pos in ((210, (640, 560)), (120, (440, 760)), (96, (760, 380))):
        star = sparkle(size)
        canvas.alpha_composite(star, pos)

    # 顶部玻璃高光
    sheen = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sheen)
    sd.pieslice((-200, -700, 1224, 420), start=0, end=180, fill=(255, 255, 255, 16))
    canvas = Image.alpha_composite(canvas, Image.composite(sheen, Image.new("RGBA", (S, S)), mask))

    # 边缘描边
    edge = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ed = ImageDraw.Draw(edge)
    ed.rounded_rectangle(tile_box, radius=radius, outline=(214, 255, 140, 120), width=6)
    canvas = Image.alpha_composite(canvas, edge)

    # 输出
    canvas.save(os.path.join(OUT, "icon-1024.png"))
    for s in SIZES:
        canvas.resize((s, s), Image.LANCZOS).save(os.path.join(OUT, f"icon-{s}.png"))
    canvas.save(os.path.join(OUT, "icon.ico"), sizes=[(s, s) for s in [16, 24, 32, 48, 64, 128, 256]])
    canvas.resize((256, 256), Image.LANCZOS).save(os.path.join(OUT, "icon.png"))
    print("ICO sizes:", Image.open(os.path.join(OUT, "icon.ico")).ico.sizes())
    print("done:", sorted(os.listdir(OUT)))


if __name__ == "__main__":
    main()
