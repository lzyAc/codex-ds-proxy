"""
代理服务器核心 — 基于 Tornado 异步框架

拦截 Codex CLI 的 OpenAI API 请求并转发至后端 LLM Provider。
通过 providers/ 抽象层支持 DeepSeek 及任何 OpenAI 兼容 API。

协议支持:
  - HTTP Chat Completions (纯 HTTP 转发)
  - WebSocket Responses API → Chat Completions (协议转换)
"""

import json
import logging
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

import tornado.ioloop
import tornado.web
import tornado.websocket
import tornado.httpclient
from tornado.escape import json_decode

from config_manager import load_config
from providers import get_provider

logger = logging.getLogger("codex-ds-proxy")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s", datefmt="%H:%M:%S")
logger.setLevel(logging.INFO)

CST = timezone(timedelta(hours=8))

# ─── 状态与日志 ───────────────────────────────────────────────

_request_logs: list[dict] = []
_logs_lock = threading.Lock()
_proxy_running = False
_proxy_start_time: Optional[datetime] = None
_total_requests = 0
_total_tokens = 0


def get_logs(limit: int = 100) -> list[dict]:
    with _logs_lock:
        return _request_logs[-limit:]


def get_stats() -> dict:
    return {
        "running": _proxy_running,
        "start_time": _proxy_start_time.isoformat() if _proxy_start_time else None,
        "total_requests": _total_requests,
        "total_tokens": _total_tokens,
    }


def _add_log(entry: dict) -> None:
    global _total_requests, _total_tokens
    with _logs_lock:
        entry["id"] = len(_request_logs) + 1
        _request_logs.append(entry)
        if len(_request_logs) > 500:
            _request_logs.pop(0)
    _total_requests += 1
    _total_tokens += entry.get("tokens", 0)


# ─── HTTP Chat Completions 处理器 ──────────────────────────────

class ModelsHandler(tornado.web.RequestHandler):
    """GET /v1/models — 返回可用模型列表（OpenAI + Anthropic 格式兼容）"""
    def get(self, _subpath: str = ""):
        config = load_config()
        provider = get_provider(config=config)
        deepseek_models = provider.meta.get("models", [])
        # Claude 模型名 → 后端用 DeepSeek
        claude_models = [
            {"id": "claude-sonnet-4-20250514", "object": "model", "created": 1710000000, "owned_by": "anthropic"},
            {"id": "claude-opus-4-20250514", "object": "model", "created": 1710000000, "owned_by": "anthropic"},
            {"id": "claude-3.5-sonnet", "object": "model", "created": 1710000000, "owned_by": "anthropic"},
            {"id": "claude-3.5-haiku", "object": "model", "created": 1710000000, "owned_by": "anthropic"},
            {"id": "claude-opus-4.6", "object": "model", "created": 1710000000, "owned_by": "anthropic"},
            {"id": "claude-sonnet-4.6", "object": "model", "created": 1710000000, "owned_by": "anthropic"},
            {"id": "claude-haiku-4.6", "object": "model", "created": 1710000000, "owned_by": "anthropic"},
            {"id": "claude-opus-4.7", "object": "model", "created": 1710000000, "owned_by": "anthropic"},
            {"id": "claude-sonnet-4.7", "object": "model", "created": 1710000000, "owned_by": "anthropic"},
            # 1M 上下文模式
            {"id": "claude-opus-4.6-1m", "object": "model", "created": 1710000000, "owned_by": "anthropic"},
            {"id": "claude-sonnet-4.6-1m", "object": "model", "created": 1710000000, "owned_by": "anthropic"},
            {"id": "claude-haiku-4.6-1m", "object": "model", "created": 1710000000, "owned_by": "anthropic"},
            {"id": "claude-opus-4.7-1m", "object": "model", "created": 1710000000, "owned_by": "anthropic"},
            {"id": "claude-sonnet-4.7-1m", "object": "model", "created": 1710000000, "owned_by": "anthropic"},
        ]
        self.finish({
            "object": "list",
            "data": deepseek_models + claude_models,
        })


