"""仪器类型抽象基类:按仪器类型定义特有接口

每种仪器类型对应一个抽象基类, 定义该类型通用的操作接口。
具体驱动继承相应的类型基类, 实现特定型号的 SCPI 命令。
"""

from __future__ import annotations

import enum
import weakref
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from typing_extensions import Self

if TYPE_CHECKING:
    from .manager import InstrumentManager


@dataclass(frozen=True)
class InstrumentInfo:
    """已发现仪器的完整信息"""

    address: str
    label: str
    inst_type: InstrumentType
    supported: tuple[str, ...] = ()

    def supports(
        self,
        inst_type: InstrumentType | str,
        type_: str,
    ) -> bool:
        """判断是否支持指定类型的能力

        Args:
            inst_type: 仪器类型(字符串按类型名解析)
            type_: 能力名(如 "VOLTAGE_DC")
        """
        if isinstance(inst_type, str):
            inst_type = InstrumentType(inst_type.lower())
        return self.inst_type == inst_type and type_.upper() in self.supported

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


class Instrument(ABC):
    """仪器基类:所有驱动共用的生命周期接口"""

    # 设备信息(地址/label/类型/能力), 由 InstrumentManager 打开连接时注入;
    # 驱动本身不感知, 未通过管理器打开的实例该属性为 None
    info: InstrumentInfo | None = None

    # 由 InstrumentManager 打开连接时经 _attach_manager 注入的弱引用,
    # 供 close() 模板方法回调管理器以移除连接缓存; 未托管实例为 None
    _manager: weakref.ReferenceType[InstrumentManager] | None = None

    def _attach_manager(self, manager) -> None:
        """注入管理器弱引用, 供 :meth:`close` 模板方法回调

        Args:
            manager: 托管该实例的 :class:`~insty.manager.InstrumentManager`
        """
        self._manager = weakref.ref(manager)

    def close(self) -> None:
        """关闭仪器连接（模板方法）

        依次调用 :meth:`_close` 关闭底层连接，并在由
        ``InstrumentManager`` 打开时通知其移除连接缓存。
        """
        self._close()
        if self._manager is not None:
            mgr = self._manager()
            if mgr is not None:
                mgr._on_inst_closed(self)

    @abstractmethod
    def _close(self) -> None:
        """关闭底层连接，由具体驱动/混入类实现"""
        raise NotImplementedError

    @abstractmethod
    def beep(self) -> None:
        """发出设备提示音(如支持)"""
        raise NotImplementedError

    def get_errors(self) -> list[str]:
        """查询设备错误队列

        每条格式为 ``<错误码>,<错误信息>``); 不支持或无需查询时返回空列表。
        """
        return []

    def setup(self, **kwargs) -> Self:
        """初始化仪器(如连接参数、运行模式), 子类可重写"""
        return self


class PowerSupply(Instrument):
    """数字电源类型抽象基类

    支持接口:
        channels: int — 输出通道数（只读）
        set_voltage(volt: float, channel: int = 1) -> Self
        output_enable(channel: int = 0) -> Self
        output_disable(channel: int = 0) -> Self
    """

    @property
    def channels(self) -> int:
        """输出通道数（只读）"""
        return 1

    @abstractmethod
    def set_voltage(self, volt: float, channel: int = 1) -> Self:
        """设置输出电压并自动使能输出, 支持链式调用"""
        raise NotImplementedError

    @abstractmethod
    def output_enable(self, channel: int = 0) -> Self:
        """使能输出。channel=0 表示全部通道"""
        raise NotImplementedError

    @abstractmethod
    def output_disable(self, channel: int = 0) -> Self:
        """关闭输出。channel=0 表示全部通道"""
        raise NotImplementedError

    def _close(self) -> None:
        """关闭仪器连接, 子类可重写"""


