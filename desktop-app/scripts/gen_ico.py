"""
用 Pillow 生成 Windows .ico 和 macOS .icns 图标

用法:
  python3 gen_ico.py

依赖: pip install Pillow

对于 macOS .icns:
  - 如果系统有 iconutil 命令，会自动用它生成 .icns
  - 否则生成一个 .iconset 文件夹供你手动转换
"""

import os
import subprocess
import sys

try:
    from PIL import Image
except ImportError:
    print("请先安装 Pillow: pip install Pillow")
    sys.exit(1)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.join(BASE_DIR, "..")
ICONS_DIR = os.path.join(PROJECT_DIR, "src-tauri", "icons")


def main():
    # 1. 生成 .ico（Windows）
    print("📦 生成 icon.ico...")
    png_path = os.path.join(ICONS_DIR, "256x256.png")
    if not os.path.exists(png_path):
        png_path = os.path.join(ICONS_DIR, "128x128.png")
    if not os.path.exists(png_path):
        print("❌ 找不到源 PNG 文件，请先运行 gen_source_icon.py")
        return

    img = Image.open(png_path)
    ico_path = os.path.join(ICONS_DIR, "icon.ico")
    # ICO 可以包含多个尺寸，Pillow 自动处理
    img.save(ico_path, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"✅ icon.ico 已生成: {ico_path}")

    # 2. 生成 .icns（macOS）
    print("\n📦 生成 icon.icns...")
    iconset_path = os.path.join(ICONS_DIR, "icon.iconset")
    if not os.path.exists(iconset_path):
        print(f"❌ 找不到 {iconset_path}，请先运行 generate-icons.sh")
        return

    # 尝试用 iconutil（macOS 原生工具）
    try:
        result = subprocess.run(
            ["iconutil", "-c", "icns", iconset_path, "-o", os.path.join(ICONS_DIR, "icon.icns")],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            print(f"✅ icon.icns 已生成（使用 iconutil）")
        else:
            print(f"⚠️  iconutil 失败: {result.stderr}")
            print("   请手动执行: iconutil -c icns icon.iconset -o icon.icns")
    except FileNotFoundError:
        print("⚠️  系统没有 iconutil 命令（非 macOS 环境）")
        print("   在 macOS 上执行: cd src-tauri/icons && iconutil -c icns icon.iconset -o icon.icns")
    except Exception as e:
        print(f"⚠️  生成失败: {e}")
        print("   请手动执行: iconutil -c icns icon.iconset -o icon.icns")

    # 3. 检查结果
    print("")
    icons_dir = ICONS_DIR
    for f in os.listdir(icons_dir):
        fpath = os.path.join(icons_dir, f)
        if os.path.isfile(fpath) and not f.endswith(".png") and not os.path.isdir(fpath):
            size = os.path.getsize(fpath)
            print(f"   {f}: {size / 1024:.1f} KB")

    print("\n✅ 图标生成完成")


if __name__ == "__main__":
    main()
