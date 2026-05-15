.PHONY: setup setup-linux config start start-no-tray stop clean codex-on codex-off

VENV = .venv
PYTHON = $(VENV)/bin/python3
PIP = $(VENV)/bin/pip

# ===== 一键配置环境（macOS）=====
setup: $(VENV)
	@echo "⬆️  升级 pip..."
	$(PIP) install --upgrade pip --quiet 2>/dev/null || true
	@echo "📦 安装依赖..."
	$(PIP) install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn 2>/dev/null || \
	$(PIP) install -r requirements.txt
	@echo "✅ 环境配置完成"
	@echo ""
	@echo "下一步: make start"

# ===== 一键配置环境（Linux）=====
setup-linux: $(VENV)
	@echo "⬆️  升级 pip..."
	$(PIP) install --upgrade pip --quiet 2>/dev/null || true
	@echo "🐧 安装 Linux 依赖（不含 macOS 托盘组件）..."
	$(PIP) install -r requirements-linux.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn 2>/dev/null || \
	$(PIP) install -r requirements-linux.txt
	@echo "✅ Linux 环境配置完成"
	@echo ""
	@echo "下一步: make start"

$(VENV):
	@echo "🐍 创建虚拟环境..."
	python3 -m venv $(VENV)

# ===== 配置 API Key（适合无桌面服务器）=====
config:
	@read -p "🔑 请输入 DeepSeek API Key: " KEY; \
	$(PYTHON) app.py --set-key "$$KEY"

# ===== 启动 =====
start:
	@echo "🚀 启动 Codex DeepSeek Proxy（桌面模式）..."
	$(PYTHON) app.py

start-no-tray:
	@echo "🚀 启动 Codex DeepSeek Proxy（无托盘）..."
	$(PYTHON) app.py --no-tray

# ===== 停止 =====
stop:
	@echo "⏹️  停止代理..."
	@pkill -f "python3.*app.py" 2>/dev/null && echo "✅ 已停止" || echo "⚠️  代理未在运行"

# ===== Codex 一键切代理/还原 =====
codex-on:
	@mkdir -p ~/.codex
	@printf 'model           = "gpt-5.5"\nmodel_provider  = "openai"\nopenai_base_url = "http://127.0.0.1:8787/v1"\n' > ~/.codex/config.toml
	@echo "✅ Codex 已指向本地代理 (DeepSeek)"
	@echo "   ~/.codex/config.toml 已写入"
	@echo ""
	@echo "   ⚠️  还需确保代理在运行: make start"
	@echo "   ⚠️  codex 还需要 API Key 环境变量:"
	@echo "       export OPENAI_API_KEY=deepseek-proxy"

codex-off:
	@rm -f ~/.codex/config.toml
	@echo "✅ 已删除 ~/.codex/config.toml"
	@echo "   Codex 恢复为默认配置（直连 OpenAI）"
	@echo ""
	@echo "   ⚠️  也别忘了清空环境变量:"
	@echo "       unset OPENAI_BASE_URL OPENAI_API_KEY"

# ===== 清理 =====
clean:
	@echo "🧹 清理虚拟环境和缓存..."
	rm -rf $(VENV) __pycache__ .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "✅ 清理完成"
