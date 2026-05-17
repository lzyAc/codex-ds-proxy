#!/bin/bash
# ===== Docker 入口脚本 =====
# 将环境变量同步到 config.json，然后启动代理

set -e

CONFIG_DIR="$HOME/.codex-ds"
CONFIG_FILE="$CONFIG_DIR/config.json"

# 确保配置目录存在
mkdir -p "$CONFIG_DIR"

# 从环境变量构建配置
if [ ! -f "$CONFIG_FILE" ]; then
    echo '{}' > "$CONFIG_FILE"
fi

# 环境变量 → config.json 同步（仅当环境变量有值时覆盖）
if [ -n "$DEEPSEEK_API_KEY" ]; then
    python3 -c "
import json
with open('$CONFIG_FILE') as f:
    cfg = json.load(f)
cfg['deepseek_api_key'] = '$DEEPSEEK_API_KEY'
with open('$CONFIG_FILE', 'w') as f:
    json.dump(cfg, f, indent=2)
" 2>/dev/null || true
fi

if [ -n "$DEEPSEEK_BASE_URL" ]; then
    python3 -c "
import json
with open('$CONFIG_FILE') as f:
    cfg = json.load(f)
cfg['deepseek_base_url'] = '$DEEPSEEK_BASE_URL'
with open('$CONFIG_FILE', 'w') as f:
    json.dump(cfg, f, indent=2)
" 2>/dev/null || true
fi

if [ -n "$DEEPSEEK_MODEL" ]; then
    python3 -c "
import json
with open('$CONFIG_FILE') as f:
    cfg = json.load(f)
cfg['deepseek_model'] = '$DEEPSEEK_MODEL'
with open('$CONFIG_FILE', 'w') as f:
    json.dump(cfg, f, indent=2)
" 2>/dev/null || true
fi

# 显示配置状态
echo "🔧 Codex DeepSeek Proxy — Docker"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
KEY_SHOW="${DEEPSEEK_API_KEY:0:8}...${DEEPSEEK_API_KEY: -4}"
echo "  API Key:      ${DEEPSEEK_API_KEY:+$KEY_SHOW}${DEEPSEEK_API_KEY:-未配置}"
echo "  Base URL:     $DEEPSEEK_BASE_URL"
echo "  默认模型:     $DEEPSEEK_MODEL"
echo "  代理端口:     ${PROXY_PORT:-8787}"
echo "  Web UI 端口:  ${WEB_PORT:-8788}"
echo ""

# 启动代理（--no-tray 确保在 Docker 中不会尝试 macOS 托盘）
exec python3 /app/app.py --no-tray --proxy-port "${PROXY_PORT:-8787}" --port "${WEB_PORT:-8788}"
