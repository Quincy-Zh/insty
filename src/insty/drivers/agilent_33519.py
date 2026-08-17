from __future__ import annotations

# 信号发生器：AGILENT::33519
import logging

from pyvisa.resources import Resource

from ..instrument_types import (
    InstrumentRegistry,
    WaveformGenerator,
)
from ..visa_based_instrument import VisaBasedInstrument

logger = logging.getLogger(__name__)

_WAVE_MAP = {
    "DC": "DC",
    "SIN": "SIN",
    "SQU": "SQU",
    "RAMP": "RAMP",
    "TRI": "TRI",
}


class Agilent33519(VisaBasedInstrument, WaveformGenerator):
    """Agilent 33519 系列信号发生器驱动基类"""

    Vmax = 20  # 输出最大电压值

    def __init__(self, resource: Resource | None) -> None:
        super().__init__(resource)
        self.beep_ = False
        self.output_load = "INFinity"
        self.cfg = {
            "wave": "sin",
            "freq": 1000,
            "vpp": 3.3,
            "offset": 1.65,
        }

    def beep(self):
        if self.beep_:
            self.run_cmds(["SYSTem:BEEPer"])

    def configure(
        self,
        wave: str,
        freq: float,
        vpp: float,
        offset: float,
        **kwargs,
    ) -> None:
        """配置波形及参数"""
        wave_upper = wave.upper()
        if wave_upper not in _WAVE_MAP:
            raise ValueError(f'Unsupported wave type: {wave}')

        self.cfg["wave"] = _WAVE_MAP[wave_upper]
        self.cfg["freq"] = freq
        self.cfg["vpp"] = vpp
        self.cfg["offset"] = offset

        vpp, offset = self.cfg["vpp"], self.cfg["offset"]
        limit = self.Vmax - vpp / 2
        if abs(offset) >= limit:
            raise ValueError("|offset| must be less than (Vmax - vpp/2)")

        if hasattr(self, "channel"):
            cmd = f"OUTPut{self.channel}:LOAD {self.output_load}"
        else:
            cmd = f"OUTPut:LOAD {self.output_load}"
        self.run_cmds([cmd])

        self._apply_waveform()

    def _apply_waveform(self) -> None:
        """应用当前波形配置"""
        if hasattr(self, "channel"):
            cmd = f"SOURce{self.channel}:"
        else:
            cmd = ""

        if self.cfg["wave"] == "DC":
            cmd = f"{cmd}APPL:DC DEF,DEF,{self.cfg['offset']}"
        else:
            cmd = f"{cmd}APPL:{self.cfg['wave']} {self.cfg['freq']},{self.cfg['vpp']},{self.cfg['offset']}"

        self.run_cmds([cmd])

    def output_enable(self) -> None:
        """使能输出"""
        if hasattr(self, "channel"):
            cmd = f"OUTPut{self.channel} ON"
        else:
            cmd = "OUTPut ON"
        self.run_cmds([cmd])

    def output_disable(self) -> None:
        """关闭输出"""
        if hasattr(self, "channel"):
            cmd = f"OUTPut{self.channel} OFF"
        else:
            cmd = "OUTPut OFF"
        self.run_cmds([cmd])

    def set_frequency(self, freq: float) -> None:
        self.cfg["freq"] = freq
        self._apply_waveform()

    def set_amplitude(self, vpp: float) -> None:
        self.cfg["vpp"] = vpp
        self._apply_waveform()

    def set_offset(self, offset: float) -> None:
        self.cfg["offset"] = offset
        self._apply_waveform()

    def close(self) -> None:
        self.output_disable()


# 注册到仪器注册表
InstrumentRegistry.register_waveform_generator(
    "AGILENT::33519",
    Agilent33519,
    supported=("WAVEFORM",),
)