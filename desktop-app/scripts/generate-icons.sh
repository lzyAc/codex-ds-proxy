#!/bin/bash
# 生成 Tauri 所需的各种图标
# 需要安装: brew install imagemagick librsvg
# 源文件: icon.png (1024x1024 PNG)

set -e

SRC="icon.png"
ICONS_DIR="../src-tauri/icons"

if [ ! -f "$SRC" ]; then
  echo "请准备 1024x1024 的 icon.png 作为源文件"
  echo "可使用项目中已有的 icon.png"
  exit 1
fi

mkdir -p "$ICONS_DIR"

# macOS 图标
convert "$SRC" -resize 32x32 "$ICONS_DIR/32x32.png"
convert "$SRC" -resize 128x128 "$ICONS_DIR/128x128.png"
convert "$SRC" -resize 256x256 "$ICONS_DIR/128x128@2x.png"

# 生成 .icns (macOS)
mkdir -p icon.iconset
for size in 16 32 64 128 256 512 1024; do
  convert "$SRC" -resize "${size}x${size}" "icon.iconset/icon_${size}x${size}.png"
  if [ $size -le 512 ]; then
    size2=$((size * 2))
    convert "$SRC" -resize "${size2}x${size2}" "icon.iconset/icon_${size}x${size}@2x.png"
  fi
done
iconutil -c icns icon.iconset -o "$ICONS_DIR/icon.icns"
rm -rf icon.iconset

# Windows 图标
convert "$SRC" -resize 256x256 "$ICONS_DIR/icon.ico"

# 源 PNG
convert "$SRC" -resize 512x512 "$ICONS_DIR/icon.png"

echo "✅ 图标已生成到 $ICONS_DIR"
ls -la "$ICONS_DIR/"
