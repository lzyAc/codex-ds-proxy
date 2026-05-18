.PHONY: setup setup-linux config start start-no-tray stop clean codex-on codex-off claude-on claude-off

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

# ===== Claude 一键切代理/还原 =====
claude-on:
	@echo "✅ Claude 代理配置：在当前终端中执行以下命令"
	@echo ""
	@echo "   export ANTHROPIC_BASE_URL=http://127.0.0.1:8787"
	@echo "   export ANTHROPIC_API_KEY=deepseek-proxy"
	@echo ""
	@echo "   ⚠️  还需确保代理在运行: make start"

claude-off:
	@echo "✅ 还原 Claude 直连：在当前终端中执行以下命令"
	@echo ""
	@echo "   unset ANTHROPIC_BASE_URL ANTHROPIC_API_KEY"

# ===== 清理 =====
clean:
	@echo "🧹 清理虚拟环境和缓存..."
	rm -rf $(VENV) __pycache__ .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "✅ 清理完成"

# ===== 桌面版 Tauri 应用（macOS .app / .dmg）=====

DESKTOP = desktop-app

desktop-setup:
	@echo "📦 安装桌面版依赖..."
	cd $(DESKTOP) && npm install
	@echo "✅ 前端依赖安装完成"
	@echo ""
	@echo "下一步: make desktop-dev  （开发模式，热重载）"
	@echo "   或: make desktop-build  （生产构建，生成 .app）"

desktop-dev:
	@echo "🚀 启动桌面版开发模式..."
	@echo "   窗口打开后按 Cmd+Option+I 打开 DevTools"
	cd $(DESKTOP) && npm run tauri dev

desktop-build:
	@echo "🔨 构建桌面版（需要 macOS + Xcode + Rust）..."
	@echo "   产物路径: $(DESKTOP)/src-tauri/target/release/bundle/"
	@echo "   - macOS: .app（直接拖到 Applications 使用）"
	@echo "   - macOS: .dmg（可分发的安装包）"
	@echo ""
	@echo "   注意: 如果弹出 bundle_dmg.sh 错误，用下面的 desktop-build-app 命令"
	cd $(DESKTOP) && npm run tauri build

desktop-build-app:
	@echo "🔨 构建桌面版（仅 .app，跳过 dmg）..."
	cd $(DESKTOP) && npm run tauri build -- --bundles app
	@echo ""
	@echo "✅ 构建完成！.app 文件:"
	@echo "   $(DESKTOP)/src-tauri/target/release/bundle/macos/Codex-DS 代理.app"
	@echo "   直接拖入 Applications 文件夹使用"

desktop-build-dmg:
	@echo "🔨 构建 macOS .dmg 安装包..."
	cd $(DESKTOP) && npm run tauri build -- --bundles dmg

desktop-clean:
	@echo "🧹 清理桌面版构建缓存..."
	cd $(DESKTOP) && rm -rf src-tauri/target node_modules dist
	@echo "✅ 清理完成"

desktop-icons:
	@echo "🖼️  生成应用图标..."
	cd $(DESKTOP)/scripts && bash generate-icons.sh

# ===== 快捷命令 =====
clean-all: clean desktop-clean
	@echo "🧹 已清理所有构建产物"
