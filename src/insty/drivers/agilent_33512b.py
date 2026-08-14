from __future__ import annotations

# 信号发生器：AGILENT::33512B
import logging

from pyvisa.resources import Resource

from ..instrument_types import (
    InstrumentRegistry,
    WaveformGeneratorBase,
)
from ..visa_based_instrument import VisaBasedInstrument

logger = logging.getLogger(__name__)

_WAVE_MAP = {
    "DC": "DC",
    "SIN": "SIN",
    "SQU": "SQU",
    "TRI": "TRI",
    "RAMP": "RAMP",
}


class Agilent33512B(VisaBasedInstrument, WaveformGeneratorBase):
    """Agilent 33512B 信号发生器驱动"""

    def __init__(self, resource: Resource | None) -> None:
        super().__init__(resource)
        logger.debug(f"Initializing AGILENT::33512B with {resource}")
        self.channel = 1
        self.beep_ = False
        self.params = {}

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

        self.params = {
            "wave": _WAVE_MAP[wave_upper],
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

        cmds = [
            f"OUTPut{self.channel}:LOAD INF",
            f"SOURce{self.channel}:FUNCtion {self.params['wave']}",
        ]

        if self.params["wave"] == "DC":
            cmds.append(f"SOURce{self.channel}:VOLTage:OFFSet {self.params['amplitude']}")
        else:
            cmds.extend([
                f"SOURce{self.channel}:FREQuency {self.params['frequency']}",
                f"SOURce{self.channel}:VOLTage {self.params['amplitude']}",
                f"SOURce{self.channel}:VOLTage:OFFSet {self.params['offset']}",
                f"SOURce{self.channel}:PHASe {self.params['phase']}",
            ])
            if self.params["wave"] == "SQU":
                cmds.append(
                    f"SOURce{self.channel}:FUNCtion:SQUare:DCYCle {self.params['duty_cycle']}"
                )
            elif self.params["wave"] == "RAMP":
                cmds.append(
                    f"SOURce{self.channel}:FUNCtion:RAMP:SYMMetry {self.params['duty_cycle']}"
                )

        cmds.extend([
            f"OUTPut{self.channel} ON",
            f"DISPlay:FOCus CH{self.channel}",
        ])

        if not self.run_cmds(cmds):
            raise RuntimeError("Failed to configure Agilent33512B")
        self.beep()

    def output_enable(self) -> None:
        """使能输出"""
        if not self.run_cmds([f"OUTPut{self.channel} ON"]):
            raise RuntimeError("Failed to enable output")

    def output_disable(self) -> None:
        """关闭输出"""
        self.run_cmds([f"OUTPut{self.channel} OFF", "OUTPut2 OFF"])

    def set_frequency(self, freq: float) -> None:
        self.run_cmds([f"SOURce{self.channel}:FREQuency {freq}"])

    def set_amplitude(self, vpp: float) -> None:
        self.run_cmds([f"SOURce{self.channel}:VOLTage {vpp}"])

    def set_offset(self, offset: float) -> None:
        self.run_cmds([f"SOURce{self.channel}:VOLTage:OFFSet {offset}"])

    def close(self) -> None:
        """关闭输出"""
        self.output_disable()


# 注册到仪器注册表
InstrumentRegistry.register_waveform_generator(
    "AGILENT::33512B",
    Agilent33512B,
    supported=("WAVEFORM",),
)