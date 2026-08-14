"""仪器类型抽象基类：按仪器类型定义特有接口

每种仪器类型对应一个抽象基类，定义该类型通用的操作接口。
具体驱动继承相应的类型基类，实现特定型号的 SCPI 命令。
"""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar


@dataclass(frozen=True)
class InstrumentInfo:
    """已发现仪器的完整信息"""
    address: str
    label: str
    inst_type: InstrumentType
    supported: tuple[str, ...] = ()

    def supports(
        self,
        inst_type: InstrumentType | str | tuple[InstrumentType, ...],
        type_: str,
    ) -> bool:
        """判断是否支持指定类型的能力

        Args:
            inst_type: 仪器类型（可为单个或元组，字符串按类型名解析）
            type_: 能力名（如 "VOLTAGE_DC"）
        """
        if isinstance(inst_type, str):
            inst_type = InstrumentType(inst_type.lower())
        types = inst_type if isinstance(inst_type, tuple) else (inst_type,)
        return self.inst_type in types and type_.upper() in self.supported

    def to_dict(self) -> dict[str, Any]:
        return {
            "address": self.address,
            "label": self.label,
            "inst_type": self.inst_type.value,
            "supported": self.supported,
        }


# ═══════════════════════════════════════════════════════════════════════
# 类型抽象基类
# ═══════════════════════════════════════════════════════════════════════


class InstrumentBase(ABC):
    """仪器基类：所有驱动共用的生命周期接口"""

    @abstractmethod
    def close(self) -> None:
        """关闭仪器连接"""
        raise NotImplementedError


class PowerSupplyBase(InstrumentBase):
    """数字电源类型抽象基类

    支持接口：
        set_voltage(volt: float, channel: int = 1) -> None
        output_enable(channel: int = 0) -> None
        output_disable(channel: int = 0) -> None
    """

    @abstractmethod
    def set_voltage(self, volt: float, channel: int = 1) -> None:
        """设置输出电压"""
        raise NotImplementedError

    @abstractmethod
    def output_enable(self, channel: int = 0) -> None:
        """使能输出。channel=0 表示全部通道"""
        raise NotImplementedError

    @abstractmethod
    def output_disable(self, channel: int = 0) -> None:
        """关闭输出。channel=0 表示全部通道"""
        raise NotImplementedError

    def close(self) -> None:
        """关闭仪器连接，子类可重写"""


class ThermalChamberBase(InstrumentBase):
    """高低温发生器类型抽象基类

    支持接口：
        set_temperature(temp: float, soak: int = 15) -> None
        wait(timeout: int = 150) -> bool
        get_temperature() -> Optional[float]
    """

    @abstractmethod
    def set_temperature(self, temp: float, soak: int = 15) -> None:
        """设置目标温度，soak 为浸润时间（秒）"""
        raise NotImplementedError

    @abstractmethod
    def wait(self, timeout: int = 150) -> bool:
        """等待温度稳定，超时返回 False"""
        raise NotImplementedError

    @abstractmethod
    def get_temperature(self) -> float | None:
        """读取当前温度"""
        raise NotImplementedError

    def get_status(self) -> bool:
        raise NotImplementedError

    def prepare(self) -> ThermalChamberBase:
        """开机检查与初始化配置，子类可重写"""
        return self

    def reset(self)-> ThermalChamberBase:
        """重置，子类可重写"""
        return self

    def close(self) -> None:
        pass


class WaveformGeneratorBase(InstrumentBase):
    """信号发生器类型抽象基类

    支持接口：
        configure(wave: str, freq: float, vpp: float, offset: float, **kwargs) -> None
        output_enable() -> None
        output_disable() -> None
        set_frequency(freq: float) -> None
        set_amplitude(vpp: float) -> None
        set_offset(offset: float) -> None
    """

    @abstractmethod
    def configure(
        self,
        wave: str,
        freq: float,
        vpp: float,
        offset: float,
        **kwargs,
    ) -> None:
        """配置波形及参数。wave: DC/SIN/SQU/RAMP/TRI"""
        raise NotImplementedError

    @abstractmethod
    def output_enable(self) -> None:
        """使能输出"""
        raise NotImplementedError

    @abstractmethod
    def output_disable(self) -> None:
        """关闭输出"""
        raise NotImplementedError

    def set_frequency(self, freq: float) -> None:
        """设置频率（Hz），子类可重写"""

    def set_amplitude(self, vpp: float) -> None:
        """设置幅值（Vpp），子类可重写"""

    def set_offset(self, offset: float) -> None:
        """设置偏置（V），子类可重写"""

    def close(self) -> None:
        pass


class DMMBase(InstrumentBase):
    """数字万用表类型抽象基类

    支持接口：
        read_voltage(params: dict = None) -> float
        read_current(params: dict = None) -> float
        configure(params: dict) -> None
    """

    @abstractmethod
    def read_voltage(self, params: dict | None = None) -> float:
        """读取电压（直流）。params 可包含 range、power_line_cycles、filter 等"""
        raise NotImplementedError

    @abstractmethod
    def read_current(self, params: dict | None = None) -> float:
        """读取电流（直流）"""
        raise NotImplementedError

    def configure(self, params: dict | None = None) -> None:
        """配置测量参数，子类可重写"""

    def close(self) -> None:
        pass


