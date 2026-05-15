#!/usr/bin/env python3
"""
Codex DeepSeek Proxy - 桌面应用程序入口

功能：
- 本地代理服务器：拦截 Codex CLI 的 API 请求，转发至 DeepSeek
- 系统托盘：macOS 菜单栏快捷控制（启动/停止/打开面板/退出）
- Web 管理面板：配置 API Key、模型选择、查看日志
- macOS .app 打包：可生成原生应用包放入 /Applications
- 开机自启：可选的一键设置

用法：
    python app.py                  # 桌面模式（系统托盘 + 自动打开浏览器）
    python app.py --no-tray        # 无托盘模式（终端 + 浏览器）
"""

import argparse
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

# 确保项目目录在 Python 路径中
APP_PATH = Path(__file__).parent.absolute()
sys.path.insert(0, str(APP_PATH))

import tornado.ioloop

from config_manager import load_config
from proxy import start_proxy, stop_proxy, _proxy_running, _proxy_start_time
from web_ui import make_web_ui_app


def print_banner():
    print(r"""
   ____          _          ____                 _
  / ___|___   __| | _____  |  _ \  ___  ___ _ __| | __
 | |   / _ \ / _` |/ _ \ \/ / | | |/ _ \/ _ \ '__| |/ /
 | |__| (_) | (_| |  __/>  <| |_| |  __/  __/ |  |   <
  \____\___/ \__,_|\___/_/\_\____/ \___|\___|_|  |_|\_\

  Codex CLI → DeepSeek 代理 v1.1
  ===================================
""")
    print("  将 Codex CLI 的 API 请求自动转发至 DeepSeek")
    print()


def open_browser(port: int, delay: float = 1.5):
    time.sleep(delay)
    webbrowser.open(f"http://127.0.0.1:{port}")


# ─── Tornado 后台线程 ───────────────────────────────────────────

def _run_tornado_in_thread(web_port: int, proxy_host: str, proxy_port: int):
    """在独立线程中运行 Tornado（代理 + Web UI）"""
    import tornado.ioloop

    loop = tornado.ioloop.IOLoop()
    loop.make_current()

    # 启动代理服务器
    start_proxy(host=proxy_host, port=proxy_port)

    # 创建 Web UI 应用
    web_app = make_web_ui_app()
    web_app.listen(web_port, address="127.0.0.1")

    loop.start()


# ─── 系统托盘（主线程运行）────────────────────────────────────

def _run_tray_main(proxy_host: str, proxy_port: int, web_port: int):
    """在主线程运行 rumps 系统托盘（Cocoa 要求主线程）"""
    import rumps

    class TrayApp(rumps.App):
        def __init__(self):
            super().__init__(
                name="Codex-DS",
                title="🔄",
                quit_button=None,
            )
            self.menu = [
                rumps.MenuItem(title="代理运行中", callback=None),
                None,
                rumps.MenuItem(title="打开管理面板", callback=self._open_panel),
                rumps.MenuItem(title="复制终端配置", callback=self._copy_env),
                None,
                rumps.MenuItem(title="退出 Codex-DS", callback=self._quit_app),
            ]
            rumps.Timer(self._refresh, 3).start()

        def _refresh(self, _):
            from proxy import _proxy_running as running
            self.title = "🟢" if running else "🔴"
            if running:
                self.menu["代理运行中"].title = "代理运行中"
                self.menu["代理运行中"].set_callback(None)
            else:
                self.menu["代理运行中"].title = "代理已停止 — 点击重启"
                self.menu["代理运行中"].set_callback(self._restart_proxy)

        def _open_panel(self, _):
            webbrowser.open(f"http://127.0.0.1:{web_port}")

        def _copy_env(self, _):
            import subprocess
            cmd = (
                f'export OPENAI_BASE_URL=http://127.0.0.1:{proxy_port}/v1\n'
                'export OPENAI_API_KEY="deepseek-proxy"'
            )
            subprocess.run("pbcopy", input=cmd, text=True)
            prev = self.menu["复制终端配置"].title
            self.menu["复制终端配置"].title = "✅ 已复制到剪贴板"
            def restore():
                self.menu["复制终端配置"].title = prev
            threading.Timer(2.0, restore).start()

        def _restart_proxy(self, _):
            from proxy import start_proxy, _proxy_running
            if not _proxy_running:
                start_proxy(host=proxy_host, port=proxy_port)

        def _quit_app(self, _):
            from proxy import stop_proxy
            stop_proxy()
            try:
                rumps.quit_application()
            except Exception:
                pass
            os._exit(0)

    TrayApp().run()


# ─── 主入口 ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Codex DeepSeek Proxy - 将 Codex CLI 接入 DeepSeek 的桌面代理工具",
    )
    parser.add_argument(
        "--no-tray", action="store_true",
        help="不显示系统托盘图标（终端模式）",
    )
    parser.add_argument("--port", type=int, default=None, help="Web UI 端口")
    parser.add_argument("--proxy-port", type=int, default=None, help="代理端口")
    args = parser.parse_args()

    print_banner()

    config = load_config()
    web_port = args.port or 8788
    proxy_port = args.proxy_port or config.get("proxy_port", 8787)
    proxy_host = config.get("proxy_host", "127.0.0.1")
    show_tray = not args.no_tray

    # 检查 API Key
    api_key = config.get("deepseek_api_key", "")
    if not api_key:
        print("⚠️  尚未配置 DeepSeek API Key")
        print("   请启动后在管理面板中配置，或访问 https://platform.deepseek.com/api_keys 获取")
        print()

    if show_tray:
        # ─── 桌面模式：Tornado 后台线程 + 托盘主线程 ───
        print(f"🔌 代理服务器: http://{proxy_host}:{proxy_port}")
        print(f"🌐 管理面板: http://127.0.0.1:{web_port}")
        print(f"📌 系统托盘: 菜单栏可见 🔄 图标")
        print()

        # Tornado 放入后台线程
        threading.Thread(
            target=_run_tornado_in_thread,
            args=(web_port, proxy_host, proxy_port),
            daemon=True,
        ).start()

        # 等 Tornado 就绪后打开浏览器
        threading.Thread(target=open_browser, args=(web_port,), daemon=True).start()

        # 托盘在主线程运行（阻塞，Cocoa 要求主线程）
        try:
            _run_tray_main(proxy_host, proxy_port, web_port)
        except KeyboardInterrupt:
            print("\n正在关闭...")
            stop_proxy()
            print("代理已停止，再见！")
    else:
        # ─── 终端模式：Tornado 主线程 ───
        print(f"🔌 启动代理服务器: http://{proxy_host}:{proxy_port}")
        start_proxy(host=proxy_host, port=proxy_port)

        web_app = make_web_ui_app()
        web_app.listen(web_port, address="127.0.0.1")

        threading.Thread(target=open_browser, args=(web_port,), daemon=True).start()

        print(f"🌐 管理面板: http://127.0.0.1:{web_port}")
        print()
        print("📋 在另一个终端中设置环境变量以使用 Codex CLI：")
        print(f"   export OPENAI_BASE_URL=http://127.0.0.1:{proxy_port}/v1")
        print('   export OPENAI_API_KEY="deepseek-proxy"')
        print()
        print("   然后直接运行 codex 命令即可使用 DeepSeek")
        print()
        print("=" * 50)
        print("按 Ctrl+C 停止所有服务")
        print()

        try:
            tornado.ioloop.IOLoop.current().start()
        except KeyboardInterrupt:
            print("\n\n正在关闭...")
            stop_proxy()
            print("代理已停止，再见！")


if __name__ == "__main__":
    main()
