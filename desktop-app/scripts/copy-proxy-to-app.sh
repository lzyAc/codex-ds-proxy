#!/bin/bash
# 构建后将 Python 代理脚本复制到 .app 包内
# 这样应用打开后就能直接从包内找到 app.py

set -e

APP_PATH="src-tauri/target/release/bundle/macos/Codex-DS 代理.app"

if [ ! -d "$APP_PATH" ]; then
    echo "❌ 找不到应用包: $APP_PATH"
    echo "   请先运行: npm run tauri build"
    exit 1
fi

RESOURCES_DIR="$APP_PATH/Contents/Resources/proxy"

echo "📦 复制 Python 代理到应用包..."
mkdir -p "$RESOURCES_DIR/providers"
mkdir -p "$RESOURCES_DIR/templates"
mkdir -p "$RESOURCES_DIR/static/css"
mkdir -p "$RESOURCES_DIR/static/js"

cp proxy/*.py "$RESOURCES_DIR/"
cp proxy/providers/*.py "$RESOURCES_DIR/providers/"
cp proxy/templates/* "$RESOURCES_DIR/templates/"
cp proxy/static/css/* "$RESOURCES_DIR/static/css/"
cp proxy/static/js/* "$RESOURCES_DIR/static/js/"
cp proxy/__init__.py "$RESOURCES_DIR/"

echo "✅ Python 代理已复制到应用包: $RESOURCES_DIR"
ls -la "$RESOURCES_DIR/"
