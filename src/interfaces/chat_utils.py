"""ChatEngine 单例 + 工具函数（供 web_api.py 和 cards.py 共享）。

避免 cards.py → web_api.py 的循环依赖。
"""
from __future__ import annotations

_chat_engine = None


def get_chat_engine():
    """获取 ChatEngine 单例实例（懒初始化）。"""
    global _chat_engine
    if _chat_engine is None:
        from src.ai.chat_engine import ChatEngine  # noqa: PLC0415
        _chat_engine = ChatEngine()
    return _chat_engine


def normalize_chat_top_k(raw_value, default: int = 5) -> int:
    """规范化智能问答检索条数，避免非法值或过量检索。"""
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, 20))
