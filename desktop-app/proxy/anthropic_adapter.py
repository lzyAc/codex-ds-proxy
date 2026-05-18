"""
Anthropic Messages API ↔ OpenAI Chat Completions 格式转换

修复：超长对话中 tool_call_id 校验失败问题（"insufficient tool messages following tool_calls"）

支持 Claude Desktop / Claude CLI / 任意 Anthropic SDK 客户端
通过代理将请求转发至 DeepSeek。
"""

import json
import time
import uuid
from collections import Counter


# ─── 模型名映射 ────────────────────────────────────────────

CLAUDE_MODEL_MAP = {
    # ── 标准模型（普通上下文）──
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
    "claude-opus-4.6": "deepseek-v4-pro",
    "claude-sonnet-4.6": "deepseek-v4-pro",
    "claude-haiku-4.6": "deepseek-v4-flash",
    "claude-opus-4.7": "deepseek-v4-pro",
    "claude-sonnet-4.7": "deepseek-v4-pro",
    # ── 1M 上下文模型（不限制 max_tokens）──
    "claude-opus-4.6-1m": "deepseek-v4-pro",
    "claude-sonnet-4.6-1m": "deepseek-v4-pro",
    "claude-haiku-4.6-1m": "deepseek-v4-flash",
    "claude-opus-4.7-1m": "deepseek-v4-pro",
    "claude-sonnet-4.7-1m": "deepseek-v4-pro",
}

# 1M 上下文模式前缀
LARGE_CONTEXT_PREFIXES = ("claude-opus-4.6-1m", "claude-sonnet-4.6-1m",
                          "claude-haiku-4.6-1m", "claude-opus-4.7-1m",
                          "claude-sonnet-4.7-1m")

def is_large_context_model(model: str) -> bool:
    """判断是否为 1M 上下文模式模型"""
    return model in LARGE_CONTEXT_PREFIXES or model.endswith("-1m")

def map_claude_model(model: str, model_mapping: dict = None) -> str:
    """Claude 模型名 → DeepSeek 模型名

    优先级：config.model_mapping > 硬编码 CLAUDE_MODEL_MAP
    """
    # 1. 先查用户自定义映射（config.json model_mapping）
    if model_mapping:
        if model in model_mapping:
            return model_mapping[model]
        for key, target in model_mapping.items():
            if model.startswith(key):
                return target

    # 2. fallback 硬编码映射
    if model in CLAUDE_MODEL_MAP:
        return CLAUDE_MODEL_MAP[model]
    for prefix, target in CLAUDE_MODEL_MAP.items():
        if model.startswith(prefix):
            return target
    return "deepseek-v4-pro"


# ─── Tool 消息配对校验 ─────────────────────────────────────

def _validate_tool_call_pairs(messages: list) -> list:
    """
    验证并修复 tool_call → tool 消息的配对关系。
    DeepSeek API 严格要求每个 assistant.tool_calls 后面跟着对应的 tool 消息。

    常见问题场景：
    - tool_use_id 为空 → 跳过无效 tool 消息
    - tool 消息中 tool_call_id 不存在于 pending 中 → 跳过
    - user 消息出现但还有未响应的 tool_calls → 插入空 tool 响应
    - 连续多个 assistant 消息中间没有 tool → 合并不带 tool_calls 的 assistant
    """
    fixed = []
    pending_ids = {}  # tool_call_id -> count of occurrences needed

    for msg in messages:
        role = msg.get("role", "")

        if role == "assistant" and msg.get("tool_calls"):
            # 过滤掉没有 id 的 tool_calls
            valid_calls = []
            for tc in msg.get("tool_calls", []):
                tc_id = tc.get("id", "")
                if tc_id:
                    valid_calls.append(tc)
            if valid_calls:
                msg["tool_calls"] = valid_calls
                for tc in valid_calls:
                    tc_id = tc["id"]
                    pending_ids[tc_id] = pending_ids.get(tc_id, 0) + 1
                fixed.append(msg)
            else:
                # 所有 tool_calls 都没有 id → 降级为纯文本
                new_msg = dict(msg)
                new_msg.pop("tool_calls", None)
                if new_msg.get("content") is None:
                    new_msg["content"] = ""
                fixed.append(new_msg)

        elif role == "tool":
            tc_id = msg.get("tool_call_id", "")
            if not tc_id or tc_id not in pending_ids:
                # 无效 tool_call_id → 跳过
                continue
            # 消耗一个 pending
            pending_ids[tc_id] -= 1
            if pending_ids[tc_id] <= 0:
                del pending_ids[tc_id]
            fixed.append(msg)

        elif role == "user" and pending_ids:
            # user 消息出现但还有未响应的 tool_calls
            # 插入空 tool 响应来满足 DeepSeek 校验
            for tc_id in list(pending_ids.keys()):
                fixed.append({"role": "tool", "tool_call_id": tc_id, "content": ""})
            pending_ids.clear()
            fixed.append(msg)

        else:
            fixed.append(msg)

    # 最后还有未消耗的 pending → 追加空 tool 消息
    for tc_id in list(pending_ids.keys()):
        fixed.append({"role": "tool", "tool_call_id": tc_id, "content": ""})
    pending_ids.clear()

    return fixed


