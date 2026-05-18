#!/bin/bash
# 构建后将 Python 代理脚本复制到 .app 包内
# 用法: bash scripts/copy-proxy-to-app.sh
# 需要在 npm run tauri build 之后执行

set -e

APP_PATH="src-tauri/target/release/bundle/macos/Codex-DS 代理.app"

if [ ! -d "$APP_PATH" ]; then
    echo "❌ 找不到应用包: $APP_PATH"
    echo "   请先运行: npm run tauri build"
    exit 1
fi

RESOURCES_DIR="$APP_PATH/Contents/Resources"

echo "📦 复制 Python 代理到应用包..."

# 清空旧的 proxy 目录
rm -rf "$RESOURCES_DIR/proxy"

# 创建目录
mkdir -p "$RESOURCES_DIR/proxy/providers"
mkdir -p "$RESOURCES_DIR/proxy/templates"
mkdir -p "$RESOURCES_DIR/proxy/static/css"
mkdir -p "$RESOURCES_DIR/proxy/static/js"

# 复制所有 Python 脚本
cp proxy/*.py "$RESOURCES_DIR/proxy/"
cp proxy/providers/*.py "$RESOURCES_DIR/proxy/providers/"
cp proxy/templates/* "$RESOURCES_DIR/proxy/templates/"
cp proxy/static/css/* "$RESOURCES_DIR/proxy/static/css/"
cp proxy/static/js/* "$RESOURCES_DIR/proxy/static/js/"
cp proxy/__init__.py "$RESOURCES_DIR/proxy/"

echo "✅ Python 代理已复制到: $RESOURCES_DIR/proxy/"
ls -la "$RESOURCES_DIR/proxy/"
