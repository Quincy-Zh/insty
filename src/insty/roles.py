"""角色封装：把底层仪器实例适配为面向测试脚本的领域接口

脚本通过 ``InstrumentManager.get_*`` 按“角色”获取仪器封装实例，例如：

    mngr = InstrumentManager(device_table=".device_table.json")
    ps = mngr.get_power_supply(address="USB0::...")   # 数字电源
    ps.set_voltage(3.3)                                # 设置电压

    thermal = mngr.get_thermal()                       # 唯一连接的高低温箱
    thermal.set_temperature(-40)
    thermal.wait(timeout=300)                          # 等待温度稳定

    vm = mngr.get_dmm(address="USB0::...")             # 数字万用表
    print(vm.read_voltage())

    osc = mngr.get_oscilloscope(address="USB0::...")   # 示波器
    osc.execute("single")
    freq = osc.read_frequency()

    mngr.close()

角色层（``*Role``）是面向测试脚本的 API 视图层，职责包括：

- 链式调用与参数默认值等业务语义（如 ``set_voltage().output_enable()``）
- 附加设备信息（``address``/``label``/``info``）与统一 ``close()``
- 自定义状态缓存（如 ``WaveformGeneratorRole.cfg``）
- 多类别充当：同一仪器可按多个角色访问（如示波器充当频率计），
  由 ``_ROLES`` 映射表驱动，无需为每种角色新建实例

底层驱动只负责具体型号的 SCPI 命令（接口见 ``instrument_types`` 的类型基类），
两者的重叠部分由角色显式转发或 ``__getattr__`` 透传补齐。
"""

from __future__ import annotations

import logging

from .instrument_types import InstrumentInfo, InstrumentType

logger = logging.getLogger(__name__)


class _RoleBase:
    """角色封装基类

    - 统一持有底层仪器实例与 ``InstrumentInfo``，提供 ``inst``/``address``/``label`` 属性
    - 提供统一的 ``close()``
    - 未显式定义的方法通过 ``__getattr__`` 透传到底层仪器实例，
      因此各角色只保留带“业务逻辑”（参数默认值、链式返回、自定义状态）的接口
    """

    def __init__(self, inst, info: InstrumentInfo) -> None:
        self._inst = inst
        self.info = info

    @property
    def inst(self):
        return self._inst

    @property
    def address(self) -> str:
        return self.info.address

    @property
    def label(self) -> str:
        return self.info.label

    def close(self) -> None:
        try:
            self._inst.close()
        except Exception as ex:
            logger.warning(f"Fail to close {self.label} @ {self.address}: {ex}")

    def __getattr__(self, name: str):
        # 仅当常规属性查找失败时调用：透传到底层仪器实例
        inst = self.__dict__.get("_inst")
        if inst is None:
            raise AttributeError(f"{type(self).__name__} has no attribute {name!r}")
        return getattr(inst, name)


class PowerSupplyRole(_RoleBase):
    """数字电源角色封装"""

    def set_voltage(self, volt: float, channel: int = 1) -> PowerSupplyRole:
        """设置通道电压并自动使能输出"""
        self._inst.set_voltage(volt, channel)
        return self

    def output_enable(self, channel: int = 0) -> PowerSupplyRole:
        """打开输出（0 表示全部通道）"""
        self._inst.output_enable(channel)
        return self

    def output_disable(self, channel: int = 0) -> PowerSupplyRole:
        """关闭输出（0 表示全部通道）"""
        self._inst.output_disable(channel)
        return self


class ThermalChamberRole(_RoleBase):
    """高低温发生器角色封装"""

    def setup(self) -> ThermalChamberRole:
        """初始化"""
        self._inst.setup()
        return self

    def set_temperature(self, temp: float, soak: int = 15) -> None:
        """设置目标温度"""
        self._inst.set_temperature(temp, soak)

    def get_temperature(self) -> float | None:
        """读取当前温度"""
        return self._inst.get_temperature()

    def execute(self, action: str) -> ThermalChamberRole:
        """执行动作"""
        self._inst.execute(action)
        return self

    def wait(self, timeout: int = 150, interval: float = 3):
        """等待温度稳定，超时抛 ``TimeoutError``"""
        return self._inst.wait(timeout=timeout)

    def ready(self) -> bool:
        """高低温设备是否就绪：Head 位置等状态"""
        return self._inst.ready()

    def get_error(self) -> list[str]:
        """获取错误信息列表"""
        return self._inst.get_error()


