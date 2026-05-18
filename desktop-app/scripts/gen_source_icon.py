"""
生成 1024x1024 应用图标
简洁高级风格：渐变圆形 + "Proxy" 字标

依赖: pip install Pillow
"""

import math
import os

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
except ImportError:
    print("请先安装 Pillow: pip install Pillow")
    exit(1)

SIZE = 1024
OUTPUT = os.path.join(os.path.dirname(__file__), "..", "icon.png")


def find_font(size):
    """按优先级找系统字体"""
    paths = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNSDisplay.ttf",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    ]
    for fp in paths:
        try:
            return ImageFont.truetype(fp, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


def draw_gradient_ellipse(draw, cx, cy, r, color1, color2):
    """画渐变圆：从 color1（中心）到 color2（边缘）"""
    for i in range(r, 0, -1):
        t = i / r  # 1 = 内圈, 0 = 外圈
        rr = int(color1[0] + (color2[0] - color1[0]) * (1 - t))
        gg = int(color1[1] + (color2[1] - color1[1]) * (1 - t))
        bb = int(color1[2] + (color2[2] - color1[2]) * (1 - t))
        aa = int(220 + (255 - 220) * t)
        draw.ellipse([cx - i, cy - i, cx + i, cy + i], fill=(rr, gg, bb, aa))


def main():
    # 1. 创建透明底图
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = SIZE // 2, SIZE // 2

    # 2. 主渐变圆（品牌紫-蓝渐变）
    draw_gradient_ellipse(draw, cx, cy, 460,
                          (99, 102, 241),   # #6366F1 indigo-500
                          (37, 99, 235))     # #2563EB blue-600
    # 外围光晕
    draw_gradient_ellipse(draw, cx, cy, 490,
                          (139, 92, 246),    # #8B5CF6 violet-500
                          (79, 70, 229))     # #4F46E5 indigo-600

    # 3. 内部磨砂玻璃卡片
    cm = 190  # card margin
    cr = 72   # corner radius
    draw.rounded_rectangle(
        [cm, cm, SIZE - cm, SIZE - cm],
        radius=cr,
        fill=(255, 255, 255, 230),
    )

    # 4. 绘制 "Proxy" 文字（多层叠加做出高级感）
    text = "Proxy"
    fs_main = 168

    font_main = find_font(fs_main)
    bbox = draw.textbbox((0, 0), text, font=font_main)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx = (SIZE - tw) // 2
    ty = (SIZE - th) // 2 - 20

    # 底部阴影
    draw.text((tx + 4, ty + 4), text,
              fill=(0, 0, 0, 30), font=font_main)

    # 主体文字（深色）
    draw.text((tx, ty), text,
              fill=(30, 30, 50, 235), font=font_main)

    # 细高光（顶部薄层）
    draw.text((tx, ty - 2), text,
              fill=(255, 255, 255, 60), font=font_main)

    # 5. 子标签 "DeepSeek"
    sub = "DeepSeek"
    fs_sub = 52
    font_sub = find_font(fs_sub)
    sbbox = draw.textbbox((0, 0), sub, font=font_sub)
    stw, sth = sbbox[2] - sbbox[0], sbbox[3] - sbbox[1]
    stx = (SIZE - stw) // 2
    sty = ty + th + 36

    # 标签背景
    label_pad = 28
    draw.rounded_rectangle(
        [stx - label_pad, sty - 10, stx + stw + label_pad, sty + sth + 10],
        radius=18,
        fill=(99, 102, 241, 40),
    )

    draw.text((stx, sty), sub,
              fill=(79, 70, 229, 180), font=font_sub)

    # 6. 保存
    img.save(OUTPUT, "PNG")
    print(f"✅ 图标已生成: {OUTPUT}")
    print(f"   尺寸: {SIZE}x{SIZE}")
    print(f"   大小: {os.path.getsize(OUTPUT) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