class ChatCompletionsHandler(tornado.web.RequestHandler):
    """POST /v1/chat/completions — 透明转发到后端 provider"""

    async def post(self):
        config = load_config()
        provider = get_provider(config=config)

        if not provider.get_api_key():
            self.set_status(500)
            self.finish({"error": {"message": "API Key 未配置", "type": "config_error"}})
            return

        try:
            body = json_decode(self.request.body)
        except Exception:
            self.set_status(400)
            self.finish({"error": {"message": "无效的请求体", "type": "invalid_request"}})
            return

        original_model = body.get("model", "unknown")
        body["model"] = provider.map_model(original_model)
        is_stream = body.get("stream", False) is True

        logger.info(f"[Proxy] ChatCompletions model={original_model}→{body['model']}, stream={is_stream}")

        t0 = time.time()
        try:
            if is_stream:
                await self._proxy_stream(provider, body, original_model, body["model"], t0)
            else:
                await self._proxy_non_stream(provider, body, original_model, body["model"], t0)
        except tornado.httpclient.HTTPClientError as e:
            err_detail = str(e.response.body)[:500] if hasattr(e, 'response') and e.response else str(e)
            logger.error(f"Upstream error: HTTP {e.code} - {err_detail}")
            _add_log({
                "time": datetime.now(CST).isoformat(),
                "model_original": original_model, "model_mapped": body["model"],
                "stream": is_stream, "status": "error", "error": str(e)[:100],
                "duration_ms": int((time.time() - t0) * 1000), "tokens": 0,
            })
            self.set_status(502)
            self.finish({"error": {"message": str(e)[:200], "type": "upstream_error"}})
        except Exception as e:
            _add_log({
                "time": datetime.now(CST).isoformat(),
                "model_original": original_model, "model_mapped": body["model"],
                "stream": is_stream, "status": "error", "error": str(e)[:100],
                "duration_ms": int((time.time() - t0) * 1000), "tokens": 0,
            })
            self.set_status(502)
            self.finish({"error": {"message": str(e)[:200], "type": "connection_error"}})

    async def _proxy_non_stream(self, provider, body, orig, mapped, t0):
        resp = await provider.chat_completion(body)
        tokens = resp.get("usage", {}).get("total_tokens", 0)
        _add_log({
            "time": datetime.now(CST).isoformat(), "model_original": orig,
            "model_mapped": mapped, "stream": False, "status": "success",
            "duration_ms": int((time.time() - t0) * 1000), "tokens": tokens,
        })
        self.set_header("Content-Type", "application/json")
        self.finish(resp)

    async def _proxy_stream(self, provider, body, orig, mapped, t0):
        self.set_header("Content-Type", "text/event-stream")
        self.set_header("Cache-Control", "no-cache")
        self.set_header("Connection", "keep-alive")
        self.set_header("X-Accel-Buffering", "no")

        chunk_count = 0
        full_text = ""
        async for event in provider.stream_chat_completion(body):
            if event.get("_done"):
                break
            line = f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            self.write(line)
            chunk_count += 1
            if chunk_count % 10 == 0:
                self.flush()
            # 统计文本 token
            for choice in event.get("choices", []):
                d = choice.get("delta", {})
                full_text += (d.get("content") or "")

        self.flush()
        _add_log({
            "time": datetime.now(CST).isoformat(), "model_original": orig,
            "model_mapped": mapped, "stream": True, "status": "success",
            "duration_ms": int((time.time() - t0) * 1000), "tokens": len(full_text) // 3,
        })


# ─── Anthropic Messages API 处理器 ───────────────────────────

