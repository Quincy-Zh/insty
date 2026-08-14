# 高低温发生器：TEMPTRONIC::ATS-710

from __future__ import annotations

import logging
import time
from typing import ClassVar

from pyvisa.resources import Resource

from ..instrument_types import (
    InstrumentRegistry,
    ThermalChamberBase,
)
from ..visa_based_instrument import VisaBasedInstrument

logger = logging.getLogger(__name__)


class TemptronicATS710(VisaBasedInstrument, ThermalChamberBase):
    """TEMPTRONIC ATS-710 高低温发生器驱动"""

    SUPPORTED_ACTIONS: ClassVar = {
        "head down": "HEAD 1",
        "head up": "HEAD 0",
    }

    ERROR_REGISTER_BIT_MAP: ClassVar = {
        14: "No DUT sensor selected",
        12: "BVRAM fault",
        11: "NVRAM fault",
        10: "No Line Sense",
        9: "Flow sensor hardware error",
        7: "Internal error",
        5: "Air sensor open",
        4: "Low input air pressure",
        3: "Low flow",
        1: "Air open loop",
        0: "Overheat",
    }

    AUXC_REGISTER_BIT_MAP: ClassVar = {
        9: ("Ramp mode Off", "Ramp mode On"),
        8: ("Program", "Manual Mode"),
        6: ("Startup", "Ready"),
        5: ("Flow Off", "Flow On"),
        4: ("Air-control Mode", "DUT Mode"),
        3: ("Compressor on", "Heat only mode"),
        2: ("Head up", "Head down"),  # bit2 的逻辑故意取反的
    }

    TEMPERATURE_EVENT_REGISTER_BIT_MAP: ClassVar = {
        5: "stopped cycling",
        4: "end of all cycles",
        3: "end of one cycle",
        2: "end of test",
        1: "not at temperature",
        0: "at temperature",
    }

    def __init__(self, resource: Resource | None) -> None:
        super().__init__(resource)
        logger.debug(f"Initializing TEMPTRONIC::ATS-710 with {resource}")

    def _read_register(self, cmd: str) -> int:
        """读取寄存器:
        - `AUXC?`: Read the auxiliary condition register.
        - `TECR?`: Read the temperature event condition register.
        - `EROR?`: Read the device-specific error register (16 bits).
        """

        resp = self.query(cmd)
        if not resp:
            logger.warning(f'No resp, command: "{cmd}"')
            return 0
        try:
            val = int(resp)
        except ValueError:
            logger.error(f'Fail to parse resp: "{resp}')
            val = 0

        return val

    def _read_auxiliary_condition_register(self) -> dict[int, str]:
        reg_val = self._read_register("AUXC?")
        logger.debug(f"AUXC: {reg_val:010b}.")
        rc = {}

        reg_val ^= 1 << 2  # bit2: head up=1, head down=0 这里取反，1表示下压

        for bitoffset, items in self.AUXC_REGISTER_BIT_MAP.items():
            s = (reg_val >> bitoffset) & 1
            rc[bitoffset] = items[s]

        return rc

    def _read_temperature_event_register(self) -> dict[int, str]:
        reg_val = self._read_register("TECR?")
        logger.debug(f"TECR: {reg_val:08b}.")
        rc = {}
        for bitoffset, text in self.TEMPERATURE_EVENT_REGISTER_BIT_MAP.items():
            if ((reg_val >> bitoffset) & 1) == 1:
                rc[bitoffset] = text

        return rc

    def setup(self) -> None:
        """初始化:
        - 停止 cycling
        - Enter Ramp
        - 使能 DUT mode
        - 设置气流流速 FLSE 15 SCFM
        - 启动 Flow
        """
        if not self.run_cmds(["CYCL 0; RMPC 1; DUTM 1; FLSE 15; FLOW 1"]):
            raise RuntimeError("Failed to setup")

    def set_temperature(self, temp: float, soak: int = 15) -> None:
        """设置目标温度"""
        if not (-40.0 <= temp <= 150.0):
            raise ValueError("'temperature' parameter out of range (-40.0 - 150.0)")

        logger.debug(f"Setting temperature to {temp} °C, soak={soak}s")

        """设置温度值"""
        ch = 1  # 常温通道
        if temp <= 20:
            ch = 2  # 制冷通道
        elif temp >= 30:
            ch = 0  # 制热通道

        if not self.run_cmds([f"SETN {ch}; SOAK {soak}; SETN {ch}; SETP {temp:0.1f}"]):
            raise RuntimeError(f"Failed to set temperature to {temp} °C")

    def get_temperature(self) -> float | None:
        """读取当前温度"""
        resp = self.query("TEMP?")
        if resp:
            try:
                return float(resp)
            except (TypeError, ValueError):
                logger.error(f"Invalid temperature value received: {resp}")
        return None

    def execute(self, action: str) -> None:
        """执行动作"""
        action_ = action.lower()

        if action_ not in self.SUPPORTED_ACTIONS:
            logger.warning(f"Invalid {action}")
        else:
            self.run_cmds([self.SUPPORTED_ACTIONS[action_]])

    def wait(self, timeout: int = 150) -> bool:
        """等待温度稳定"""
        ts = time.time()
        while time.time() - ts < timeout:
            rc = self._read_temperature_event_register()

            if 0 in rc:
                # bit0: at temperature
                return True

            t = self.get_temperature()
            logger.debug(f"Current Temp.: {t}")
            time.sleep(3)

        logger.warning(f"温度稳定等待超时 ({timeout}s)")
        return False

    def ready(self) -> bool:
        status = self._read_auxiliary_condition_register()
        return 2 in status  # bit2: head down

    def get_error(self) -> list[str]:
        rc = []
        reg_val = self._read_register("EROR?")
        logger.debug(f"EROR: {reg_val:016b}.")

        for bitoffset, title in self.ERROR_REGISTER_BIT_MAP.items():
            if reg_val & (1 << bitoffset) == 0:
                continue
            rc += title

        return rc

    def close(self) -> None:
        """关闭仪器：设置为室温"""
        try:
            self.set_temperature(25.0)
        except RuntimeError as ex:
            logger.warning(f"Error during close: {ex}")


# 注册到仪器注册表
InstrumentRegistry.register_thermal_chamber(
    "TEMPTRONIC::ATS-710",
    TemptronicATS710,
    supported=("TEMPERATURE",),
)
