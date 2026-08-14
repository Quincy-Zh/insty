"""高级测试台 API

把底层 ``InstrumentManager`` 与具体仪器类适配为面向测试脚本的领域接口。
脚本通过 ``TestBench`` 按“角色”获取仪器封装实例，例如：

    mngr = TestBench(device_table=".device_table.json")
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
"""

from __future__ import annotations

import logging
import subprocess
import time

from typing_extensions import Self

from .instrument_types import InstrumentInfo, InstrumentType
from .manager import InstrumentManager

logger = logging.getLogger(__name__)


def frange(start, stop, step=1.0) -> list[float]:
    """浮点等差数列（含端点），行为与 JSON 版 ``start~end,step`` 语法一致"""
    if step == 0:
        raise ValueError("step 不能为 0")
    n = max(0, round((stop - start) / step) + 1)
    return [round(start + i * step, 12) for i in range(n)]


# ── 角色封装：适配类型化接口 ──────────────────────────────────────


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
    """数字万用表角色封装, read_voltage/read_current 透传"""

    def configure(self, params: dict | None = None) -> DMMRole:
        """配置测量参数"""
        self._inst.configure(params)
        return self


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


class FrequencyCounterRole(_RoleBase):
    """频率计角色封装, read_frequency/read_duty_cycle 透传"""


# ── 角色映射表 ──────────────────────────────────────────────────────
# 元组结构：(inst_type 或类型元组, 能力名, 角色类)
# frequency_counter 允许 OSCILLOSCOPE / FREQUENCY_COUNTER 两类仪器充当。

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


# ── 测试台 ──────────────────────────────────────────────────────────


class TestBench:
    """测试台：按角色解析并连接仪器

    Usage::

        mngr = TestBench(device_table=".device_table.json")
        ps = mngr.get_power_supply(address="USB0::...")
        thermal = mngr.get_thermal()
        vm = mngr.get_dmm(address="USB0::...")
        osc = mngr.get_oscilloscope(address="USB0::...")
        ...
        mngr.close()
    """

    def __init__(self, device_table=None, persistent_store=None) -> None:
        """初始化测试台

        Args:
            device_table: 运行时设备表（JSON 路径 / DeviceTable / None），
                承载串口（ASRL）等地址会漂移的设备
            persistent_store: 持久设备存储（JSON 路径 / DeviceTable / None），
                承载 USB/TCPIP 等地址稳定唯一的设备；None 时使用默认路径
            manager: 已构造的 InstrumentManager（测试注入用），与 device_table 二选一
        """
        self._mgr = InstrumentManager(
            device_table=device_table, persistent_store=persistent_store
        )

        # 在线仪器列表惰性发现：首次 get_* 时 discover，之后缓存；匹配失败自动刷新一次
        self._infos: list[InstrumentInfo] | None = None

    def refresh(self) -> list[InstrumentInfo]:
        """重新发现当前在线的仪器并更新缓存, 存在性检查，不做 "*IDN?"

        设备连接变化（尤其串口换口）后请调用 :meth:`scan` 重建设备表。
        """
        self._infos = self._mgr.discover()
        return list(self._infos)

    def scan(self) -> list[InstrumentInfo]:
        """显式全量识别在线仪器（对每个地址执行 *IDN?*）并重建设备表

        耗时较高（串口需逐档波特率试探），仅在设备连接变化后由用户
        在脚本中显式调用。

        Returns:
            识别出的仪器列表，同时更新本测试台的在线缓存
        """
        self._infos = self._mgr.full_scan()
        return list(self._infos)

    def _ensure_infos(self) -> None:
        """确保在线仪器列表已发现（惰性）"""
        if self._infos is None:
            self._infos = self._mgr.discover()

    def _find_info(
        self, role: str, address: str | None, _retried: bool = False
    ) -> InstrumentInfo:
        inst_type, capability, _ = _ROLES[role]
        self._ensure_infos()

        if address:
            for info in self._infos:
                if info.address == address:
                    if not info.supports(inst_type, capability):
                        raise RuntimeError(
                            f'{info.label}[{address}] 不支持 "{capability}"'
                        )
                    return info
            # 地址不在当前在线列表：自动重新发现一次再匹配
            if not _retried:
                self.refresh()
                return self._find_info(role, address, _retried=True)
            raise RuntimeError(f'仪器地址不存在或未连接: "{address}"')

        candidates = [
            info for info in self._infos if info.supports(inst_type, capability)
        ]
        if not candidates:
            # 当前在线列表无匹配仪器：自动重新发现一次再匹配
            if not _retried:
                self.refresh()
                return self._find_info(role, address, _retried=True)
            raise RuntimeError(f'未找到可用 "{capability}" 的仪器（{role}）')
        if len(candidates) > 1:
            raise RuntimeError(
                f'找到多台 "{capability}" 仪器，请通过 address 参数指定: '
                + ", ".join(c.address for c in candidates)
            )
        return candidates[0]

    def _open_role(self, role: str, address: str | None):
        info = self._find_info(role, address)
        inst = self._mgr.open(info.address, info.label, timeout=30000)
        _, _, role_class = _ROLES[role]
        return role_class(inst, info)

    # ── 角色获取 ────────────────────────────────────────────────────

    def get_power_supply(self, address: str | None = None) -> PowerSupplyRole:
        """获取数字电源实例"""
        return self._open_role("power_supply", address)

    def get_thermal(self, address: str | None = None) -> ThermalChamberRole:
        """获取高低温发生器实例，并完成开机检查与 DUT 模式配置"""
        return self._open_role("thermal", address)

    def get_dmm(self, address: str | None = None) -> DMMRole:
        """获取数字万用表实例"""
        return self._open_role("dmm", address)

    def get_waveform_generator(
        self, address: str | None = None
    ) -> WaveformGeneratorRole:
        """获取波形发生器实例"""
        return self._open_role("waveform_generator", address)

    def get_oscilloscope(self, address: str | None = None) -> OscilloscopeRole:
        """获取示波器实例"""
        return self._open_role("oscilloscope", address)

    def get_frequency_counter(self, address: str | None = None) -> FrequencyCounterRole:
        """获取频率计实例"""
        return self._open_role("frequency_counter", address)

    # ── 工具方法 ───────────────────────────────────────────────────

    @staticmethod
    def hold(seconds: float) -> None:
        """保持当前状态等待指定时间"""
        time.sleep(seconds)

    def run_cmd(self, args, check: bool = True, timeout: float | None = None) -> bool:
        """执行外部命令（如 DUT 串口命令）"""
        cmd = [str(a) for a in args]
        logger.info(f'Run: {" ".join(cmd)}')
        try:
            subprocess.run(cmd, shell=False, check=True, timeout=timeout)
            return True
        except subprocess.CalledProcessError as ex:
            logger.error(f"命令执行失败: {ex}")
            if check:
                raise RuntimeError(f"命令执行失败: {ex}") from ex
            return False

    def close(self) -> None:
        """关闭所有仪器连接并释放资源"""
        self._mgr.shutdown()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc) -> None:
        self.close()
