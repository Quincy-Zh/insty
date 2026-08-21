# ITECH IT6302 数字电源

from __future__ import annotations

import logging

from pyvisa.resources import Resource
from typing_extensions import Self

from ..instrument_types import (
    InstrumentRegistry,
    PowerSupply,
)
from ..visa_based_instrument import VisaBasedInstrument

logger = logging.getLogger(__name__)


class ItechIT6302(VisaBasedInstrument, PowerSupply):
    """ITECH IT6302 数字电源驱动"""

    def __init__(self, resource: Resource | None) -> None:
        super().__init__(resource)
        logger.debug(f"Initializing Itech::IT6302 with {resource}")
        self.channel = 1
        self.output_enabled = False

        cmds = ["SYSTem:REMote"]
        self.run_cmds(cmds)

    @property
    def channels(self) -> int:
        return 3

    def set_voltage(self, volt: float, channel: int = 1) -> Self:
        """设置输出电压并自动使能输出"""
        if not (0.0 <= volt <= 32.0):
            raise ValueError("'voltage' parameter out of range (0.0 - 32.0)")

        if not (1 <= channel <= 3):
            raise ValueError("'channel' parameter out of range (1 - 3)")

        cmds = [
            f"INSTrument:SELect CH{channel}",
            f"VOLTage:LEVel {volt}",
        ]
        if not self.run_cmds(cmds):
            raise RuntimeError(f"Failed to set voltage {volt}V on CH{channel}")

        if not self.output_enabled:
            self.output_enable(channel)
            
        return self

    def output_enable(self, channel: int = 0) -> Self:
        """使能输出"""
        s = "ON"
        if channel < 1:
            cmds = [f"OUTPut:STATe {s}"]
        else:
            cmds = [
                f"INSTrument:SELect CH{channel}",
                f"CHANnel:OUTPut:STATe {s}",
            ]
        if not self.run_cmds(cmds):
            raise RuntimeError(f"Failed to enable output on CH{channel}")
        self.output_enabled = True
        return self

    def output_disable(self, channel: int = 0) -> Self:
        """关闭输出"""
        s = "OFF"
        if channel < 1:
            cmds = [f"OUTPut:STATe {s}"]
        else:
            cmds = [
                f"INSTrument:SELect CH{channel}",
                f"CHANnel:OUTPut:STATe {s}",
            ]
        if not self.run_cmds(cmds):
            raise RuntimeError(f"Failed to disable output on CH{channel}")
        self.output_enabled = False
        return self

    def _close(self) -> None:
        """关闭仪器：设置安全电压、关闭输出并释放 VISA 连接"""
        try:
            self.set_voltage(3.3, 3)
            self.set_voltage(3.3, 2)
            self.set_voltage(3.3, 1)
            self.output_disable(0)
            self.run_cmds(["SYSTem:Loc"])
        except Exception as ex:
            logger.warning(f"Error during close: {ex}")
        super()._close()


# 注册到仪器注册表
InstrumentRegistry.register_power_supply(
    "ITECH::IT6302",
    ItechIT6302,
    supported=("VOLTAGE",),
)