def _merge_adjacent_assistant(messages: list) -> list:
    """
    合并相邻的 assistant 消息（DeepSeek 不接受连续 assistant 消息）。
    """
    if not messages:
        return messages
    merged = [messages[0]]
    for msg in messages[1:]:
        last = merged[-1]
        if last.get("role") == "assistant" and msg.get("role") == "assistant":
            # 合并 tool_calls
            last_tc = last.get("tool_calls", [])
            msg_tc = msg.get("tool_calls", [])
            if last_tc or msg_tc:
                last["tool_calls"] = last_tc + msg_tc
            # 合并文本内容（保留非空的）
            last_content = last.get("content") or ""
            msg_content = msg.get("content") or ""
            if last_content or msg_content:
                last["content"] = (last_content + "\n" + msg_content).strip()
            else:
                last["content"] = None
        else:
            merged.append(msg)
    return merged


# ─── Request: Anthropic → OpenAI ───────────────────────────

def anthropic_to_openai(body: dict, model_mapping: dict = None) -> dict:
    """将 Anthropic Messages 请求转为 OpenAI Chat Completions 请求

    model_mapping: 用户自定义模型映射（来自 config.json model_mapping），优先于硬编码映射"""

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
                    tc_id = block.get("id", "").strip()
                    if not tc_id:
                        tc_id = f"tu_{uuid.uuid4().hex[:12]}"
                    tool_calls.append({
                        "id": tc_id,
                        "type": "function",
                        "function": {
                            "name": block.get("name", ""),
                            "arguments": json.dumps(input_data, ensure_ascii=False)
                        }
                    })
                elif btype == "tool_result":
                    content_raw = block.get("content", "")
                    if isinstance(content_raw, list):
                        content_strs = []
                        for p in content_raw:
                            if isinstance(p, dict):
                                content_strs.append(p.get("text", json.dumps(p, ensure_ascii=False)))
                            else:
                                content_strs.append(str(p))
                        content_str = " ".join(content_strs)
                    else:
                        content_str = str(content_raw) if content_raw is not None else ""
                    tool_results.append({
                        "role": "tool",
                        "tool_call_id": block.get("tool_use_id", ""),
                        "content": content_str,
                    })
                elif btype == "image":
                    text_parts.append("[图片]")
                elif btype == "thinking":
                    text_parts.append(block.get("thinking", ""))
                elif btype == "tool_call" or btype == "function_call":
                    fc_input = block.get("input", block.get("arguments", {}))
                    if isinstance(fc_input, str):
                        try:
                            fc_input = json.loads(fc_input)
                        except json.JSONDecodeError:
                            fc_input = {"raw": fc_input}
                    fc_id = block.get("id", "").strip()
                    if not fc_id:
                        fc_id = f"fc_{uuid.uuid4().hex[:12]}"
                    tool_calls.append({
                        "id": fc_id,
                        "type": "function",
                        "function": {
                            "name": block.get("name", ""),
                            "arguments": json.dumps(fc_input, ensure_ascii=False)
                        }
                    })

            # 合并：同一原始消息的 text + tool_calls → 一条 assistant 消息
            if tool_calls:
                assistant_msg = {"role": "assistant", "tool_calls": tool_calls}
                text_content = " ".join(filter(None, text_parts))
                assistant_msg["content"] = text_content if text_content else None
                messages.append(assistant_msg)
            elif text_parts:
                messages.append({"role": role, "content": " ".join(filter(None, text_parts))})

            # tool_results 以原始顺序追加
            messages.extend(tool_results)
        else:
            messages.append({"role": role, "content": str(content)})

    # tool_call 配对校验 + 相邻 assistant 合并
    messages = _validate_tool_call_pairs(messages)
    messages = _merge_adjacent_assistant(messages)

    chat = {
        "model": map_claude_model(body.get("model", ""), model_mapping),
        "messages": messages,
    }

    # max_tokens → max_tokens
    # 1M 上下文模式：不限制 max_tokens，完全透传
    # 普通模式：限制 128K（DeepSeek V4 最大输出）
    if "max_tokens" in body:
        orig_model = body.get("model", "")
        if is_large_context_model(orig_model):
            chat["max_tokens"] = body["max_tokens"]
        else:
            chat["max_tokens"] = min(body["max_tokens"], 131072)

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

    # 多轮关闭 thinking（DeepSeek 需要多轮推理上下文不带 thinking）
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

    received_any = False
    async for event in provider.stream_chat_completion(openai_body):
        _ensure_message_start()
        if event.get("_done"):
            break
        received_any = True

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
                    # 先发送完整参数的 delta（覆盖 content_block_start 的空 input）
                    _sse("content_block_delta", {
                        "type": "content_block_delta",
                        "index": idx + (1 if text_block_opened else 0),
                        "delta": {"type": "input_json_delta", "partial_json": json.dumps(input_data, ensure_ascii=False)}
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

    # message_stop - 仅在收到了有效事件时才发
    if received_any:
        _sse("message_stop", {"type": "message_stop"})
    return input_tokens, output_tokens
