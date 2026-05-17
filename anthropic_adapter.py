"""
Anthropic Messages API ↔ OpenAI Chat Completions 格式转换

支持 Claude Desktop / Claude CLI / 任意 Anthropic SDK 客户端
通过代理将请求转发至 DeepSeek。
"""

import json
import time
import uuid


# ─── 模型名映射 ────────────────────────────────────────────

CLAUDE_MODEL_MAP = {
    "claude-sonnet-4-20250514": "deepseek-v4-pro",
    "claude-sonnet-4-5-20250929": "deepseek-v4-pro",
    "claude-sonnet-4-5-20250915": "deepseek-v4-pro",
    "claude-opus-4-20250514": "deepseek-v4-pro",
    "claude-opus-4-5-20250915": "deepseek-v4-pro",
    "claude-haiku-4-5-20251001": "deepseek-v4-flash",
    "claude-3.5-sonnet": "deepseek-v4-pro",
    "claude-3.5-haiku": "deepseek-v4-flash",
    "claude-3-opus": "deepseek-v4-pro",
    "claude-3-sonnet": "deepseek-v4-pro",
    "claude-3-haiku": "deepseek-v4-flash",
}

def map_claude_model(model: str) -> str:
    """Claude 模型名 → DeepSeek 模型名"""
    if model in CLAUDE_MODEL_MAP:
        return CLAUDE_MODEL_MAP[model]
    for prefix, target in CLAUDE_MODEL_MAP.items():
        if model.startswith(prefix):
            return target
    return "deepseek-v4-pro"


# ─── Request: Anthropic → OpenAI ───────────────────────────

def anthropic_to_openai(body: dict) -> dict:
    """将 Anthropic Messages 请求转为 OpenAI Chat Completions 请求"""
    messages = []

    # System prompt
    system = body.get("system", "")
    if system:
        if isinstance(system, list):
            parts = [p.get("text", "") for p in system if p.get("type") == "text"]
            system_text = " ".join(parts)
        else:
            system_text = system
        if system_text.strip():
            messages.append({"role": "system", "content": system_text})

    # Messages
    for msg in body.get("messages", []):
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if isinstance(content, str):
            messages.append({"role": role, "content": content})
        elif isinstance(content, list):
            text_parts = []
            tool_calls = []
            tool_results = []
            for block in content:
                btype = block.get("type", "")
                if btype == "text":
                    text_parts.append(block.get("text", ""))
                elif btype == "tool_use":
                    input_data = block.get("input", {})
                    tool_calls.append({
                        "id": block.get("id", ""),
                        "type": "function",
                        "function": {
                            "name": block.get("name", ""),
                            "arguments": json.dumps(input_data, ensure_ascii=False)
                        }
                    })
                elif btype == "tool_result":
                    tool_results.append({
                        "role": "tool",
                        "tool_call_id": block.get("tool_use_id", ""),
                        "content": block.get("content", "") if isinstance(block.get("content"), str)
                                   else json.dumps(block.get("content", ""))
                    })
                elif btype == "image":
                    text_parts.append("[image]")
                elif btype == "thinking":
                    text_parts.append(block.get("thinking", ""))
            # 合并：同一原始消息的 text + tool_calls → 一条 assistant 消息
            if tool_calls:
                assistant_msg = {"role": "assistant", "tool_calls": tool_calls}
                if text_parts:
                    assistant_msg["content"] = " ".join(text_parts)
                else:
                    assistant_msg["content"] = None
                messages.append(assistant_msg)
            elif text_parts:
                messages.append({"role": role, "content": " ".join(text_parts)})
            # tool_results 放在最后
            messages.extend(tool_results)
        else:
            messages.append({"role": role, "content": str(content)})

    chat = {
        "model": map_claude_model(body.get("model", "")),
        "messages": messages,
    }

    # max_tokens → max_tokens
    if "max_tokens" in body:
        chat["max_tokens"] = min(body["max_tokens"], 8192)

    # Anthropic tools → OpenAI tools
    tools = body.get("tools", [])
    if tools:
        openai_tools = []
        for tool in tools:
            if isinstance(tool, dict) and tool.get("name"):
                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
                    }
                })
        if openai_tools:
            chat["tools"] = openai_tools

    # temperature, top_p, stop_sequences → stop
    for k in ("temperature", "top_p"):
        if k in body:
            chat[k] = body[k]
    if "stop_sequences" in body and body["stop_sequences"]:
        chat["stop"] = body["stop_sequences"]

    # 禁用 thinking（DeepSeek 需要多轮推理上下文）
    if len(messages) > 1:
        chat["thinking"] = {"type": "disabled"}

    return chat


# ─── Response: OpenAI → Anthropic ──────────────────────────

