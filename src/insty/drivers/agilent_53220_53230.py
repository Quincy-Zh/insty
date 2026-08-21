# Agilent 53220A / 53230A 频率计

from __future__ import annotations

import logging

from pyvisa.resources import Resource
from typing_extensions import Self

from ..instrument_types import (
    FrequencyCounter,
    InstrumentRegistry,
)
from ..utils import is_invalid_reading
from ..visa_based_instrument import VisaBasedInstrument

logger = logging.getLogger(__name__)

_MEAS_MAP = {
    "frequency": "FREQuency",
    "duty_cycle": "PDUTycycle",
    "period": "PERiod",
    "pulse_width": "PWIDth",
}


class Agilent53220Base(VisaBasedInstrument, FrequencyCounter):
    """Agilent 53220A/53230A 频率计公共基类"""

    def __init__(self, resource: Resource | None) -> None:
        super().__init__(resource)
        logger.debug(f"Initializing AGILENT 53220A/53230A with {resource}")
        self.channel = 1

    def _check_channel(self, channel: int) -> None:
        """校验通道号是否在 1~channels 范围内"""
        if not (1 <= channel <= self.channels):
            raise ValueError(f"channel out of range (1 - {self.channels})")

    def setup(self, *, channel: int = 1, **kwargs) -> Self:
        """配置输入通道参数

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
        self._check_channel(channel)
        coupling = kwargs.get("coupling")
        impedance = kwargs.get("impedance")
        range_val = kwargs.get("range")
        threshold = kwargs.get("threshold")
        low_pass_filter = kwargs.get("low_pass_filter")
        coupling = coupling if coupling is not None else "DC"
        impedance = impedance if impedance is not None else 1e6
        range_val = range_val if range_val is not None else 5
        low_pass_filter = low_pass_filter if low_pass_filter is not None else False

        if coupling.upper() not in ("AC", "DC"):
            raise ValueError("coupling must be 'AC' or 'DC'")
        if impedance not in (50, 1e6):
            raise ValueError("impedance must be 50 or 1e6")
        if not isinstance(low_pass_filter, bool):
            raise TypeError("low_pass_filter must be True or False")

        prefix = f"INPut{channel}"

        probe_factor_str = self.query(f"{prefix}:PROBe?")
        probe_factor = int(probe_factor_str) if probe_factor_str else 1
        if probe_factor == 1:
            valid_ranges = (5, 50)
        elif probe_factor == 10:
            valid_ranges = (50, 500)
        else:
            raise ValueError(f"unexpected probe factor {probe_factor}, must be 1 or 10")
        
        if range_val not in valid_ranges:
            raise ValueError(
                f"range must be {valid_ranges} with probe factor {probe_factor}:1"
            )

        cmds = [
            f"{prefix}:COUPling {coupling.upper()}",
            f"{prefix}:IMPedance {impedance}",
            f"{prefix}:RANGe {range_val}",
        ]

        if threshold is None:
            cmds.append(f"{prefix}:LEVel:AUTO ON")
        elif isinstance(threshold, str) and threshold.endswith("%"):
            percent = int(threshold.rstrip("%"))
            if not (10 <= percent <= 90):
                raise ValueError("threshold percent out of range (10-90)")
            cmds.append(f"{prefix}:LEVel:RELative {percent}")
        elif isinstance(threshold, (int, float)):
            if (range_val == 5 and not (-5.125 <= threshold <= 5.125)):
                raise ValueError("threshold out of range for 5V range (-5.125 to 5.125)")
            elif (range_val == 50 and not (-51.25 <= threshold <= 51.25)):
                raise ValueError("threshold out of range for 50V range (-51.25 to 51.25)")
            elif (range_val == 500 and not (-512.5 <= threshold <= 512.5)):
                raise ValueError("threshold out of range for 500V range (-512.5 to 512.5)")
            cmds.append(f"{prefix}:LEVel {threshold}")
        else:
            raise ValueError("threshold must be None, number, or percentage string")

        cmds.append(f"{prefix}:FILTer:STATe {'ON' if low_pass_filter else 'OFF'}")
        self.run_cmds(cmds)
        return self

    def read_frequency(self, channel: int = 1) -> float | None:
        """测量波形频率（Hz）

        值无效（INFinity 或 >= 9.9E+37）或查询失败时返回 None
        """
        self._check_channel(channel)
        try:
            x = self.query(f"MEASure:FREQuency? (@{channel})")
            if not x:
                return None
            val = float(x)
            if is_invalid_reading(val):
                return None
            return val
        except Exception as e:
            logger.error(f"Error reading frequency: {e}")
            return None

    def read_duty_cycle(self, channel: int = 1) -> float | None:
        """测量波形占空比（比值 0~1），查询失败时返回 None"""
        self._check_channel(channel)
        try:
            x = self.query(f"MEASure:PDUTycycle? (@{channel})")
            if not x:
                return None
            val = float(x)
            if is_invalid_reading(val):
                return None
            return val
        except Exception as e:
            logger.error(f"Error reading duty cycle: {e}")
            return None

    def _close(self) -> None:
        """释放 VISA 连接"""
        super()._close()


class Agilent53220A(Agilent53220Base):
    """Agilent 53220A 频率计驱动（2通道，可选第3通道）"""

    @property
    def channels(self) -> int:
        return 2


class Agilent53230A(Agilent53220Base):
    """Agilent 53230A 频率计驱动（3通道）"""

    @property
    def channels(self) -> int:
        return 3


# 注册到仪器注册表
InstrumentRegistry.register_frequency_counter(
    "AGILENT::53220A",
    Agilent53220A,
    supported=("FREQUENCY", "DUTY_CYCLE", "PERIOD", "PULSE_WIDTH"),
)
InstrumentRegistry.register_frequency_counter(
    "AGILENT::53230A",
    Agilent53230A,
    supported=("FREQUENCY", "DUTY_CYCLE", "PERIOD", "PULSE_WIDTH"),
)