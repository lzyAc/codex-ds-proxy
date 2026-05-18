"""
Web UI — 基于 Tornado 的管理面板 API

提供: 配置 CRUD / 代理状态 / 请求日志 / 连接测试 / Provider 列表
"""

import json
import os
from datetime import datetime

import tornado.web
import requests as req

from config_manager import load_config, save_config, get_env_instructions, APP_PATH
from proxy import get_logs, get_stats, _proxy_running


class IndexHandler(tornado.web.RequestHandler):
    def get(self):
        path = os.path.join(APP_PATH, "templates", "index.html")
        with open(path, "r", encoding="utf-8") as f:
            html = f.read()
        self.set_header("Content-Type", "text/html; charset=utf-8")
        self.finish(html)


class ConfigHandler(tornado.web.RequestHandler):
    """GET /api/config — 获取（脱敏）; POST — 保存"""
    def get(self):
        c = load_config()
        safe = {**c}
        key = safe.get("deepseek_api_key", "")
        if key and len(key) > 8:
            safe["deepseek_api_key"] = key[:4] + "****" + key[-4:]
        elif key:
            safe["deepseek_api_key"] = "****"
        self.finish(safe)

    def post(self):
        try:
            data = json.loads(self.request.body.decode("utf-8"))
        except Exception:
            self.set_status(400)
            self.finish({"ok": False, "error": "无效的请求数据"})
            return

        c = load_config()
        if "deepseek_api_key" in data and "****" not in data["deepseek_api_key"]:
            c["deepseek_api_key"] = data["deepseek_api_key"]
        for k in ("deepseek_base_url", "deepseek_model", "proxy_host",
                  "proxy_port", "auto_start", "provider"):
            if k in data:
                c[k] = data[k]
        if "model_mapping" in data:
            c["model_mapping"] = data["model_mapping"]
        save_config(c)
        self.finish({"ok": True})


class ConfigTestHandler(tornado.web.RequestHandler):
    """POST /api/config/test — 测试当前 provider 连接"""
    def post(self):
        c = load_config()
        key = c.get("deepseek_api_key", "")
        url = c.get("deepseek_base_url", "https://api.deepseek.com")
        if not key:
            self.finish({"ok": False, "error": "请先配置 API Key"})
            return
        try:
            resp = req.post(
                f"{url.rstrip('/')}/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": c.get("deepseek_model", "deepseek-v4-pro"),
                      "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 5},
                timeout=15,
            )
            if resp.status_code == 200:
                self.finish({"ok": True, "message": "连接成功！API 响应正常"})
            else:
                self.finish({"ok": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"})
        except req.exceptions.ConnectionError:
            self.finish({"ok": False, "error": "无法连接服务器，请检查 Base URL"})
        except req.exceptions.Timeout:
            self.finish({"ok": False, "error": "连接超时，请检查网络"})
        except Exception as e:
            self.finish({"ok": False, "error": str(e)})


class ProxyStatusHandler(tornado.web.RequestHandler):
    def get(self):
        s = get_stats()
        c = load_config()
        self.finish({**s, "port": c.get("proxy_port", 8787),
                      "host": c.get("proxy_host", "127.0.0.1"),
                      "provider": c.get("provider", "deepseek")})


class LogsHandler(tornado.web.RequestHandler):
    def get(self):
        limit = int(self.get_argument("limit", 100))
        logs = get_logs(limit)
        self.set_header("Content-Type", "application/json")
        self.finish(json.dumps(logs, ensure_ascii=False))


class EnvHandler(tornado.web.RequestHandler):
    def get(self):
        c = load_config()
        self.finish({"instructions": get_env_instructions(c)})


class HealthHandler(tornado.web.RequestHandler):
    def get(self):
        self.finish({"status": "ok", "proxy_running": _proxy_running,
                      "time": datetime.now().isoformat()})


class ProvidersHandler(tornado.web.RequestHandler):
    """GET /api/providers — 列出所有已注册的 provider"""
    def get(self):
        from providers import list_providers
        self.finish({"providers": list_providers()})


def make_web_ui_app() -> tornado.web.Application:
    static_path = os.path.join(APP_PATH, "static")
    return tornado.web.Application([
        (r"/", IndexHandler),
        (r"/api/config", ConfigHandler),
        (r"/api/config/test", ConfigTestHandler),
        (r"/api/proxy/status", ProxyStatusHandler),
        (r"/api/logs", LogsHandler),
        (r"/api/env", EnvHandler),
        (r"/api/health", HealthHandler),
        (r"/api/providers", ProvidersHandler),
        (r"/static/(.*)", tornado.web.StaticFileHandler, {"path": static_path}),
    ])
