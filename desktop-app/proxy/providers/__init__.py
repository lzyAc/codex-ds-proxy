"""
Provider 注册与工厂

用法:
    from providers import get_provider, list_providers
    p = get_provider("deepseek", config)
"""

from .base import BaseProvider
from .deepseek import DeepSeekProvider

_registry: dict[str, type] = {
    "deepseek": DeepSeekProvider,
}


def register_provider(name: str, cls: type):
    """注册新的 provider（第三方扩展用）"""
    if not issubclass(cls, BaseProvider):
        raise TypeError(f"{cls} must be a subclass of BaseProvider")
    _registry[name] = cls


def get_provider(name: str = None, config: dict = None) -> BaseProvider:
    """根据配置获取 provider 实例"""
    if config is None:
        from config_manager import load_config
        config = load_config()
    name = name or config.get("provider", "deepseek")
    cls = _registry.get(name)
    if cls is None:
        raise ValueError(f"Unknown provider: {name}. Available: {list(_registry.keys())}")
    return cls(config)


def list_providers() -> list[dict]:
    """列出所有已注册的 provider"""
    return [{"id": k, "name": v.meta["name"], "desc": v.meta["description"]}
            for k, v in _registry.items()]