class AnthropicMessagesHandler(tornado.web.RequestHandler):
    """POST /v1/messages — Anthropic Messages API → DeepSeek Chat Completions"""

    async def post(self):
        config = load_config()
        provider = get_provider(config=config)

        if not provider.get_api_key():
            self.set_status(500)
            self.finish({"type": "error", "error": {"type": "authentication_error",
                         "message": "API Key 未配置"}})
            return

        try:
            body = json_decode(self.request.body)
        except Exception:
            self.set_status(400)
            self.finish({"type": "error", "error": {"type": "invalid_request_error",
                         "message": "无效的请求体"}})
            return

        from anthropic_adapter import anthropic_to_openai, openai_to_anthropic, stream_anthropic, is_large_context_model
        orig_model = body.get("model", "unknown")

        # 转为 OpenAI 格式
        chat_body = anthropic_to_openai(body)
        chat_body["stream"] = True

        if not chat_body.get("messages"):
            # 如果消息为空，返回错误而不是发给 DeepSeek
            self.set_status(400)
            self.finish({"type": "error", "error": {"type": "invalid_request_error",
                         "message": f"No messages to process. Input keys: {list(body.keys())}"}})
            return

        t0 = time.time()
        try:
            msg_count = len(chat_body.get("messages", []))
            msg_roles = [m.get('role','?') for m in chat_body.get('messages', [])]
            has_tool_calls = any('tool_calls' in m for m in chat_body.get('messages', []))
            has_tool_msgs = any(m.get('role') == 'tool' for m in chat_body.get('messages', []))
            large_ctx = " [1M]" if is_large_context_model(orig_model) else ""
            logger.info(f"[Proxy] model={orig_model}→{chat_body.get('model')}{large_ctx}, msgs={msg_count}, "
                        f"max_tokens={chat_body.get('max_tokens', 'N/A')}, tools={len(chat_body.get('tools',[]))}, "
                        f"tool_calls={has_tool_calls}, tool_msgs={has_tool_msgs}, roles={msg_roles[:20]}{'...' if len(msg_roles)>20 else ''}")
            in_tokens, out_tokens = await stream_anthropic(provider, chat_body, orig_model, self)

            _add_log({
                "time": datetime.now(CST).isoformat(),
                "model_original": orig_model,
                "model_mapped": chat_body["model"],
                "stream": True, "status": "success",
                "duration_ms": int((time.time() - t0) * 1000), "tokens": out_tokens,
            })
        except tornado.httpclient.HTTPClientError as e:
            err_detail = str(e.response.body)[:500] if hasattr(e, 'response') and e.response else str(e)
            logger.error(f"[Anthropic Error] HTTP {e.code}: {err_detail}")
            msg_roles = [m.get('role','?') for m in chat_body.get('messages',[])]
            msg_count = len(chat_body.get('messages',[]))
            logger.error(f"[Anthropic Error] model={chat_body.get('model')}, msgs={msg_count}, roles={msg_roles[:50]}...")
            _add_log({
                "time": datetime.now(CST).isoformat(),
                "model_original": orig_model, "model_mapped": chat_body["model"],
                "stream": True, "status": "error", "error": str(e)[:100],
                "duration_ms": int((time.time() - t0) * 1000), "tokens": 0,
            })
            # 检测工具调用校验错误，给出更友好的提示
            if "tool_calls" in err_detail.lower() or "insufficient tool" in err_detail.lower():
                logger.warning("Tool call pairing error detected. The adapter will attempt to fix this automatically.")
            self.set_status(502)
            self.set_header("Content-Type", "text/event-stream")
            self.set_header("Cache-Control", "no-cache")
            self.set_header("Connection", "keep-alive")
            self.set_header("X-Accel-Buffering", "no")
            # 以 SSE 格式返回错误，让 Claude Desktop 能解析
            self.write("event: error\ndata: " + json.dumps({
                "type": "error",
                "error": {"type": "api_error", "message": f"DeepSeek API 错误 (HTTP {e.code})，请尝试刷新对话"}
            }, ensure_ascii=False) + "\n\n")
            self.flush()
        except Exception as e:
            logger.error(f"Anthropic unexpected error: {e}", exc_info=True)
            _add_log({
                "time": datetime.now(CST).isoformat(),
                "model_original": orig_model, "model_mapped": chat_body["model"],
                "stream": True, "status": "error", "error": str(e)[:100],
                "duration_ms": int((time.time() - t0) * 1000), "tokens": 0,
            })
            self.set_status(502)
            self.set_header("Content-Type", "text/event-stream")
            self.set_header("Cache-Control", "no-cache")
            self.set_header("Connection", "keep-alive")
            self.set_header("X-Accel-Buffering", "no")
            self.write("event: error\ndata: " + json.dumps({
                "type": "error",
                "error": {"type": "api_error", "message": f"代理内部错误: {str(e)[:200]}"}
            }, ensure_ascii=False) + "\n\n")
            self.flush()