class OscilloscopeBase(InstrumentBase):
    """示波器类型抽象基类

    支持接口：
        read_frequency() -> float
        read_duty_cycle() -> float
        read_pulse() -> float
        execute(mode: str) -> None
        screenshot() -> bytes
    """

    @abstractmethod
    def read_frequency(self) -> float:
        """测量波形频率（Hz）"""
        raise NotImplementedError

    @abstractmethod
    def read_duty_cycle(self) -> float:
        """测量波形占空比（比值 0~1）"""
        raise NotImplementedError

    @abstractmethod
    def read_pulse(self) -> float:
        """测量波形脉宽（s）"""
        raise NotImplementedError

    @abstractmethod
    def execute(self, mode: str) -> None:
        """切换运行模式：single/run/stop"""
        raise NotImplementedError

    @abstractmethod
    def screenshot(self) -> bytes:
        """截屏，返回图片字节数据"""
        raise NotImplementedError

    def close(self) -> None:
        pass


class FrequencyCounterBase(InstrumentBase):
    """频率计类型抽象基类

    支持接口：
        read_frequency() -> float
        read_duty_cycle() -> float
    """

    @abstractmethod
    def read_frequency(self) -> float:
        """测量波形频率（Hz）"""
        raise NotImplementedError

    @abstractmethod
    def read_duty_cycle(self) -> float:
        """测量波形占空比（比值 0~1）"""
        raise NotImplementedError

    def close(self) -> None:
        pass


# ═══════════════════════════════════════════════════════════════════════
# 统一注册与工厂
# ═══════════════════════════════════════════════════════════════════════


class InstrumentType(enum.Enum):
    """仪器类型枚举，用于注册表分类"""
    POWER_SUPPLY = "power_supply"
    THERMAL_CHAMBER = "thermal_chamber"
    WAVEFORM_GENERATOR = "waveform_generator"
    DMM = "dmm"
    OSCILLOSCOPE = "oscilloscope"
    FREQUENCY_COUNTER = "frequency_counter"


_TypeBaseMap = {
    InstrumentType.POWER_SUPPLY: PowerSupplyBase,
    InstrumentType.THERMAL_CHAMBER: ThermalChamberBase,
    InstrumentType.WAVEFORM_GENERATOR: WaveformGeneratorBase,
    InstrumentType.DMM: DMMBase,
    InstrumentType.OSCILLOSCOPE: OscilloscopeBase,
    InstrumentType.FREQUENCY_COUNTER: FrequencyCounterBase,
}


class InstrumentRegistry:
    """仪器注册表：按类型组织的驱动注册"""

    _registry: ClassVar[dict[str, tuple[InstrumentType, tuple[str, ...], type]]] = {}

    @classmethod
    def register(
        cls,
        name: str,
        inst_type: InstrumentType,
        supported: tuple[str, ...],
        driver_cls: type,
    ) -> None:
        key = name.upper()
        if key in cls._registry:
            raise ValueError(f"Instrument '{key}' already registered")
        supported_upper = tuple(s.upper() for s in supported)
        cls._registry[key] = (inst_type, supported_upper, driver_cls)

    # ── 每类显式注册方法 ─────────────────────────────────────────
    # 各类驱动通过对应的 register_* 显式注入，无需再传 InstrumentType 枚举。

    @classmethod
    def register_power_supply(
        cls,
        name: str,
        driver_cls: type,
        supported: tuple[str, ...],
    ) -> None:
        cls.register(name, InstrumentType.POWER_SUPPLY, supported, driver_cls)

    @classmethod
    def register_thermal_chamber(
        cls,
        name: str,
        driver_cls: type,
        supported: tuple[str, ...],
    ) -> None:
        cls.register(name, InstrumentType.THERMAL_CHAMBER, supported, driver_cls)

    @classmethod
    def register_waveform_generator(
        cls,
        name: str,
        driver_cls: type,
        supported: tuple[str, ...],
    ) -> None:
        cls.register(name, InstrumentType.WAVEFORM_GENERATOR, supported, driver_cls)

    @classmethod
    def register_dmm(
        cls,
        name: str,
        driver_cls: type,
        supported: tuple[str, ...],
    ) -> None:
        cls.register(name, InstrumentType.DMM, supported, driver_cls)

    @classmethod
    def register_oscilloscope(
        cls,
        name: str,
        driver_cls: type,
        supported: tuple[str, ...],
    ) -> None:
        cls.register(name, InstrumentType.OSCILLOSCOPE, supported, driver_cls)

    @classmethod
    def register_frequency_counter(
        cls,
        name: str,
        driver_cls: type,
        supported: tuple[str, ...],
    ) -> None:
        cls.register(name, InstrumentType.FREQUENCY_COUNTER, supported, driver_cls)

    @classmethod
    def get_driver(cls, name: str) -> type:
        res = cls._registry.get(name.upper())
        if res is None:
            raise ValueError(f"Unknown instrument: {name}")
        return res[2]

    @classmethod
    def get_info(cls, name: str) -> tuple[InstrumentType, tuple[str, ...]]:
        res = cls._registry.get(name.upper())
        if res is None:
            raise ValueError(f"Unknown instrument: {name}")
        return res[0], res[1]


def make_instrument(name: str, resource) -> PowerSupplyBase | ThermalChamberBase | WaveformGeneratorBase | DMMBase | OscilloscopeBase | FrequencyCounterBase:
    """工厂函数：创建仪器实例"""
    driver_cls = InstrumentRegistry.get_driver(name)
    return driver_cls(resource)