"""
配置管理器 - Codex DeepSeek Proxy 配置存储

配置文件: ~/.codex-ds/config.json
支持多 provider 配置 (DeepSeek / OpenAI / 自定义)
"""

import json
import os
from pathlib import Path

APP_PATH = Path(__file__).parent.absolute()
CONFIG_DIR = Path.home() / ".codex-ds"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "provider": "deepseek",          # 当前使用的 provider ID
    "deepseek_api_key": "",
    "deepseek_base_url": "https://api.deepseek.com",
    "deepseek_model": "deepseek-v4-pro",
    "proxy_host": "127.0.0.1",
    "proxy_port": 8787,
    "auto_start": False,
    "model_mapping": {
        "gpt-4": "deepseek-v4-pro",
        "gpt-4o": "deepseek-v4-pro",
        "gpt-4o-mini": "deepseek-v4-flash",
        "gpt-4-turbo": "deepseek-v4-pro",
        "gpt-3.5-turbo": "deepseek-v4-flash",
        "o1": "deepseek-v4-pro",
        "o1-mini": "deepseek-v4-flash",
        "o3": "deepseek-v4-pro",
        "o3-mini": "deepseek-v4-flash",
        "codex": "deepseek-v4-pro",
        "codex-mini": "deepseek-v4-flash",
        "gpt-5.5": "deepseek-v4-pro",  # Codex 默认模型
        # Claude 模型 → DeepSeek 映射（可自定义）
        "claude-opus-4.6": "deepseek-v4-pro",
        "claude-sonnet-4.6": "deepseek-v4-pro",
        "claude-haiku-4.6": "deepseek-v4-flash",
        "claude-opus-4.7": "deepseek-v4-pro",
        "claude-sonnet-4.7": "deepseek-v4-pro",
        "claude-opus-4.6-1m": "deepseek-v4-pro",
        "claude-sonnet-4.6-1m": "deepseek-v4-pro",
        "claude-haiku-4.6-1m": "deepseek-v4-flash",
        "claude-opus-4.7-1m": "deepseek-v4-pro",
        "claude-sonnet-4.7-1m": "deepseek-v4-pro",
    },
    # 多 provider 配置（可扩展）
    "providers": {
        "deepseek": {
            "name": "DeepSeek",
            "api_key": "",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-v4-pro",
        },
    },
    "available_models": [
        {"id": "deepseek-v4-pro", "name": "DeepSeek V4 Pro", "desc": "旗舰模型，最强推理能力，1M 上下文"},
        {"id": "deepseek-v4-flash", "name": "DeepSeek V4 Flash", "desc": "快速模型，高性价比，1M 上下文"},
        {"id": "deepseek-chat", "name": "DeepSeek Chat (V3)", "desc": "对话模型，通用能力强"},
        {"id": "deepseek-reasoner", "name": "DeepSeek Reasoner (R1)", "desc": "推理模型，擅长数学/编程"},
    ],
}


def ensure_config_dir():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    """加载配置，合并默认值"""
    ensure_config_dir()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
            merged = {**DEFAULT_CONFIG, **config}
            for key in DEFAULT_CONFIG:
                if isinstance(DEFAULT_CONFIG[key], dict) and key in config:
                    merged[key] = {**DEFAULT_CONFIG[key], **config[key]}
            return merged
        except (json.JSONDecodeError, IOError):
            return DEFAULT_CONFIG.copy()
    return DEFAULT_CONFIG.copy()


def save_config(config: dict):
    ensure_config_dir()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def get_env_instructions(config: dict) -> str:
    proxy_port = config.get("proxy_port", 8787)
    lines = [
        "# ===== Codex + DeepSeek 代理配置 =====",
        "# 将此内容添加到 ~/.bashrc 或 ~/.zshrc",
        "",
        f'export OPENAI_BASE_URL="http://127.0.0.1:{proxy_port}/v1"',
        f'export OPENAI_API_KEY="deepseek-proxy"',
        "",
        "# 设置后，运行 codex 命令即可使用 DeepSeek",
        "# ========================================",
    ]
    return "\n".join(lines)
