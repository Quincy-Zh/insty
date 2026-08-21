"""智能仪器仪表

提供仪器类型抽象基类、每类显式注册（register_*）、传输后端、仪器管理器
（含按类别的访问接口 get_*）等功能。

驱动在各自模块末尾通过 ``InstrumentRegistry.register_*`` 显式注册
（如 ``register_oscilloscope("ZHIYUAN::ZDS1104", ZDS1104, supported=...)``）。
导入 ``insty`` 时由 ``drivers`` 包级联导入各驱动以完成注册。
"""

from __future__ import annotations

import logging

__version__ = "0.1.5"

logging.getLogger(__name__).addHandler(logging.NullHandler())

# 导入即触发仪器模块的注册
from . import visa_based_instrument  # noqa: F401
from .instrument_types import (
    DMM,
    FrequencyCounter,
    Instrument,
    InstrumentInfo,
    InstrumentRegistry,
    InstrumentType,
    Oscilloscope,
    PowerSupply,
    ThermalChamber,
    WaveformGenerator,
    make_instrument,
)
from .manager import InstrumentManager
from .transport_backend import TransportBackend
from .utils import frange, is_invalid_reading
from .visa_backend import VisaTransportBackend

__all__ = [
    "DMM",
    "FrequencyCounter",
    "Instrument",
    "InstrumentInfo",
    "InstrumentManager",
    "InstrumentRegistry",
    "InstrumentType",
    "Oscilloscope",
    "PowerSupply",
    "ThermalChamber",
    "TransportBackend",
    "VisaTransportBackend",
    "WaveformGenerator",
    "frange",
    "is_invalid_reading",
    "make_instrument",
]
