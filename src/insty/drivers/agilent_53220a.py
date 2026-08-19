# 频率计：AGILENT::53220A

from __future__ import annotations

import logging

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

    def read_frequency(self, channel: int = 1) -> float | None:
        """测量波形频率（Hz）

        值无效（INFinity 或 >= 9.9E+37）或查询失败时返回 None
        """
        try:
            x = self.query(f"MEASure:FREQuency? (@{channel})")
            if not x:
                return None
            val = float(x)
            if val >= 9.9e37:
                return None
            return val
        except Exception as e:
            logger.error(f"Error reading frequency: {e}")
            return None

    def read_duty_cycle(self, channel: int = 1) -> float | None:
        """测量波形占空比（比值 0~1），查询失败时返回 None"""
        try:
            x = self.query(f"MEASure:PDUTycycle? (@{channel})")
            return float(x) if x else None
        except Exception as e:
            logger.error(f"Error reading duty cycle: {e}")
            return None

    def close(self) -> None:
        """释放 VISA 连接"""
        super().close()


# 注册到仪器注册表
InstrumentRegistry.register_frequency_counter(
    "AGILENT::53220A",
    Agilent53220A,
    supported=("FREQUENCY", "DUTY_CYCLE", "PERIOD", "PULSE_WIDTH"),
)