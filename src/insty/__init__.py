"""智能仪器仪表

提供仪器类型抽象基类、每类显式注册（register_*）、传输后端、仪器管理器、TestBench 等功能。

驱动在各自模块末尾通过 ``InstrumentRegistry.register_*`` 显式注册
（如 ``register_oscilloscope("ZHIYUAN::ZDS1104", ZDS1104, supported=...)``）。
导入 ``insty`` 时由 ``drivers`` 包级联导入各驱动以完成注册。

测试报告与单位换算（``Report``）在 ``utils.report``，与仪器无关。
"""

import logging

__version__ = "0.1.0"

logging.getLogger(__name__).addHandler(logging.NullHandler())

# 导入即触发仪器模块的注册
from . import visa_based_instrument
from .bench import (
    DMMRole,
    FrequencyCounterRole,
    OscilloscopeRole,
    PowerSupplyRole,
    TestBench,
    ThermalChamberRole,
    WaveformGeneratorRole,
    frange,
)
from .device_table import DeviceTable
from .instrument_types import (
    DMMBase,
    FrequencyCounterBase,
    InstrumentBase,
    InstrumentInfo,
    InstrumentRegistry,
    InstrumentType,
    OscilloscopeBase,
    PowerSupplyBase,
    ThermalChamberBase,
    WaveformGeneratorBase,
    make_instrument,
)
from .manager import InstrumentManager
from .transport_backend import TransportBackend
from .visa_backend import VisaTransportBackend

__all__ = [
    "DMMBase",
    "DMMRole",
    "DeviceTable",
    "FrequencyCounterBase",
    "FrequencyCounterRole",
    "InstrumentBase",
    "InstrumentInfo",
    "InstrumentManager",
    "InstrumentRegistry",
    "InstrumentType",
    "OscilloscopeBase",
    "OscilloscopeRole",
    "PowerSupplyBase",
    "PowerSupplyRole",
    "TestBench",
    "ThermalChamberBase",
    "ThermalChamberRole",
    "TransportBackend",
    "VisaTransportBackend",
    "WaveformGeneratorBase",
    "WaveformGeneratorRole",
    "frange",
    "make_instrument",
]
