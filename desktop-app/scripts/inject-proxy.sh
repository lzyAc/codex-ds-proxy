#!/bin/bash
# 构建后将 proxy/ 注入到 .app/Contents/Resources/
# 在 tauri.conf.json 的 afterBuildCommand 中调用

set -e

APP_BUNDLE="src-tauri/target/release/bundle/macos/Codex-DS 代理.app"
RES_DIR="$APP_BUNDLE/Contents/Resources/proxy"

if [ ! -d "$APP_BUNDLE" ]; then
    echo "⚠️  未找到 .app 包，跳过 proxy 注入"
    exit 0
fi

echo "📦 注入 Python 代理到 .app 包..."
rm -rf "$RES_DIR"
mkdir -p "$RES_DIR/providers"
mkdir -p "$RES_DIR/templates"
mkdir -p "$RES_DIR/static/css"
mkdir -p "$RES_DIR/static/js"

cp proxy/*.py "$RES_DIR/"
cp proxy/providers/*.py "$RES_DIR/providers/"
cp proxy/templates/* "$RES_DIR/templates/"
cp proxy/static/css/* "$RES_DIR/static/css/"
cp proxy/static/js/* "$RES_DIR/static/js/"
cp proxy/__init__.py "$RES_DIR/"

echo "✅ Python 代理已注入: $RES_DIR"
ls "$RES_DIR/"*.py 2>/dev/null
