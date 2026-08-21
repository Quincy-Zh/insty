"""通用工具函数"""

from __future__ import annotations

_INVALID_THRESHOLD = 9.9e37


def is_invalid_reading(value: float) -> bool:
    """判断 VISA 读数是否为无效值（>= 9.9e37 表示 INFinity / 错误）"""
    return value >= _INVALID_THRESHOLD


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