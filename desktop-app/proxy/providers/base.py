"""
BaseProvider — 所有模型提供商的抽象基类

扩展新模型只需：
1. 继承 BaseProvider
2. 实现 chat_completion / stream_chat_completion
3. 在 providers/__init__.py 注册
"""

from abc import ABC, abstractmethod


class BaseProvider(ABC):
    """LLM Provider 抽象基类"""

    # 子类必须定义的元信息
    meta = {
        "name": "base",
        "description": "Base provider",
        "models": [],
    }

    def __init__(self, config: dict):
        self.config = config

    # ─── 必须实现 ────────────────────────────────────────

    @abstractmethod
    async def chat_completion(self, body: dict) -> dict:
        """非流式 Chat Completion，返回完整响应体"""
        ...

    @abstractmethod
    async def stream_chat_completion(self, body: dict):
        """流式 Chat Completion，yield SSE 事件 dict（含 _done 标记）"""
        ...

    # ─── 可选覆盖 ────────────────────────────────────────

    def map_model(self, openai_model: str) -> str:
        """将上游模型名映射为 provider 模型名（默认用配置中的 mapping）"""
        mapping = self.config.get("model_mapping", {})
        if openai_model in mapping:
            return mapping[openai_model]
        for prefix, target in mapping.items():
            if openai_model.startswith(prefix):
                return target
        return self.config.get("deepseek_model", self.meta["models"][0]["id"] if self.meta["models"] else "unknown")

    def get_api_key(self) -> str:
        return self.config.get("deepseek_api_key", "")

    def get_base_url(self) -> str:
        return self.config.get("deepseek_base_url", "https://api.deepseek.com")

    def get_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.get_api_key()}",
            "Content-Type": "application/json",
        }

    def build_url(self, path: str) -> str:
        base = self.get_base_url().rstrip("/")
        return f"{base}/{path.lstrip('/')}"

    def convert_tools(self, tools: list) -> list:
        """将 Responses API 工具格式转为 Chat Completions 格式"""
        converted = []
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            tool_type = tool.get("type", "")
            if "function" in tool:
                converted.append(tool)
            elif tool_type == "function" or "name" in tool:
                params = tool.get("parameters") or {}
                if not isinstance(params, dict) or params.get("type") is None:
                    params = {"type": "object", "properties": {}, "required": []}
                converted.append({
                    "type": "function",
                    "function": {
                        "name": tool.get("name", ""),
                        "description": tool.get("description", ""),
                        "parameters": params,
                    }
                })
            elif tool_type in self.unsupported_tools():
                continue
            else:
                # 未知工具类型默认丢弃，避免传到不支持的 API
                continue
        return converted

    def unsupported_tools(self) -> set:
        """返回当前 provider 不支持的工具类型集合"""
        return {"web_search", "web_search_preview", "tool_search",
                "code_interpreter", "file_search", "computer_use_preview",
                "image_generation"}

    def convert_tool_choice(self, tool_choice):
        if isinstance(tool_choice, str):
            return tool_choice
        if isinstance(tool_choice, dict):
            tc_type = tool_choice.get("type", "")
            if tc_type == "function" and "function" not in tool_choice:
                return {"type": "function", "function": {"name": tool_choice.get("name", "")}}
            return tool_choice
        return tool_choice
