#!/bin/bash
# ===== Codex DeepSeek Proxy 启动脚本 =====
# 用法：
#   ./start.sh                  # 桌面模式（系统托盘 + 自动打开面板）
#   ./start.sh --no-tray        # 终端模式（无托盘）

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR="$SCRIPT_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python3"
VENV_PIP="$VENV_DIR/bin/pip3"

# 创建虚拟环境（如果不存在）
if [ ! -f "$VENV_PYTHON" ]; then
    echo "🐍 创建 Python 虚拟环境..."
    python3 -m venv "$VENV_DIR"
fi

# 安装/更新依赖
echo "🔍 检查依赖..."
"$VENV_PIP" install -r requirements.txt --quiet 2>/dev/null || {
    echo "📦 首次安装依赖中..."
    "$VENV_PIP" install -r requirements.txt
}

echo ""

# 默认桌面模式（系统托盘）；传参可覆盖
if [ $# -eq 0 ]; then
    echo "🚀 启动 Codex DeepSeek Proxy（桌面模式）..."
else
    echo "🚀 启动 Codex DeepSeek Proxy..."
fi

"$VENV_PYTHON" app.py "$@"