# ─── WebSocket Responses API → Chat Completions ────────────────

class ResponsesWsHandler(tornado.websocket.WebSocketHandler):
    """处理 /v1/responses WebSocket — Responses API 转 Chat Completions"""

    def check_origin(self, origin):
        return True

    def open(self):
        logger.info("[Proxy] WebSocket /v1/responses 已连接")
        self._history = []  # 对话历史
        self._turn = 0

    async def on_message(self, message):
        self._turn += 1
        if isinstance(message, bytes):
            message = message.decode("utf-8")
        message = message.strip()
        if not message:
            return

        try:
            body = json.loads(message)
        except json.JSONDecodeError:
            return

        config = load_config()
        provider = get_provider(config=config)

        if not provider.get_api_key():
            self.write_message(json.dumps({
                "type": "error", "error": {"message": "API Key 未配置"}
            }))
            self.close()
            return

        t0 = time.time()
        original_model = body.get("model", "unknown")
        mapped_model = provider.map_model(original_model)

        # 构建 Chat 请求
        chat_body = _responses_to_chat(body, mapped_model, provider, self._history)
        chat_body["stream"] = True

        logger.info(f"[Proxy] turn={self._turn}, model={original_model}→{mapped_model}, "
              f"msgs={len(chat_body.get('messages',[]))}, tools={len(chat_body.get('tools',[]))}")

        try:
            await self._do_stream(provider, chat_body, body, mapped_model,
                                  original_model, t0)
        except Exception as e:
            import traceback
            traceback.print_exc()
            _add_log({
                "time": datetime.now(CST).isoformat(),
                "model_original": original_model, "model_mapped": mapped_model,
                "stream": True, "status": "error", "error": str(e)[:100],
                "duration_ms": int((time.time() - t0) * 1000), "tokens": 0,
            })
            self.close()

    async def _do_stream(self, provider, chat_body, body, mapped_model,
                         original_model, t0):
        """流式转发 SSE → WebSocket 事件"""
        # 发送前置事件
        response_id = body.get("id", "") or f"resp_{int(time.time())}"
        self.write_message(json.dumps({
            "type": "response.created",
            "response": {"id": response_id, "object": "response",
                         "model": mapped_model, "status": "in_progress", "output": []}
        }, ensure_ascii=False))
        self.write_message(json.dumps({
            "type": "response.in_progress", "response_id": response_id
        }, ensure_ascii=False))

        # 状态追踪
        msg_sent = False
        msg_id = f"{response_id}_msg_0"
        full_text = ""
        full_reasoning = ""
        tool_calls = {}  # {index: {id, name, arguments, item_id}}
        usage_in = usage_out = 0
        output_items = []

        def _ensure_msg():
            nonlocal msg_sent
            if not msg_sent:
                msg_sent = True
                self.write_message(json.dumps({
                    "type": "response.output_item.added", "output_index": 0,
                    "item": {"id": msg_id, "object": "realtime.item",
                             "type": "message", "status": "in_progress",
                             "role": "assistant", "content": []}
                }, ensure_ascii=False))
                self.write_message(json.dumps({
                    "type": "response.content_part.added",
                    "item_id": msg_id, "output_index": 0, "content_index": 0,
                    "part": {"type": "output_text", "text": ""}
                }, ensure_ascii=False))

        def _ensure_tc(idx, tc_data):
            if idx not in tool_calls:
                tc_id = tc_data.get("id", "") or f"call_{idx}"
                tc_name = tc_data.get("function", {}).get("name", "")
                item_id = f"{response_id}_tc_{idx}"
                tool_calls[idx] = {"id": tc_id, "name": tc_name,
                                   "arguments": "", "item_id": item_id}
                self.write_message(json.dumps({
                    "type": "response.output_item.added",
                    "output_index": idx + (1 if msg_sent else 0),
                    "item": {"id": item_id, "object": "realtime.item",
                             "type": "function_call", "status": "in_progress",
                             "call_id": tc_id, "name": tc_name, "arguments": ""}
                }, ensure_ascii=False))

        # 流式解析并转发
        async for event in provider.stream_chat_completion(chat_body):
            if event.get("_done"):
                break

            if "usage" in event:
                usage_in = event["usage"].get("prompt_tokens", 0)
                usage_out = event["usage"].get("completion_tokens", 0)

            for choice in event.get("choices", []):
                delta = choice.get("delta", {})

                text = delta.get("content") or ""
                reasoning = delta.get("reasoning_content") or ""
                if reasoning:
                    full_reasoning += reasoning
                if text or reasoning:
                    _ensure_msg()
                    full_text += text
                    self.write_message(json.dumps({
                        "type": "response.output_text.delta",
                        "item_id": msg_id, "output_index": 0, "content_index": 0,
                        "delta": text,
                    }, ensure_ascii=False))

                for tc in delta.get("tool_calls", []):
                    idx = tc.get("index", 0)
                    _ensure_tc(idx, tc)
                    if "function" in tc:
                        args = tc["function"].get("arguments", "")
                        if args:
                            tool_calls[idx]["arguments"] += args
                            self.write_message(json.dumps({
                                "type": "response.function_call_arguments.delta",
                                "item_id": tool_calls[idx]["item_id"],
                                "output_index": idx + (1 if msg_sent else 0),
                                "delta": args,
                            }, ensure_ascii=False))
                    fn_name = tc.get("function", {}).get("name", "")
                    if fn_name and not tool_calls[idx]["name"]:
                        tool_calls[idx]["name"] = fn_name

        # ─── 发送完成事件 ───
        if msg_sent and full_text:
            self.write_message(json.dumps({
                "type": "response.output_text.done",
                "item_id": msg_id, "output_index": 0, "content_index": 0,
                "text": full_text,
            }, ensure_ascii=False))
            self.write_message(json.dumps({
                "type": "response.content_part.done",
                "item_id": msg_id, "output_index": 0, "content_index": 0,
                "part": {"type": "output_text", "text": full_text},
            }, ensure_ascii=False))
            self.write_message(json.dumps({
                "type": "response.output_item.done", "output_index": 0,
                "item": {"id": msg_id, "object": "realtime.item",
                         "type": "message", "status": "completed",
                         "role": "assistant",
                         "content": [{"type": "output_text", "text": full_text}]}
            }, ensure_ascii=False))
            output_items.append({
                "type": "message", "id": msg_id, "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": full_text}],
            })

        for idx in sorted(tool_calls.keys()):
            tc = tool_calls[idx]
            self.write_message(json.dumps({
                "type": "response.function_call_arguments.done",
                "item_id": tc["item_id"],
                "output_index": idx + (1 if msg_sent else 0),
                "arguments": tc["arguments"],
            }, ensure_ascii=False))
            self.write_message(json.dumps({
                "type": "response.output_item.done",
                "output_index": idx + (1 if msg_sent else 0),
                "item": {"id": tc["item_id"], "object": "realtime.item",
                         "type": "function_call", "status": "completed",
                         "call_id": tc["id"], "name": tc["name"],
                         "arguments": tc["arguments"]}
            }, ensure_ascii=False))
            output_items.append({
                "type": "function_call", "id": tc["item_id"],
                "call_id": tc["id"], "name": tc["name"],
                "arguments": tc["arguments"], "status": "completed",
            })

        if usage_out == 0:
            usage_out = max(1, sum(len(tc["arguments"]) // 2 for tc in tool_calls.values()))

        self.write_message(json.dumps({
            "type": "response.completed",
            "response": {
                "id": response_id, "object": "response", "model": mapped_model,
                "status": "completed", "output": output_items,
                "usage": {"input_tokens": usage_in, "output_tokens": usage_out,
                          "total_tokens": usage_in + usage_out},
            }
        }, ensure_ascii=False))

        # 保存对话历史
        saved = []
        for m in chat_body.get("messages", []):
            msg = dict(m)
            if msg.get("role") == "assistant" and full_reasoning:
                msg["reasoning_content"] = full_reasoning
            saved.append(msg)
        self._history = saved

        _add_log({
            "time": datetime.now(CST).isoformat(),
            "model_original": original_model, "model_mapped": mapped_model,
            "stream": True, "status": "success",
            "duration_ms": int((time.time() - t0) * 1000), "tokens": usage_out,
        })
        self.close()


# ─── 协议转换工具 ────────────────────────────────────────────

def _responses_to_chat(body: dict, mapped_model: str, provider, history: list) -> dict:
    """Responses API → Chat Completions JSON"""
    messages = []
    instructions = body.get("instructions", "")
    if instructions:
        messages.append({"role": "system", "content": instructions})

    user_input = body.get("input", "")
    if isinstance(user_input, list):
        for item in user_input:
            t = item.get("type", "")
            role = item.get("role", "user")
            if t == "message":
                content = item.get("content", "")
                if isinstance(content, list):
                    parts = [p.get("text", "") for p in content
                             if p.get("type") in ("input_text", "output_text")]
                    if role in ("user", "assistant") and parts:
                        messages.append({"role": role, "content": " ".join(parts)})
                elif isinstance(content, str) and content:
                    messages.append({"role": role, "content": content})
            elif t == "function_call":
                # 合并到前一条 assistant 消息（如果存在），DeepSeek 要求
                # assistant 的 text 和 tool_calls 在同一个消息中
                tc = {
                    "id": item.get("call_id", ""), "type": "function",
                    "function": {"name": item.get("name", ""),
                                 "arguments": item.get("arguments", "")}
                }
                if messages and messages[-1]["role"] == "assistant":
                    existing = messages[-1].setdefault("tool_calls", [])
                    existing.append(tc)
                    if messages[-1].get("content") is None and "content" not in messages[-1]:
                        messages[-1]["content"] = None
                else:
                    messages.append({
                        "role": "assistant", "content": None,
                        "tool_calls": [tc]
                    })
            elif t == "function_call_output":
                messages.append({
                    "role": "tool",
                    "tool_call_id": item.get("call_id", ""),
                    "content": str(item.get("output", "")),
                })
    elif isinstance(user_input, str) and user_input:
        if history:
            messages = history + messages
        messages.append({"role": "user", "content": user_input})

    # input 数组已包含完整对话历史，不再拼接 history 避免重复

    chat = {"model": mapped_model, "messages": messages}
    # 多轮关闭 thinking
    if len(messages) > 1:
        chat["thinking"] = {"type": "disabled"}

    for k in ("temperature", "top_p", "max_tokens", "max_output_tokens"):
        if k in body:
            chat["max_tokens" if k == "max_output_tokens" else k] = body[k]

    if "tools" in body:
        chat["tools"] = provider.convert_tools(body["tools"])
    if "tool_choice" in body:
        chat["tool_choice"] = provider.convert_tool_choice(body["tool_choice"])

    # 验证并修复 tool_call 配对关系
    from anthropic_adapter import _validate_tool_call_pairs, _merge_adjacent_assistant
    chat["messages"] = _validate_tool_call_pairs(chat["messages"])
    chat["messages"] = _merge_adjacent_assistant(chat["messages"])

    return chat


# ─── 上下文压缩桩（DeepSeek 无此接口）─────────────────────────

class CompactHandler(tornado.web.RequestHandler):
    """POST /v1/responses/compact — 返回原始消息（无操作压缩）"""
    async def post(self):
        try:
            body = json_decode(self.request.body)
        except Exception:
            self.set_status(400)
            self.finish({"error": {"message": "invalid body"}})
            return
        self.finish({
            "output": body.get("input", body.get("messages", [])),
            "compacted": False
        })


# ─── 杂项端点 ───────────────────────────────────────────────

class FaviconHandler(tornado.web.RequestHandler):
    """GET /favicon.ico — 返回空 204，避免 Claude Desktop 疯狂 404 日志"""
    def get(self):
        self.set_status(204)
        self.finish()

    head = get


class RootHandler(tornado.web.RequestHandler):
    """GET / 或 HEAD / — Claude Desktop 会发 HEAD 检查，返回 200"""
    async def get(self):
        self.set_status(200)
        self.set_header("Content-Type", "application/json")
        self.finish({"status": "ok", "service": "codex-ds-proxy"})

    async def head(self):
        self.set_status(200)
        self.set_header("Content-Type", "application/json")
        self.finish()


class CatchAllHandler(tornado.web.RequestHandler):
    async def get(self, subpath: str):
        if subpath.startswith("api/"):
            # 不转发 /api/ 开头的路径
            self.set_status(404)
            self.finish({"error": "Not found"})
            return
        await self._fwd("GET", subpath)

    async def post(self, subpath: str):
        await self._fwd("POST", subpath)

    async def head(self, subpath: str):
        # HEAD 请求直接返回 200 空响应
        self.set_status(200)
        self.finish()

    async def _fwd(self, method: str, subpath: str):
        config = load_config()
        provider = get_provider(config=config)
        url = provider.build_url(f"v1/{subpath}")
        headers = provider.get_headers()
        body = self.request.body or None
        req = tornado.httpclient.HTTPRequest(
            url=url, method=method, headers=headers,
            body=body, request_timeout=120,
        )
        http = tornado.httpclient.AsyncHTTPClient()
        try:
            resp = await http.fetch(req)
            self.set_header("Content-Type", resp.headers.get("Content-Type", "application/json"))
            self.finish(resp.body)
        except Exception as e:
            self.set_status(502)
            self.finish({"error": {"message": str(e)[:200]}})


class CountTokensHandler(tornado.web.RequestHandler):
    """POST /v1/messages/count_tokens — Claude token 计数端点"""

    async def post(self):
        try:
            body = json_decode(self.request.body)
        except Exception:
            self.finish({"input_tokens": 0})
            return

        from anthropic_adapter import anthropic_to_openai
        chat_body = anthropic_to_openai(body)

        # 粗略估算 token 数: UTF-8 字节数 / 2
        total_text = ""
        for msg in chat_body.get("messages", []):
            content = msg.get("content", "")
            if isinstance(content, str):
                total_text += content
            elif isinstance(content, list):
                total_text += json.dumps(content)
        for tool in chat_body.get("tools", []):
            total_text += json.dumps(tool)

        est_tokens = max(1, len(total_text.encode("utf-8")) // 2)
        self.finish({"input_tokens": est_tokens})


class EventLoggingHandler(tornado.web.RequestHandler):
    """POST /api/event_logging/batch — Claude 遥测，静默忽略"""

    def post(self):
        self.finish({})

    def options(self):
        self.set_status(204)
        self.finish()


class HealthHandler(tornado.web.RequestHandler):
    def get(self):
        self.finish({"status": "ok", "service": "codex-ds-proxy"})


# ─── 应用工厂 / 启停 ──────────────────────────────────────────

def make_proxy_app() -> tornado.web.Application:
    return tornado.web.Application([
        (r"/favicon.ico", FaviconHandler),
        (r"/", RootHandler),
        (r"/v1/models(?:/(.*))?", ModelsHandler),
        (r"/v1/messages/count_tokens", CountTokensHandler),
        (r"/v1/messages", AnthropicMessagesHandler),
        (r"/v1/chat/completions", ChatCompletionsHandler),
        (r"/api/event_logging/batch", EventLoggingHandler),
        (r"/v1/responses/compact", CompactHandler),
        (r"/v1/responses", ResponsesWsHandler),
        (r"/v1/(.*)", CatchAllHandler),
        (r"/health", HealthHandler),
    ])


def start_proxy(host: str = "127.0.0.1", port: int = 8787):
    global _proxy_running, _proxy_start_time
    app = make_proxy_app()
    app.listen(port, address=host)
    _proxy_running = True
    _proxy_start_time = datetime.now(timezone.utc)
    logger.info(f"代理服务器已启动: http://{host}:{port}")
    return app


def stop_proxy():
    global _proxy_running
    _proxy_running = False
    try:
        tornado.ioloop.IOLoop.current().stop()
    except Exception:
        pass
    logger.info("代理服务器已停止")