class WaveformGeneratorRole(_RoleBase):
    """波形发生器角色封装"""

    def __init__(self, inst, info: InstrumentInfo) -> None:
        super().__init__(inst, info)
        self.cfg = {"wave": "sin", "freq": 1000.0, "vpp": 3.3, "offset": 1.65}

    def configure(
        self,
        wave: str = "sin",
        freq: float = 1000.0,
        vpp: float = 3.3,
        offset: float = 1.65,
        **kw,
    ) -> WaveformGeneratorRole:
        """配置波形并开启输出"""
        self.cfg.update(wave=wave, freq=freq, vpp=vpp, offset=offset, **kw)
        self._inst.configure(wave, freq, vpp, offset, **kw)
        return self

    def output_enable(self) -> WaveformGeneratorRole:
        self._inst.output_enable()
        return self

    def output_disable(self) -> WaveformGeneratorRole:
        self._inst.output_disable()
        return self

    def set_frequency(self, freq: float) -> WaveformGeneratorRole:
        self._inst.set_frequency(freq)
        return self

    def set_amplitude(self, vpp: float) -> WaveformGeneratorRole:
        self._inst.set_amplitude(vpp)
        return self

    def set_offset(self, offset: float) -> WaveformGeneratorRole:
        self._inst.set_offset(offset)
        return self


class DMMRole(_RoleBase):
    """数字万用表角色封装"""

    def configure(self, params: dict | None = None) -> DMMRole:
        """配置测量参数"""
        self._inst.configure(params)
        return self

    def read_voltage(self, params: dict | None = None) -> float:
        """读取直流电压"""
        return self._inst.read_voltage(params)

    def read_current(self, params: dict | None = None) -> float:
        """读取直流电流"""
        return self._inst.read_current(params)


class OscilloscopeRole(_RoleBase):
    """示波器角色封装, read_frequency/read_pulse 等透传"""

    @property
    def status(self) -> str:
        return self._inst.get_status()

    def execute(self, mode: str) -> OscilloscopeRole:
        """切换运行模式
        - single
        - run
        - stop"""
        self._inst.execute(mode)
        return self

    def configure(self, **kw) -> OscilloscopeRole:
        """透传底层配置"""
        self._inst.configure(**kw)
        return self

    def read_frequency(self, channel: int = 1) -> float:
        """读取频率"""
        return self._inst.read_frequency(channel)

    def read_duty_cycle(self, channel: int = 1) -> float:
        """读取占空比"""
        return self._inst.read_duty_cycle(channel)

    def read_pulse(self, channel: int = 1) -> float:
        """读取脉冲宽度"""
        return self._inst.read_pulse(channel)

    def read_image(self) -> bytes:
        """读取当前屏幕图像"""
        return self._inst.read_image()

    def screenshot(self) -> bytes:
        """截图（与 read_image 等价）"""
        return self._inst.screenshot()


class FrequencyCounterRole(_RoleBase):
    """频率计角色封装（示波器 / 频率计均可充当）"""

    def read_frequency(self, channel: int = 1) -> float:
        """读取频率"""
        return self._inst.read_frequency(channel)

    def read_duty_cycle(self, channel: int = 1) -> float:
        """读取占空比"""
        return self._inst.read_duty_cycle(channel)


# ── 角色映射表 ──────────────────────────────────────────────────────
# 元组结构：(inst_type 或类型元组, 能力名, 角色类)
# 多类别充当：inst_type 可为元组，表示多类仪器可充当同一角色
# （如 frequency_counter 允许 OSCILLOSCOPE / FREQUENCY_COUNTER 两类，
# 示波器自带频率测量能力）。匹配成功即返回对应角色类实例。

_ROLES = {
    "power_supply": (InstrumentType.POWER_SUPPLY, "VOLTAGE", PowerSupplyRole),
    "thermal": (InstrumentType.THERMAL_CHAMBER, "TEMPERATURE", ThermalChamberRole),
    "dmm": (InstrumentType.DMM, "VOLTAGE_DC", DMMRole),
    "waveform_generator": (
        InstrumentType.WAVEFORM_GENERATOR,
        "WAVEFORM",
        WaveformGeneratorRole,
    ),
    "oscilloscope": (InstrumentType.OSCILLOSCOPE, "FREQUENCY", OscilloscopeRole),
    "frequency_counter": (
        (InstrumentType.OSCILLOSCOPE, InstrumentType.FREQUENCY_COUNTER),
        "FREQUENCY",
        FrequencyCounterRole,
    ),
}
