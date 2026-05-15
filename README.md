# Codex DeepSeek Proxy

让 OpenAI Codex CLI 通过本地代理无缝接入 DeepSeek，享受高性价比的 AI 编程体验。

macOS 原生支持：菜单栏托盘，一键启动。

## 环境要求

| 项目 | 要求 | 说明 |
|------|------|------|
| 操作系统 | **macOS 11.0+ / Linux** | macOS 有系统托盘；Linux 自动使用终端模式 |
| Python | **3.9 ~ 3.12** | `python3 --version` 确认 |
| Codex CLI | **v0.80.0+** | `brew install codex` 或从 openai/codex 仓库安装 |
| DeepSeek API Key | 必需 | [platform.deepseek.com/api_keys](https://platform.deepseek.com/api_keys) 注册获取（需充值） |
| 网络 | 能访问 `api.deepseek.com` | 国内直连通常没问题 |
| 磁盘空间 | ~100MB（macOS）/ ~50MB（Linux） | 虚拟环境 + 依赖 |

**不支持的环境：**

- **Windows**：未适配，但可以通过 WSL2 在 Linux 模式下运行。
- **Python 3.13+**：macOS 依赖 `pyobjc-core==10.3.1` 暂无预编译 wheel。

## 快速开始

### macOS

```bash
cd ~/codex-ds
make setup    # 一键创建虚拟环境 + 安装依赖
make start    # 启动（系统托盘 + 自动打开管理面板）
```

### Linux

```bash
cd ~/codex-ds
make setup-linux    # 安装依赖（不含 macOS 托盘组件）
make start          # 启动（自动使用终端模式）
```

程序会自动检测系统为 Linux，跳过托盘功能，直接以终端模式运行。

### 无桌面服务器配置 Key

如果服务器没有浏览器，用命令行配置：

```bash
make config            # 交互式输入 Key
# 或直接：
python3 app.py --set-key YOUR_DEEPSEEK_API_KEY
```

配好后再 `make start` 启动代理。Proxy 启动后会自动识别已配置的 Key，无需再操作 Web 面板。

然后用 Codex：

```bash
export OPENAI_API_KEY=deepseek-proxy
codex "用 python 输出 hello world"
```

## 使用说明

### 第一步：获取 DeepSeek API Key

访问 [platform.deepseek.com/api_keys](https://platform.deepseek.com/api_keys) 创建 Key（需充值，价格远低于 OpenAI）。

### 第二步：启动代理

```bash
make start            # 桌面模式：系统托盘 + 自动打开浏览器
make start-no-tray    # 终端模式：不启动托盘
```

管理面板默认在 `http://127.0.0.1:8788`，代理监听 `http://127.0.0.1:8787`。

菜单栏托盘功能：查看代理状态、打开面板、一键复制终端配置、退出。

### 第三步：配置

在管理面板「配置」页：
- 填入 DeepSeek API Key
- 选择默认模型（推荐 `deepseek-v4-pro`）
- 点击「测试连接」验证
- 点击「保存配置」

### 第四步：配置 Codex

创建 `~/.codex/config.toml`：

```toml
model           = "gpt-5.5"
model_provider  = "openai"
openai_base_url = "http://127.0.0.1:8787/v1"
```

### 第五步：使用

```bash
export OPENAI_API_KEY=deepseek-proxy
codex "你的问题"
```

代理会自动将 `gpt-5.5` 映射为 `deepseek-v4-pro`，所有 API 请求转发至 DeepSeek。

## Make 命令

| 命令 | 说明 |
|------|------|
| `make setup` | 创建虚拟环境 + 安装依赖（macOS） |
| `make setup-linux` | 创建虚拟环境 + 安装依赖（Linux，无托盘组件） |
| `make config` | 命令行配置 API Key（适合无桌面服务器） |
| `make start` | 启动代理（系统托盘 + 自动打开面板） |
| `make start-no-tray` | 启动代理（无托盘，终端模式） |
| `make stop` | 停止代理 |
| `make clean` | 清理虚拟环境和缓存 |

## 功能特性

- **系统托盘**：macOS 菜单栏图标，查看状态、打开面板、复制配置、退出
- **零配置代理**：拦截 Codex 的 OpenAI API 请求，自动转发至 DeepSeek
- **WebSocket 支持**：完整支持 Codex 的 Responses API（WebSocket 协议）
- **SSE 流式转发**：实时转发 DeepSeek 的流式响应
- **模型映射**：自动将 `gpt-5.5`、`gpt-4`、`o3` 等 OpenAI 模型名映射为 DeepSeek 模型
- **工具调用**：支持 Codex 的 function_call 工具（写文件、执行命令等）
- **多轮对话**：处理 Codex 的多轮工具调用循环
- **思考模式**：首轮对话启用 DeepSeek V4 Thinking Mode，发挥最强推理能力
- **开机自启**：macOS LaunchAgent 支持（管理面板中勾选）
- **实时日志**：管理面板查看每次请求的耗时、Token 消耗
- **深色主题**：类 IDE 风格的管理界面
- **多模型可扩展**：Provider 抽象层，轻松接入其他厂商

## 管理面板

访问 `http://127.0.0.1:8788` 可使用以下功能：

| 页面 | 功能 |
|------|------|
| 仪表盘 | 代理状态、请求统计、运行时长 |
| 配置 | API Key、Base URL、默认模型、Provider 选择 |
| 模型映射 | 自定义 OpenAI → DeepSeek 模型名映射 |
| 请求日志 | 实时查看每次请求的转发情况 |
| 环境变量 | 一键复制/清空终端配置命令 |

## 多模型支持（Provider 架构）

代理内置 Provider 抽象层，可轻松接入其他模型厂商。当前已内置：

| Provider | 模型 | 说明 |
|----------|------|------|
| `deepseek` | deepseek-v4-pro, deepseek-chat 等 | 默认 provider |

### 添加自定义 Provider

在 `providers/` 目录下新建文件，继承 `BaseProvider` 并注册即可：

```python
# providers/my_provider.py
from providers.base import BaseProvider
from providers import register_provider

class MyProvider(BaseProvider):
    meta = {"name": "my_provider", "description": "My custom LLM provider",
            "models": ["my-model-v1"]}

    def get_api_key(self):           return self.config.get("my_api_key", "")
    def build_url(self, path):       return f"https://api.my-provider.com/{path}"
    def map_model(self, model):      return model.replace("gpt-5.5", "my-model-v1")

    async def chat_completion(self, body):    ...  # 同步请求
    async def stream_chat_completion(self, body): ...  # SSE 流式请求

register_provider("my_provider", MyProvider)
```

需要实现的方法：
- `chat_completion()` — 非流式 Chat Completions 请求
- `stream_chat_completion()` — 流式请求，yield SSE 事件 dict，最后 yield `{"_done": True}`
- 可选覆写：`map_model()`, `get_api_key()`, `get_headers()`, `build_url()`, `convert_tools()`, `convert_tool_choice()`

然后在管理面板中将 `provider` 字段改为 `my_provider` 即可切换。

## 技术架构

### 整体方案

```
Codex CLI (TUI)
    │  WebSocket (ws://127.0.0.1:8787/v1/responses)
    │  Responses API 格式
    ▼
┌─────────────────────────────────┐
│       Codex DeepSeek Proxy      │
│                                 │
│  ┌───────────────────────────┐  │
│  │   Responses → Chat 转换    │  │
│  │   · 格式翻译              │  │
│  │   · 模型名映射            │  │
│  │   · 工具格式适配          │  │
│  └───────────┬───────────────┘  │
│              │                  │
│  ┌───────────▼───────────────┐  │
│  │   Provider 抽象层         │  │
│  │   · DeepSeekProvider      │  │
│  │   · 可扩展 MyProvider     │  │
│  └───────────────────────────┘  │
│                                 │
│  ┌───────────────────────────┐  │
│  │   系统托盘 (rumps)        │  │
│  │   · 状态监控              │  │
│  │   · 一键复制配置          │  │
│  └───────────────────────────┘  │
│                                 │
│  ┌───────────────────────────┐  │
│  │   Web 管理面板 (Tornado)  │  │
│  │   · 配置管理              │  │
│  │   · 实时日志              │  │
│  │   · 状态 API              │  │
│  └───────────────────────────┘  │
└─────────────────────────────────┘
    │  HTTP POST (SSE Streaming)
    │  Chat Completions API 格式
    ▼
LLM API (DeepSeek / 其他 Provider)
```

### 核心组件

| 文件 | 职责 |
|------|------|
| `app.py` | 主入口：代理启停、系统托盘、Web UI 调度 |
| `proxy.py` | 代理核心：WebSocket 处理、SSE 解析、协议转换 |
| `web_ui.py` | 管理面板 API（配置、日志、状态） |
| `config_manager.py` | 配置文件读写（`~/.codex-ds/config.json`） |
| `autostart.py` | macOS LaunchAgent 开机自启 |
| `providers/` | Provider 抽象层：支持多模型厂商扩展 |

### 协议转换细节

Codex 使用 OpenAI Responses API（WebSocket 协议），而 DeepSeek 仅支持 Chat Completions API（HTTP SSE）。代理在两者之间做双向转换：

**请求方向**（Codex → DeepSeek）：
1. WebSocket 接收 Responses API 格式消息
2. 解析 `input` 数组为 Chat `messages` 列表
3. 处理 `function_call` / `function_call_output` 项的对话历史重建
4. 过滤 DeepSeek 不支持的工具类型（web_search 等）
5. 修正工具 JSON Schema（确保 `type: "object"`）
6. 转发为 HTTP POST + SSE Streaming

**响应方向**（DeepSeek → Codex）：
1. 接收 DeepSeek 的 SSE 流式响应
2. 解析 `delta.content` 和 `delta.reasoning_content`
3. 转换为 Responses API WebSocket 事件序列：
   - `response.created` → `response.in_progress`
   - `response.output_item.added` → `response.content_part.added`
   - `response.output_text.delta`（流式文本）
   - `response.function_call_arguments.delta`（流式工具参数）
   - `response.*.done` → `response.output_item.done`
   - `response.completed`

### 技术栈

| 层级 | 技术 |
|------|------|
| 语言 | Python 3.9+ |
| Web 框架 | Tornado 6.x（异步 HTTP + WebSocket） |
| HTTP 客户端 | tornado.httpclient（异步） |
| HTTP 同步 | requests（管理面板用） |
| 前端 | 原生 HTML/CSS/JS（无框架，零依赖） |
| 系统集成 | rumps（菜单栏托盘）、macOS LaunchAgent |
| 配置存储 | JSON 文件（`~/.codex-ds/config.json`） |

### 设计决策

**为什么用 rumps 而不是 Electron/pywebview？**
rumps 是纯 Python 的 macOS 菜单栏库，依赖轻量（仅需 pyobjc-core，预编译 wheel 直接安装）。相比 Electron（~200MB）和 pywebview（需编译 pyobjc 全家桶），rumps 零编译开销，安装即用，且菜单栏托盘是 macOS 用户最熟悉的"后台服务"交互模式。

**为什么用 Tornado 而不是 Flask？**
Tornado 原生支持异步 HTTP 和 WebSocket，无需额外依赖。代理需要同时处理 WebSocket 连接和 HTTP 请求，Tornado 的单线程事件循环模型天然适合这个场景。

**为什么关闭多轮思考模式？**
DeepSeek V4 的 Thinking Mode 要求在多轮对话中将 `reasoning_content` 传回 API。由于 Codex 每轮都开启新的 WebSocket 连接，代理无法在连接间保持推理内容。因此首轮对话启用思考模式发挥推理能力，后续工具调用轮次关闭以避免错误。

**为什么不用 Codex 降级方案？**
Codex v0.80.0 支持 `wire_api = "chat"`（纯 HTTP），但功能受限且版本老旧。通过 WebSocket 代理支持最新版 Codex，可获得完整功能和最新模型支持。

## License

MIT