class ThermalChamber(Instrument):
    """高低温发生器类型抽象基类

    支持接口:
        set_temperature(temp: float, soak: int = 15) -> None
        wait(timeout: int = 150) -> bool
        get_temperature() -> Optional[float]
        setup() -> Self
        execute(action: str) -> Self
        ready() -> bool
        get_errors() -> list[str]
    """

    @abstractmethod
    def set_temperature(self, temp: float, soak: int = 15) -> None:
        """设置目标温度, soak 为浸润时间(秒)"""
        raise NotImplementedError

    @abstractmethod
    def wait(self, timeout: int = 150) -> bool:
        """等待温度稳定, 超时返回 False"""
        raise NotImplementedError

    @abstractmethod
    def get_temperature(self) -> float | None:
        """读取当前温度"""
        raise NotImplementedError

    def prepare(self) -> Self:
        """开机检查与初始化配置, 子类可重写"""
        return self

    def reset(self) -> Self:
        """重置, 子类可重写"""
        return self

    def setup(self, **kwargs) -> Self:
        """初始化(如停止 cycling、使能 DUT mode), 子类可重写"""
        return self

    def execute(self, action: str) -> Self:
        """执行动作(如 head up / head down), 子类可重写"""
        return self

    def ready(self) -> bool:
        """设备是否就绪(如 Head 已下压到位), 子类可重写"""
        return False

    def _close(self) -> None:
        pass


class WaveformGenerator(Instrument):
    """信号发生器类型抽象基类

    支持接口:
        channels: int — 输出通道数（只读）
        setup(wave: str, *, channel: int = 1, **kwargs) -> Self
        output_enable(channel: int = 1) -> Self
        output_disable(channel: int = 1) -> Self
        set_frequency(freq: float, channel: int = 1) -> Self
        set_amplitude(vpp: float, channel: int = 1) -> Self
        set_offset(offset: float, channel: int = 1) -> Self
        set_phase(phase: float, channel: int = 1) -> Self
        set_output_load(load: float | str, channel: int = 1) -> Self
    """

    @property
    def channels(self) -> int:
        """输出通道数（只读）"""
        return 1

    def setup(self, wave: str, *, channel: int = 1, **kwargs) -> Self:
        """初始化并配置波形及参数

        Args:
            wave: 波形类型, 不区分大小写: SIN - 正弦波; SQU - 方波; TRI - 三角波; RAMP - 斜坡波; DC - 直流电平
            channel: 操作通道号(多通道型号 1~N, 越界抛 ValueError)
            freq: 频率(Hz), 1μHz 起, 须为正; 非 DC 波形必选, DC 波形忽略
            vpp: 峰峰值幅度(Vpp), 1mVpp 起, 须为正; 非 DC 波形必选, DC 波形忽略
            offset: 直流偏置(V); 非 DC 波形必选, 须满足 |offset| < Vmax - vpp/2(Vmax 为当前终止负载下的最大峰值电压: 高阻 10V、50Ω 5V); DC 波形必选, 为直流电平值, 须在 ±Vmax 内
            phase: 初始相位, 范围 -360~+360(单位由 UNIT:ANGLe 决定, 默认度), 默认 0; DC 波形下忽略
            duty_cycle: 占空比(%), 仅 SQU/RAMP 波形生效: SQU 为占空比 0.01~99.99(受最小脉宽限制, 手册默认 50); RAMP 为对称性 0~100(手册默认 100)
            output_load: 输出终止负载(Ω 或 'INFinity'), 可选; 缺省用当前负载(默认高阻)

        Returns:
            Self: 支持链式调用
        """
        return self

    @abstractmethod
    def output_enable(self, channel: int = 1) -> Self:
        """使能输出。channel=0 表示全部通道"""
        raise NotImplementedError

    @abstractmethod
    def output_disable(self, channel: int = 1) -> Self:
        """关闭输出。channel=0 表示全部通道"""
        raise NotImplementedError

    def set_frequency(self, freq: float, channel: int = 1) -> Self:
        """设置频率(Hz), 子类可重写"""
        return self

    def set_amplitude(self, vpp: float, channel: int = 1) -> Self:
        """设置幅值(Vpp), 子类可重写"""
        return self

    def set_offset(self, offset: float, channel: int = 1) -> Self:
        """设置偏置(V), 子类可重写"""
        return self

    def set_phase(self, phase: float, channel: int = 1) -> Self:
        """设置初始相位(度), 子类可重写"""
        return self

    def set_output_load(self, load: float | str, channel: int = 1) -> Self:
        """设置输出终止负载(Ω 或 'INFinity'), 子类可重写"""
        return self

    def _close(self) -> None:
        pass


class DMM(Instrument):
    """数字万用表类型抽象基类

    支持接口:
        read_voltage(params: dict = None) -> Optional[float]
        read_current(params: dict = None) -> Optional[float]
    """

    @abstractmethod
    def read_voltage(self, params: dict | None = None) -> float | None:
        """读取电压(直流), 测量失败时返回 None。params 可包含 range、power_line_cycles、filter 等"""
        raise NotImplementedError

    @abstractmethod
    def read_current(self, params: dict | None = None) -> float | None:
        """读取电流(直流), 测量失败时返回 None"""
        raise NotImplementedError

    def _close(self) -> None:
        pass


