"""
DeepSeek Provider — 对接 api.deepseek.com 的 Chat Completions API
"""

import json
import time
from typing import AsyncGenerator

import tornado.httpclient

from .base import BaseProvider


class DeepSeekProvider(BaseProvider):
    """DeepSeek API 提供商"""

    meta = {
        "name": "DeepSeek",
        "description": "DeepSeek V4/V3/R1 — 高性价比大模型，1M 上下文",
        "models": [
            {"id": "deepseek-v4-pro", "name": "DeepSeek V4 Pro", "desc": "旗舰模型，最强推理"},
            {"id": "deepseek-v4-flash", "name": "DeepSeek V4 Flash", "desc": "快速高性价比"},
            {"id": "deepseek-chat", "name": "DeepSeek Chat (V3)", "desc": "通用对话"},
            {"id": "deepseek-reasoner", "name": "DeepSeek Reasoner (R1)", "desc": "推理专家"},
        ],
    }

    def __init__(self, config: dict):
        super().__init__(config)
        self._http = tornado.httpclient.AsyncHTTPClient(max_clients=50)

    async def chat_completion(self, body: dict) -> dict:
        url = self.build_url("v1/chat/completions")
        headers = self.get_headers()
        body["stream"] = False
        req = tornado.httpclient.HTTPRequest(
            url=url, method="POST", headers=headers,
            body=json.dumps(body, ensure_ascii=False),
            request_timeout=120, connect_timeout=30,
        )
        resp = await self._http.fetch(req, raise_error=False)
        if resp.code != 200:
            err_body = resp.body.decode(errors="replace")[:1000]
            error = tornado.httpclient.HTTPClientError(resp.code, err_body)
            error.response = resp  # 保存响应对象以便日志记录
            raise error
        return json.loads(resp.body)

    async def stream_chat_completion(self, body: dict) -> AsyncGenerator[dict, None]:
        """流式 Chat Completion，yield SSE 事件"""
        url = self.build_url("v1/chat/completions")
        headers = self.get_headers()
        body["stream"] = True

        req = tornado.httpclient.HTTPRequest(
            url=url, method="POST", headers=headers,
            body=json.dumps(body, ensure_ascii=False),
            request_timeout=300, connect_timeout=30,
        )
        resp = await self._http.fetch(req, raise_error=False)
        if resp.code != 200:
            err_body = resp.body.decode(errors="replace")[:1000]
            error = tornado.httpclient.HTTPClientError(resp.code, err_body)
            error.response = resp  # 保存响应对象以便日志记录
            raise error

        # 解析 SSE 流式响应
        raw = resp.body.decode("utf-8", errors="replace")
        for line in raw.split("\n"):
            line = line.strip()
            if not line or not line.startswith("data: "):
                continue
            data = line[6:]
            if data == "[DONE]":
                yield {"_done": True}
                return
            try:
                yield json.loads(data)
            except json.JSONDecodeError:
                continue
        yield {"_done": True}