def openai_to_anthropic(openai_resp: dict, model: str) -> dict:
    """将 OpenAI Chat Completions 响应转为 Anthropic Messages 响应"""
    msg_id = f"msg_{uuid.uuid4().hex[:24]}"
    choice = openai_resp.get("choices", [{}])[0]
    oai_msg = choice.get("message", {})
    usage = openai_resp.get("usage", {})

    content = []
    text = oai_msg.get("content", "")
    if text:
        content.append({"type": "text", "text": text})

    for tc in oai_msg.get("tool_calls", []):
        fn = tc.get("function", {})
        try:
            args = json.loads(fn.get("arguments", "{}"))
        except json.JSONDecodeError:
            args = {}
        content.append({
            "type": "tool_use",
            "id": tc.get("id", ""),
            "name": fn.get("name", ""),
            "input": args,
        })

    stop_reason = "end_turn"
    if oai_msg.get("tool_calls"):
        stop_reason = "tool_use"
    elif choice.get("finish_reason") == "length":
        stop_reason = "max_tokens"
    elif choice.get("finish_reason") == "stop":
        stop_reason = "end_turn"

    return {
        "id": msg_id,
        "type": "message",
        "role": "assistant",
        "content": content,
        "model": model,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        },
    }


# ─── Streaming: OpenAI SSE → Anthropic SSE ─────────────────

async def stream_anthropic(provider, openai_body: dict, model: str, response_handler):
    """
    从 DeepSeek 获取 SSE 流，转为 Anthropic SSE 事件流。

    response_handler 是一个 Tornado RequestHandler，支持 write() 和 flush()。
    """
    msg_id = f"msg_{uuid.uuid4().hex[:24]}"
    full_text = ""
    tool_calls = {}  # {index: {id, name, input_dict}}
    input_tokens = output_tokens = 0
    content_index = 0
    _sse_headers_set = False

    def _ensure_sse_headers():
        nonlocal _sse_headers_set
        if not _sse_headers_set:
            response_handler.set_header("Content-Type", "text/event-stream")
            response_handler.set_header("Cache-Control", "no-cache")
            response_handler.set_header("Connection", "keep-alive")
            response_handler.set_header("X-Accel-Buffering", "no")
            _sse_headers_set = True

    def _sse(event_type: str, data: dict):
        _ensure_sse_headers()
        response_handler.write(f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n")
        response_handler.flush()

    # 延迟发送 message_start，直到成功获取首个 API 事件
    _message_started = False

    def _ensure_message_start():
        nonlocal _message_started
        if not _message_started:
            _sse("message_start", {
                "type": "message_start",
                "message": {
                    "id": msg_id, "type": "message", "role": "assistant",
                    "content": [], "model": model, "stop_reason": None,
                    "stop_sequence": None, "usage": {"input_tokens": 0, "output_tokens": 0},
                }
            })
            _message_started = True

    # Content block tracking
    text_block_opened = False
    tool_block_opened = set()

    async for event in provider.stream_chat_completion(openai_body):
        _ensure_message_start()
        if event.get("_done"):
            break

        if "usage" in event:
            input_tokens = event["usage"].get("prompt_tokens", 0)
            output_tokens = event["usage"].get("completion_tokens", 0)

        for choice in event.get("choices", []):
            delta = choice.get("delta", {})
            finish = choice.get("finish_reason", "")

            text = delta.get("content") or ""
            if text:
                if not text_block_opened:
                    text_block_opened = True
                    _sse("content_block_start", {
                        "type": "content_block_start", "index": content_index,
                        "content_block": {"type": "text", "text": ""}
                    })
                    content_index += 1
                full_text += text
                _sse("content_block_delta", {
                    "type": "content_block_delta", "index": content_index - 1,
                    "delta": {"type": "text_delta", "text": text}
                })

            for tc in delta.get("tool_calls", []):
                idx = tc.get("index", 0)
                if idx not in tool_calls:
                    tc_id = tc.get("id", "") or f"toolu_{uuid.uuid4().hex[:16]}"
                    fn_name = tc.get("function", {}).get("name", "")
                    tool_calls[idx] = {"id": tc_id, "name": fn_name, "input_str": ""}
                    tool_block_opened.add(idx)
                    _sse("content_block_start", {
                        "type": "content_block_start", "index": idx + (1 if text_block_opened else 0),
                        "content_block": {"type": "tool_use", "id": tc_id, "name": fn_name, "input": {}}
                    })
                fn = tc.get("function", {})
                args = fn.get("arguments", "")
                if args:
                    tool_calls[idx]["input_str"] += args

            if finish == "tool_calls":
                for idx, tc_info in tool_calls.items():
                    try:
                        input_data = json.loads(tc_info["input_str"])
                    except json.JSONDecodeError:
                        input_data = {}
                    _sse("content_block_delta", {
                        "type": "content_block_delta",
                        "index": idx + (1 if text_block_opened else 0),
                        "delta": {"type": "input_json_delta", "partial_json": ""}
                    })
                    _sse("content_block_stop", {
                        "type": "content_block_stop",
                        "index": idx + (1 if text_block_opened else 0),
                    })

    # Close text block
    if text_block_opened:
        _sse("content_block_stop", {
            "type": "content_block_stop", "index": 0,
        })

    # message_delta
    stop_reason = "end_turn"
    if tool_calls:
        stop_reason = "tool_use"
    _sse("message_delta", {
        "type": "message_delta",
        "delta": {"stop_reason": stop_reason, "stop_sequence": None},
        "usage": {"output_tokens": max(output_tokens, len(full_text) // 3)},
    })

    # message_stop
    _sse("message_stop", {"type": "message_stop"})
