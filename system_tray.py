"""
系统托盘 - macOS 菜单栏应用

使用 rumps 库提供原生 macOS 菜单栏支持：
- 显示代理状态
- 快速启动/停止代理
- 打开管理页面
- 退出应用
"""

import os
import sys
import webbrowser
import threading
from pathlib import Path

try:
    import rumps
    HAS_RUMPS = True
except ImportError:
    HAS_RUMPS = False


class ProxyTrayApp(rumps.App):
    """菜单栏托盘应用"""

    def __init__(self, config: dict, web_port: int, proxy_running_ref, app_path: str):
        super().__init__(
            name="Codex-DS",
            title="🔄",
            quit_button=None,
        )
        self.config = config
        self.web_port = web_port
        self._proxy_running = proxy_running_ref  # 共享的代理状态引用
        self.app_path = app_path

        # 菜单项
        self.status_item = rumps.MenuItem(title=self._status_text())
        self.toggle_item = rumps.MenuItem(
            title=self._toggle_text(),
            callback=self.on_toggle_proxy,
        )
        self.open_ui_item = rumps.MenuItem(
            title="打开管理面板",
            callback=self.on_open_ui,
        )
        self.separator = rumps.separator
        self.quit_item = rumps.MenuItem(
            title="退出",
            callback=self.on_quit,
        )

        self.menu = [
            self.status_item,
            self.toggle_item,
            self.open_ui_item,
            self.separator,
            self.quit_item,
        ]

        # 定时刷新状态（每 3 秒）
        self.timer = rumps.Timer(self._refresh_status, 3)
        self.timer.start()

    def _status_text(self) -> str:
        """生成状态文本"""
        running = bool(self._proxy_running)
        icon = "🟢" if running else "🔴"
        return f"{icon} 代理: {'运行中' if running else '已停止'}"

    def _toggle_text(self) -> str:
        """生成切换按钮文本"""
        return "停止代理" if self._proxy_running else "启动代理"

    def _refresh_status(self, _=None):
        """定时刷新状态"""
        self.status_item.title = self._status_text()
        self.toggle_item.title = self._toggle_text()
        self.title = "🟢" if self._proxy_running else "🔴"

    def on_toggle_proxy(self, _):
        """切换代理启停"""
        if self._proxy_running:
            # 停止代理
            self.stop_proxy()
        else:
            # 启动代理
            self.start_proxy()

    def on_open_ui(self, _):
        """打开管理面板"""
        url = f"http://127.0.0.1:{self.web_port}"
        webbrowser.open(url)

    def on_quit(self, _):
        """退出应用"""
        self.stop_proxy()
        rumps.quit_application()

    def start_proxy(self):
        """启动代理服务器"""
        from proxy import start_proxy, _proxy_running as running, _proxy_start_time

        if running:
            return

        thread = threading.Thread(
            target=lambda: self._start_proxy_in_thread(),
            daemon=True,
        )
        thread.start()

    def _start_proxy_in_thread(self):
        """在新线程中启动代理"""
        from proxy import start_proxy as sp
        host = self.config.get("proxy_host", "127.0.0.1")
        port = self.config.get("proxy_port", 8787)
        sp(host=host, port=port)

    def stop_proxy(self):
        """停止代理服务器"""
        from proxy import stop_proxy
        stop_proxy()

    def cleanup_before_quit(self):
        """退出前清理"""
        self.stop_proxy()
        try:
            self.timer.stop()
        except Exception:
            pass


def has_system_tray_support() -> bool:
    """检查是否支持系统托盘"""
    return HAS_RUMPS and sys.platform == "darwin"


def run_tray(config: dict, web_port: int, proxy_running_ref, app_path: str):
    """启动系统托盘应用（阻塞式）"""
    if not has_system_tray_support():
        print("⚠️  系统托盘仅在 macOS 上可用，将仅启动 Web 界面")
        return

    app = ProxyTrayApp(config, web_port, proxy_running_ref, app_path)
    try:
        app.run()
    except KeyboardInterrupt:
        app.cleanup_before_quit()
