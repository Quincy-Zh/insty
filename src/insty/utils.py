"""通用工具函数"""

from __future__ import annotations

from typing import Any


def pick_keys(mapping: dict[str, Any], keys: list[str]) -> tuple[Any, ...]:
    """从映射中摘出指定 key 对应的值，key 比较忽略大小写

    Args:
        mapping: 源映射（如 ``**kwargs`` 生成的字典）
        keys: 要摘出的 key 列表

    Returns:
        按 ``keys`` 顺序排列的元组；未命中的 key 对应 ``None``
    """
    lower_map = {k.lower(): v for k, v in mapping.items()}
    return tuple(lower_map.get(k.lower()) for k in keys)