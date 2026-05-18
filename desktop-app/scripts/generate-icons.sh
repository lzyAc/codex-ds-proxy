#!/bin/bash
# 生成 Tauri 所需的各种图标
# 需要: Python3 + Pillow + ImageMagick

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SRC="$PROJECT_DIR/icon.png"
ICONS_DIR="$PROJECT_DIR/src-tauri/icons"

mkdir -p "$ICONS_DIR"

# 1. 用 Python 生成高清水印图标
echo "🎨 生成源图标..."
python3 "$SCRIPT_DIR/gen_source_icon.py"

# 2. 检查源图标是否存在
if [ ! -f "$SRC" ]; then
  echo "❌ 源图标生成失败"
  exit 1
fi

# 3. macOS 图标
echo "🖼️  生成各个尺寸..."
convert "$SRC" -resize 32x32 "$ICONS_DIR/32x32.png"
convert "$SRC" -resize 128x128 "$ICONS_DIR/128x128.png"
convert "$SRC" -resize 256x256 "$ICONS_DIR/128x128@2x.png"

# 4. 生成 .icns (macOS)
echo "📦 生成 .icns..."
mkdir -p "$ICONS_DIR/icon.iconset"
for size in 16 32 64 128 256 512 1024; do
  convert "$SRC" -resize "${size}x${size}" "$ICONS_DIR/icon.iconset/icon_${size}x${size}.png"
  if [ $size -le 512 ]; then
    size2=$((size * 2))
    convert "$SRC" -resize "${size2}x${size2}" "$ICONS_DIR/icon.iconset/icon_${size}x${size}@2x.png"
  fi
done
iconutil -c icns "$ICONS_DIR/icon.iconset" -o "$ICONS_DIR/icon.icns"
rm -rf "$ICONS_DIR/icon.iconset"

# 5. Windows 图标
echo "📦 生成 .ico..."
convert "$SRC" -resize 256x256 "$ICONS_DIR/icon.ico"

# 6. 源 PNG
echo "📦 生成 icon.png..."
convert "$SRC" -resize 512x512 "$ICONS_DIR/icon.png"

# 7. 清理临时源图
rm -f "$SRC"

echo "✅ 图标已生成到 $ICONS_DIR"
ls -la "$ICONS_DIR/"