class Oscilloscope(Instrument):
    """示波器类型抽象基类

    支持接口:
        read_frequency() -> Optional[float]
        read_duty_cycle() -> Optional[float]
        read_pulse() -> Optional[float]
        execute(mode: str) -> Self
        screenshot() -> bytes
        setup(**kw) -> Self
    """

    @abstractmethod
    def read_frequency(self) -> float | None:
        """测量波形频率(Hz), 失败时返回 None"""
        raise NotImplementedError

    @abstractmethod
    def read_duty_cycle(self) -> float | None:
        """测量波形占空比(比值 0~1), 失败时返回 None"""
        raise NotImplementedError

    @abstractmethod
    def read_pulse(self) -> float | None:
        """测量波形脉宽(s), 失败时返回 None"""
        raise NotImplementedError

    @abstractmethod
    def execute(self, mode: str) -> Self:
        """切换运行模式:single/run/stop, 支持链式调用"""
        raise NotImplementedError

    @abstractmethod
    def screenshot(self) -> bytes:
        """截屏, 返回图片字节数据"""
        raise NotImplementedError

    def _close(self) -> None:
        pass


class FrequencyCounter(Instrument):
    """频率计类型抽象基类

    支持接口:
        channels: int — 输入通道数（只读）
        setup(*, channel: int = 1, **kwargs) -> Self
        read_frequency(channel: int = 1) -> Optional[float]
        read_duty_cycle(channel: int = 1) -> Optional[float]
    """

    @property
    def channels(self) -> int:
        """输入通道数（只读）"""
        return 1

    def setup(self, *, channel: int = 1, **kwargs) -> Self:
        """配置输入通道参数, 驱动校验参数不合法会抛异常 ValueError

        Args:
            channel: 操作通道号
            coupling: 输入耦合方式, 'AC' 或 'DC', 默认 'DC'
            impedance: 输入阻抗(Ω) , 默认 1e6
            range: 输入电压量程(V), 默认 5
            threshold: 输入阈值电压, 数字(单位V) 或者 字符（百分比） 或者 None(自动), 默认 None
            low_pass_filter: 是否使能低通滤波器, True(开)/False(关), 默认关

        Returns:
            Self: 支持链式调用
        """
        return self

    @abstractmethod
    def read_frequency(self, channel: int = 1) -> float | None:
        """测量波形频率(Hz), 失败时返回 None"""
        raise NotImplementedError

    @abstractmethod
    def read_duty_cycle(self, channel: int = 1) -> float | None:
        """测量波形占空比(比值 0~1), 失败时返回 None"""
        raise NotImplementedError

    def _close(self) -> None:
        pass


# ═══════════════════════════════════════════════════════════════════════
# 统一注册与工厂
# ═══════════════════════════════════════════════════════════════════════


class InstrumentType(enum.Enum):
    """仪器类型枚举, 用于注册表分类"""

    POWER_SUPPLY = "power_supply"
    THERMAL_CHAMBER = "thermal_chamber"
    WAVEFORM_GENERATOR = "waveform_generator"
    DMM = "dmm"
    OSCILLOSCOPE = "oscilloscope"
    FREQUENCY_COUNTER = "frequency_counter"


_TypeMap = {
    InstrumentType.POWER_SUPPLY: PowerSupply,
    InstrumentType.THERMAL_CHAMBER: ThermalChamber,
    InstrumentType.WAVEFORM_GENERATOR: WaveformGenerator,
    InstrumentType.DMM: DMM,
    InstrumentType.OSCILLOSCOPE: Oscilloscope,
    InstrumentType.FREQUENCY_COUNTER: FrequencyCounter,
}


class InstrumentRegistry:
    """仪器注册表:按类型组织的驱动注册"""

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
    # 各类驱动通过对应的 register_* 显式注入, 无需再传 InstrumentType 枚举。

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


def make_instrument(
    name: str, resource
) -> (
    PowerSupply
    | ThermalChamber
    | WaveformGenerator
    | DMM
    | Oscilloscope
    | FrequencyCounter
):
    """工厂函数:创建仪器实例"""
    driver_cls = InstrumentRegistry.get_driver(name)
    return driver_cls(resource)
