# 信号发生器：AGILENT::33512B / AGILENT::33519
# Agilent 33500 系列 Trueform 信号发生器

from __future__ import annotations

import logging

from pyvisa.resources import Resource
from typing_extensions import Self

from ..instrument_types import (
    InstrumentRegistry,
    WaveformGenerator,
)
from ..utils import pick_keys
from ..visa_based_instrument import VisaBasedInstrument

logger = logging.getLogger(__name__)

_WAVE_MAP = {
    "DC": "DC",
    "SIN": "SIN",
    "SQU": "SQU",
    "TRI": "TRI",
    "RAMP": "RAMP",
}


class Agilent33500Base(VisaBasedInstrument, WaveformGenerator):
    """Agilent 33500 系列信号发生器公共基类"""

    # 通道数，子类赋予正确值
    channels: int = 1

    def __init__(self, resource: Resource | None) -> None:
        super().__init__(resource)
        self.beep_ = False
        self.channel = 1  # 默认操作通道

    def beep(self):
        if self.beep_:
            self.run_cmds(["SYSTem:BEEPer"])

    def _check_channel(self, channel: int) -> None:
        """校验通道号是否在 1~channels 范围内"""
        if not (1 <= channel <= self.channels):
            raise ValueError(f"channel out of range (1 - {self.channels})")

    def _source_prefix(self, channel: int) -> str:
        """返回 SOURce 命令前缀：多通道带通道号，单通道不带"""
        self._check_channel(channel)
        return f"SOURce{channel}:" if self.channels > 1 else "SOURce:"

    def _out_prefix(self, channel: int) -> str:
        """返回 OUTPut 命令前缀：多通道带通道号，单通道不带"""
        self._check_channel(channel)
        return f"OUTPut{channel}" if self.channels > 1 else "OUTPut"

    def _parse_setup_args(self, kwargs) -> tuple[str, float, float, float]:
        """从 kwargs 摘取 wave/freq/vpp/offset 并校验，返回 (wave, freq, vpp, offset)"""
        wave, freq, vpp, offset = pick_keys(kwargs, ["wave", "freq", "vpp", "offset"])
        if wave is None or freq is None or vpp is None or offset is None:
            raise KeyError("Missing required parameters: wave/freq/vpp/offset")
        wave_upper = wave.upper()
        if wave_upper not in _WAVE_MAP:
            raise ValueError(f'Unsupported wave type: {wave}')
        return _WAVE_MAP[wave_upper], freq, vpp, offset

    def output_enable(self, channel: int = 1) -> Self:
        """使能输出。channel=0 表示全部通道"""
        if channel == 0:
            cmds = [f"{self._out_prefix(c)} ON" for c in range(1, self.channels + 1)]
        else:
            self._check_channel(channel)
            cmds = [f"{self._out_prefix(channel)} ON"]
        if not self.run_cmds(cmds):
            raise RuntimeError("Failed to enable output")
        return self

    def output_disable(self, channel: int = 1) -> Self:
        """关闭输出。channel=0 表示全部通道"""
        if channel == 0:
            cmds = [f"{self._out_prefix(c)} OFF" for c in range(1, self.channels + 1)]
        else:
            self._check_channel(channel)
            cmds = [f"{self._out_prefix(channel)} OFF"]
        self.run_cmds(cmds)
        return self

    def close(self) -> None:
        """关闭全部输出并释放 VISA 连接"""
        self.output_disable(0)
        super().close()


