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


def frange(start: float, stop: float, step: float = 1.0) -> list[float]:
    """浮点等差数列（含端点）

    Args:
        start: 起始值（含）
        stop: 终止值（含）
        step: 步长，须非 0；可为负值

    Returns:
        从 ``start`` 起、按 ``step`` 步进到不超过 ``stop`` 的值，
        末尾若未命中 ``stop`` 则追加补上，保证 ``stop`` 一定被包含
        （末段间隔可能不足一个步长）

    Raises:
        ValueError: ``step`` 为 0
    """
    if step == 0:
        raise ValueError("step 不能为 0")
    eps = 1e-12
    n = int((stop - start) / step + eps * max(1.0, abs((stop - start) / step)))
    n = max(0, n)
    result = [round(start + i * step, 12) for i in range(n + 1)]
    if result and abs(result[-1] - stop) > 1e-9:
        result.append(round(stop, 12))
    return result