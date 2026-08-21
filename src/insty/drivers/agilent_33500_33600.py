# Agilent 33500/33600 系列 Trueform 信号发生器

from __future__ import annotations

import logging
from typing import ClassVar

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
    """Agilent 33500/33600 系列信号发生器公共基类"""

    # 各波形最大频率（Hz），子类可覆盖
    _FREQ_MAX: ClassVar[dict[str, float]] = {
        "SIN": 30e6, "SQU": 25e6, "TRI": 200e3, "RAMP": 200e3,
    }

    def __init__(self, resource: Resource | None) -> None:
        super().__init__(resource)
        self.channel = 1  # 默认操作通道
        # 当前配置状态，供 set_* 增量修改时复用校验
        self._wave = "SIN"
        self._vpp = 0.0
        self._offset = 0.0
        self._phase = 0.0
        self._load = "INF"  # 输出终止负载，默认高阻
        # 各通道输出状态（True=开, False=关），由 output_enable/disable 维护
        self._output_states: dict[int, bool] = {c: False for c in range(1, self.channels + 1)}

    @property
    def Vmax(self) -> float:
        """当前终止负载下的最大峰值电压（V）：高阻 10V、50Ω 5V，其余按 50Ω 源阻抗分压推算"""
        if self._load == "INF":
            return 10
        load = float(self._load)
        return 10 * load / (load + 50)

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

    def _parse_setup_args(self, wave: str, kwargs) -> tuple[str, float, float, float]:
        """归一化 wave 并从 kwargs 摘取其余参数，返回 (wave, freq, vpp, offset)

        非 DC 波形还需 freq/vpp/offset；DC 波形仅需 offset（直流电平），
        freq/vpp 忽略
        """
        wave_upper = wave.upper()
        if wave_upper not in _WAVE_MAP:
            raise ValueError(f'Unsupported wave type: {wave}')
        wave = _WAVE_MAP[wave_upper]
        freq, vpp, offset = pick_keys(kwargs, ["freq", "vpp", "offset"])
        if wave == "DC":
            if offset is None:
                raise KeyError("Missing required parameter: offset")
            return wave, 0.0, 0.0, offset
        if freq is None or vpp is None or offset is None:
            raise KeyError("Missing required parameters: freq/vpp/offset")
        return wave, freq, vpp, offset

    def _check_offset_limit(self, offset: float, vpp: float) -> None:
        """校验 |offset| < Vmax - vpp/2（手册 VOLTage 命令约束）"""
        if abs(offset) >= self.Vmax - vpp / 2:
            raise ValueError("|offset| must be less than (Vmax - vpp/2)")

    def _validate(
        self,
        wave: str,
        freq: float,
        vpp: float,
        offset: float,
        phase: float,
        duty_cycle: float,
    ) -> None:
        """校验波形参数范围（对照 SCPI 手册约束）"""
        if not (-360 <= phase <= 360):
            raise ValueError("Phase out of range (-360 to 360)")
        if wave == "SQU" and not (0.01 <= duty_cycle <= 99.99):
            raise ValueError("Duty cycle out of range (0.01 to 99.99)")
        if wave == "RAMP" and not (0 <= duty_cycle <= 100):
            raise ValueError("Duty cycle out of range (0 to 100)")
        if wave == "DC":
            if abs(offset) >= self.Vmax:
                raise ValueError("DC level out of range (±Vmax)")
        else:
            if freq <= 0:
                raise ValueError("Frequency must be positive")
            max_f = self._FREQ_MAX.get(wave, 200e3)
            if freq > max_f:
                raise ValueError(f"Frequency {freq} Hz exceeds {wave} max {max_f} Hz")
            if vpp <= 0:
                raise ValueError("Amplitude must be positive")
            self._check_offset_limit(offset, vpp)

    def setup(self, wave: str, *, channel: int = 1, **kwargs) -> Self:
        """初始化并配置波形及参数（wave 必选位置参数，其余关键字参数按波形取舍）"""
        self._check_channel(channel)
        wave, freq, vpp, offset = self._parse_setup_args(wave, kwargs)
        phase = kwargs.get("phase", 0.0)
        duty_cycle = kwargs.get("duty_cycle", 50.0)
        output_load, = pick_keys(kwargs, ["output_load"])
        if output_load is not None:
            self._resolve_load(output_load)
        dut_high, dut_low, = pick_keys(kwargs, ["dut_high", "dut_low"])
        self._validate(wave, freq, vpp, offset, phase, duty_cycle)
        self._wave = wave
        self._vpp = vpp
        self._offset = offset
        self._phase = phase

        src = self._source_prefix(channel)
        out = self._out_prefix(channel)

        # 配置前先关闭全部通道输出，setup 仅保留当前通道处于已配置状态
        for c in range(1, self.channels + 1):
            self._output_states[c] = False
            
        cmds = [f"{self._out_prefix(c)} OFF" for c in range(1, self.channels + 1)]
        cmds.extend(
            [
                f"{out}:LOAD {self._load}",
                f"{src}VOLTage:UNIT VPP",
            ]
        )
        if dut_high is not None and dut_low is not None:
            cmds.extend(
                [
                    f"{src}VOLTage:LIMit:HIGH {dut_high}",
                    f"{src}VOLTage:LIMit:LOW {dut_low}",
                    f"{src}VOLTage:LIMit:STATe ON",
                ]
            )
        cmds.append(f"{src}FUNCtion {wave}")

        if wave == "DC":
            cmds.append(f"{src}VOLTage:OFFSet {offset}")
        else:
            cmds.extend(
                [
                    f"{src}FREQuency {freq}",
                    f"{src}VOLTage {vpp}",
                    f"{src}VOLTage:OFFSet {offset}",
                    f"{src}PHASe {phase}",
                ]
            )
            if wave == "SQU":
                cmds.append(f"{src}FUNCtion:SQUare:DCYCle {duty_cycle}")
            elif wave == "RAMP":
                cmds.append(f"{src}FUNCtion:RAMP:SYMMetry {duty_cycle}")

        if self.channel > 1:
            # 只有支持多通道的型号才支持这个命令，否则会报错~
            cmds.extend(
                [
                    f"DISPlay:FOCus CH{channel}",
                ]
            )

        logger.debug(f'setup command: {";".join(cmds)}')

        if not self.run_cmds(cmds):
            raise RuntimeError("Failed to configure Agilent 33500 series")
        self.beep()
        return self

    def set_frequency(self, freq: float, channel: int = 1) -> Self:
        if freq <= 0:
            raise ValueError("Frequency must be positive")
        max_f = self._FREQ_MAX.get(self._wave, 200e3)
        if freq > max_f:
            raise ValueError(f"Frequency {freq} Hz exceeds {self._wave} max {max_f} Hz")

        cmds = [f"{self._source_prefix(channel)}FREQuency {freq}"]
        logger.debug(f'set_frequency command: {";".join(cmds)}')
        self.run_cmds(cmds)

        return self

    def set_amplitude(self, vpp: float, channel: int = 1) -> Self:
        if self._wave == "DC":
            raise ValueError("DC 波形无幅度参数，请用 set_offset 调整直流电平")
        if vpp <= 0:
            raise ValueError("Amplitude must be positive")
        self._check_offset_limit(self._offset, vpp)

        self._vpp = vpp
        cmds = [f"{self._source_prefix(channel)}VOLTage {vpp}"]
        logger.debug(f'set_amplitude command: {";".join(cmds)}')
        self.run_cmds(cmds)

        return self

    def set_offset(self, offset: float, channel: int = 1) -> Self:
        if self._wave == "DC":
            if abs(offset) >= self.Vmax:
                raise ValueError("DC level out of range (±Vmax)")
        else:
            self._check_offset_limit(offset, self._vpp)
        self._offset = offset
        cmds = [f"{self._source_prefix(channel)}VOLTage:OFFSet {offset}"]
        logger.debug(f'set_offset command: {";".join(cmds)}')
        self.run_cmds(cmds)
        return self

    def set_phase(self, phase: float, channel: int = 1) -> Self:
        """设置初始相位（PHASe，单位由 UNIT:ANGLe 决定，默认度）"""
        if not (-360 <= phase <= 360):
            raise ValueError("Phase out of range (-360 to 360)")
        self._phase = phase
        cmds = [f"{self._source_prefix(channel)}PHASe {phase}"]
        logger.debug(f'set_phase command: {";".join(cmds)}')
        self.run_cmds(cmds)
        return self

    def _resolve_load(self, load: float | str) -> str:
        """校验并记录负载，返回 OUTPut:LOAD 的 SCPI 值字符串

        load: 数值 1Ω~10kΩ 或 'INFinity'（不区分大小写）
        """
        if isinstance(load, str):
            if load.upper() not in ("INF", "INFINITY"):
                raise ValueError("Load must be ohms (1-10000) or 'INFinity'")
            self._load = "INF"
            return "INF"
        if not (1 <= load <= 10000):
            raise ValueError("Load must be ohms (1-10000) or 'INFinity'")
        self._load = float(load)
        return str(load)

    def set_output_load(self, load: float | str, channel: int = 1) -> Self:
        """设置输出终止负载（OUTPut:LOAD）：数值 1Ω~10kΩ 或 INFinity"""
        value = self._resolve_load(load)
        cmds = [f"{self._out_prefix(channel)}:LOAD {value}"]
        logger.debug(f'set_output_load command: {";".join(cmds)}')
        self.run_cmds(cmds)
        return self

    def set_voltage_limit(self, high: float, low: float, channel: int = 1) -> Self:
        """设置 DUT 电压保护限值（VOLTage:LIMit:HIGH/LOW + STATe ON）"""
        if abs(high) > self.Vmax or abs(low) > self.Vmax:
            raise ValueError("Limit exceeds Vmax")
        if high <= low:
            raise ValueError("HIGH must be greater than LOW")
        src = self._source_prefix(channel)
        cmds = [
            f"{src}VOLTage:LIMit:HIGH {high}",
            f"{src}VOLTage:LIMit:LOW {low}",
            f"{src}VOLTage:LIMit:STATe ON",
        ]
        logger.debug(f'set_voltage_limit command: {";".join(cmds)}')
        self.run_cmds(cmds)
        return self

    def set_polarity(self, polarity: str, channel: int = 1) -> Self:
        """设置输出波形极性（OUTPut:POLarity）：NORMal 或 INVerted"""
        polarity_upper = polarity.upper()
        if polarity_upper not in ("NORMAL", "NORM", "INVERTED", "INV"):
            raise ValueError("Polarity must be NORMal or INVerted")
        value = "NORMal" if polarity_upper.startswith("NORM") else "INVerted"
        cmds = [f"{self._out_prefix(channel)}:POLarity {value}"]
        logger.debug(f'set_polarity command: {";".join(cmds)}')
        self.run_cmds(cmds)
        return self

    def output_enable(self, channel: int = 1) -> Self:
        """使能指定通道输出"""
        self._check_channel(channel)

        if not self._output_states[channel]:
            cmds = [f"{self._out_prefix(channel)} ON"]
            logger.debug(f'output_enable command: {";".join(cmds)}')
            if not self.run_cmds(cmds):
                raise RuntimeError("Failed to enable output")
            self._output_states[channel] = True
        return self

    def output_disable(self, channel: int = 1) -> Self:
        """关闭指定通道输出"""
        self._check_channel(channel)

        if self._output_states[channel]:
            prefix = self._out_prefix(channel)
            cmds = [
                f"{self._source_prefix(channel)}VOLTage MIN",
                f"{self._source_prefix(channel)}VOLTage:OFFSet 0",
                f"{prefix} OFF",
            ]
            logger.debug(f'output_disable command: {";".join(cmds)}')
            self.run_cmds(cmds)
            self._output_states[channel] = False
        return self

    def _close(self) -> None:
        """关闭全部输出并释放 VISA 连接"""
        for c in range(1, self.channels + 1):
            self.output_disable(c)
        super()._close()


class Agilent33519B(Agilent33500Base):
    """Agilent 33519B 单通道信号发生器驱动（30 MHz，无任意波形）"""

    @property
    def channels(self) -> int:
        return 1


class Agilent33522B(Agilent33500Base):
    """Agilent 33522B 双通道信号发生器驱动（30 MHz，支持任意波形）"""

    @property
    def channels(self) -> int:
        return 2


class Agilent33612A(Agilent33500Base):
    """Agilent 33612A 双通道信号发生器驱动（80 MHz，支持任意波形）"""

    @property
    def channels(self) -> int:
        return 2

    _FREQ_MAX: ClassVar[dict[str, float]] = {
        "SIN": 80e6, "SQU": 25e6, "TRI": 200e3, "RAMP": 200e3,
    }


# 注册到仪器注册表
InstrumentRegistry.register_waveform_generator(
    "AGILENT::33519B",
    Agilent33519B,
    supported=("WAVEFORM",),
)
InstrumentRegistry.register_waveform_generator(
    "AGILENT::33522B",
    Agilent33522B,
    supported=("WAVEFORM",),
)
InstrumentRegistry.register_waveform_generator(
    "AGILENT::33612A",
    Agilent33612A,
    supported=("WAVEFORM",),
)
