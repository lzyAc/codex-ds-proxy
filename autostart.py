"""
开机自启管理 - macOS LaunchAgent / Linux systemd 用户服务

支持：
- 安装/卸载自启
- 查询自启状态
"""

import os
import sys
import plistlib
from pathlib import Path


APP_NAME = "com.codex-ds.proxy"
APP_DISPLAY_NAME = "Codex DeepSeek Proxy"

# macOS LaunchAgent 路径
LAUNCH_AGENT_DIR = Path.home() / "Library" / "LaunchAgents"
LAUNCH_AGENT_FILE = LAUNCH_AGENT_DIR / f"{APP_NAME}.plist"


def _get_launch_agent_content(app_path: str, python_path: str) -> dict:
    """生成 macOS LaunchAgent plist 内容"""
    return {
        "Label": APP_NAME,
        "ProgramArguments": [
            python_path,
            os.path.join(app_path, "app.py"),
            "--no-tray",
        ],
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": os.path.join(app_path, "logs", "stdout.log"),
        "StandardErrorPath": os.path.join(app_path, "logs", "stderr.log"),
        "EnvironmentVariables": {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        },
        "ProcessType": "Background",
        "Nice": 5,
    }


def is_auto_start_enabled() -> bool:
    """检查是否已设置开机自启"""
    if sys.platform == "darwin":
        return LAUNCH_AGENT_FILE.exists()
    # Linux: 暂不支持 systemd 自动检测
    return False


def enable_auto_start(app_path: str) -> tuple[bool, str]:
    """启用开机自启"""
    if sys.platform == "darwin":
        return _enable_macos(app_path)
    elif sys.platform == "linux":
        return _enable_linux(app_path)
    else:
        return False, "当前操作系统不支持开机自启"


def disable_auto_start() -> tuple[bool, str]:
    """禁用开机自启"""
    if sys.platform == "darwin":
        return _disable_macos()
    elif sys.platform == "linux":
        return _disable_linux()
    else:
        return False, "当前操作系统不支持开机自启"


def _enable_macos(app_path: str) -> tuple[bool, str]:
    """macOS: 创建 LaunchAgent"""
    try:
        LAUNCH_AGENT_DIR.mkdir(parents=True, exist_ok=True)
        logs_dir = Path(app_path) / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        python_path = sys.executable
        plist_content = _get_launch_agent_content(app_path, python_path)

        with open(LAUNCH_AGENT_FILE, "wb") as f:
            plistlib.dump(plist_content, f)

        # 加载 LaunchAgent
        os.system(f"launchctl load {LAUNCH_AGENT_FILE}")

        return True, f"已启用开机自启 ({LAUNCH_AGENT_FILE})"
    except Exception as e:
        return False, f"启用失败: {e}"


def _disable_macos() -> tuple[bool, str]:
    """macOS: 移除 LaunchAgent"""
    try:
        if LAUNCH_AGENT_FILE.exists():
            os.system(f"launchctl unload {LAUNCH_AGENT_FILE}")
            LAUNCH_AGENT_FILE.unlink()
            return True, "已禁用开机自启"
        return True, "开机自启未启用"
    except Exception as e:
        return False, f"禁用失败: {e}"


def _enable_linux(app_path: str) -> tuple[bool, str]:
    """Linux: 创建 systemd 用户服务"""
    try:
        systemd_dir = Path.home() / ".config" / "systemd" / "user"
        systemd_dir.mkdir(parents=True, exist_ok=True)

        logs_dir = Path(app_path) / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        python_path = sys.executable
        service_content = f"""[Unit]
Description={APP_DISPLAY_NAME}
After=network.target

[Service]
Type=simple
ExecStart={python_path} {os.path.join(app_path, 'app.py')} --no-tray
Restart=always
RestartSec=10
StandardOutput=append:{logs_dir}/stdout.log
StandardError=append:{logs_dir}/stderr.log

[Install]
WantedBy=default.target
"""
        service_file = systemd_dir / f"{APP_NAME}.service"
        with open(service_file, "w") as f:
            f.write(service_content)

        os.system(f"systemctl --user daemon-reload")
        os.system(f"systemctl --user enable {APP_NAME}.service")
        os.system(f"systemctl --user start {APP_NAME}.service")

        return True, f"已启用开机自启 ({service_file})"
    except Exception as e:
        return False, f"启用失败: {e}"


def _disable_linux() -> tuple[bool, str]:
    """Linux: 禁用 systemd 用户服务"""
    try:
        os.system(f"systemctl --user stop {APP_NAME}.service")
        os.system(f"systemctl --user disable {APP_NAME}.service")
        return True, "已禁用开机自启"
    except Exception as e:
        return False, f"禁用失败: {e}"
