# 频率计：AGILENT::53220A

from __future__ import annotations

import logging
import math

from pyvisa.resources import Resource

from ..instrument_types import (
    FrequencyCounter,
    InstrumentRegistry,
)
from ..visa_based_instrument import VisaBasedInstrument

logger = logging.getLogger(__name__)

_MEAS_MAP = {
    "frequency": "FREQuency",
    "duty_cycle": "PDUTycycle",
    "period": "PERiod",
    "pulse_width": "PWIDth",
}


class Agilent53220A(VisaBasedInstrument, FrequencyCounter):
    """Agilent 53220A 频率计驱动"""

    def __init__(self, resource: Resource | None) -> None:
        super().__init__(resource)
        logger.debug(f"Initializing AGILENT::53220A with {resource}")
        self.channel = 1
        self.beep_ = False

    def beep(self):
        if self.beep_:
            self.run_cmds(["SYSTem:BEEPer"])

    def read_frequency(self, channel: int = 1) -> float:
        """测量波形频率（Hz）"""
        try:
            x = self.query(f"MEASure:FREQuency? (@{channel})")
            return float(x) if x else math.nan
        except Exception as e:
            logger.error(f"Error reading frequency: {e}")
            return math.nan

    def read_duty_cycle(self, channel: int = 1) -> float:
        """测量波形占空比（比值 0~1）"""
        try:
            x = self.query(f"MEASure:PDUTycycle? (@{channel})")
            return float(x) if x else math.nan
        except Exception as e:
            logger.error(f"Error reading duty cycle: {e}")
            return math.nan

    def close(self) -> None:
        """释放 VISA 连接"""
        super().close()


# 注册到仪器注册表
InstrumentRegistry.register_frequency_counter(
    "AGILENT::53220A",
    Agilent53220A,
    supported=("FREQUENCY", "DUTY_CYCLE", "PERIOD", "PULSE_WIDTH"),
)