class Agilent33512B(Agilent33500Base):
    """Agilent 33512B 双通道信号发生器驱动"""

    channels = 2

    def __init__(self, resource: Resource | None) -> None:
        super().__init__(resource)
        logger.debug(f"Initializing AGILENT::33512B with {resource}")
        self.params = {}

    def setup(self, channel: int = 1, **kwargs) -> Self:
        """初始化并配置波形及参数（wave/freq/vpp/offset 从 kwargs 获取）"""
        self._check_channel(channel)
        wave, freq, vpp, offset = self._parse_setup_args(kwargs)

        self.params = {
            "wave": wave,
            "frequency": freq,
            "amplitude": vpp,
            "offset": offset,
            "phase": kwargs.get("phase", 0.0),
            "duty_cycle": kwargs.get("duty_cycle", 50.0),
        }

        if not (-360 <= self.params["phase"] <= 360):
            raise ValueError("Phase out of range (-360 to 360)")

        if not (0 <= self.params["duty_cycle"] <= 100):
            raise ValueError("Duty cycle out of range (0 to 100)")

        src = self._source_prefix(channel)
        out = self._out_prefix(channel)

        cmds = [
            f"{out}:LOAD INF",
            f"{src}FUNCtion {self.params['wave']}",
        ]

        if self.params["wave"] == "DC":
            cmds.append(f"{src}VOLTage:OFFSet {self.params['amplitude']}")
        else:
            cmds.extend([
                f"{src}FREQuency {self.params['frequency']}",
                f"{src}VOLTage {self.params['amplitude']}",
                f"{src}VOLTage:OFFSet {self.params['offset']}",
                f"{src}PHASe {self.params['phase']}",
            ])
            if self.params["wave"] == "SQU":
                cmds.append(
                    f"{src}FUNCtion:SQUare:DCYCle {self.params['duty_cycle']}"
                )
            elif self.params["wave"] == "RAMP":
                cmds.append(
                    f"{src}FUNCtion:RAMP:SYMMetry {self.params['duty_cycle']}"
                )

        cmds.extend([
            f"{out} ON",
            f"DISPlay:FOCus CH{channel}",
        ])

        if not self.run_cmds(cmds):
            raise RuntimeError("Failed to configure Agilent33512B")
        self.beep()
        return self

    def set_frequency(self, freq: float, channel: int = 1) -> Self:
        self.run_cmds([f"{self._source_prefix(channel)}FREQuency {freq}"])
        return self

    def set_amplitude(self, vpp: float, channel: int = 1) -> Self:
        self.run_cmds([f"{self._source_prefix(channel)}VOLTage {vpp}"])
        return self

    def set_offset(self, offset: float, channel: int = 1) -> Self:
        self.run_cmds([f"{self._source_prefix(channel)}VOLTage:OFFSet {offset}"])
        return self


class Agilent33519(Agilent33500Base):
    """Agilent 33519 单通道信号发生器驱动"""

    channels = 1

    Vmax = 20  # 输出最大电压值

    def __init__(self, resource: Resource | None) -> None:
        super().__init__(resource)
        logger.debug(f"Initializing AGILENT::33519 with {resource}")
        self.output_load = "INFinity"
        self.cfg = {
            "wave": "sin",
            "freq": 1000,
            "vpp": 3.3,
            "offset": 1.65,
        }

    def setup(self, channel: int = 1, **kwargs) -> Self:
        """初始化并配置波形及参数（wave/freq/vpp/offset 从 kwargs 获取）"""
        self._check_channel(channel)
        wave, freq, vpp, offset = self._parse_setup_args(kwargs)

        self.cfg["wave"] = wave
        self.cfg["freq"] = freq
        self.cfg["vpp"] = vpp
        self.cfg["offset"] = offset

        limit = self.Vmax - vpp / 2
        if abs(offset) >= limit:
            raise ValueError("|offset| must be less than (Vmax - vpp/2)")

        self.run_cmds([f"{self._out_prefix(channel)}:LOAD {self.output_load}"])

        self._apply_waveform(channel)
        return self

    def _apply_waveform(self, channel: int = 1) -> None:
        """应用当前波形配置"""
        prefix = self._source_prefix(channel)
        if self.cfg["wave"] == "DC":
            cmd = f"{prefix}APPL:DC DEF,DEF,{self.cfg['offset']}"
        else:
            cmd = f"{prefix}APPL:{self.cfg['wave']} {self.cfg['freq']},{self.cfg['vpp']},{self.cfg['offset']}"

        self.run_cmds([cmd])

    def set_frequency(self, freq: float, channel: int = 1) -> Self:
        self._check_channel(channel)
        self.cfg["freq"] = freq
        self._apply_waveform(channel)
        return self

    def set_amplitude(self, vpp: float, channel: int = 1) -> Self:
        self._check_channel(channel)
        self.cfg["vpp"] = vpp
        self._apply_waveform(channel)
        return self

    def set_offset(self, offset: float, channel: int = 1) -> Self:
        self._check_channel(channel)
        self.cfg["offset"] = offset
        self._apply_waveform(channel)
        return self


# 注册到仪器注册表
InstrumentRegistry.register_waveform_generator(
    "AGILENT::33512B",
    Agilent33512B,
    supported=("WAVEFORM",),
)
InstrumentRegistry.register_waveform_generator(
    "AGILENT::33519",
    Agilent33519,
    supported=("WAVEFORM",),
)