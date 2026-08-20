# KEITHLEY DMM6500 数字万用表

from __future__ import annotations

import logging
import time

from pyvisa.resources import Resource

from ..instrument_types import (
    DMM,
    InstrumentRegistry,
)
from ..visa_based_instrument import VisaBasedInstrument

logger = logging.getLogger(__name__)

_SUPPORTED_FUNCS = {
    "voltage_dc": "VOLTage:DC",
    "voltage_ac": "VOLTage:AC",
    "current_dc": "CURRent:DC",
    "current_ac": "CURRent:AC",
    "resistance": "RESistance",
    "temperature": "TEMPerature",
}


class KeithleyDMM6500(VisaBasedInstrument, DMM):
    """Keithley DMM6500 数字万用表驱动"""

    def __init__(self, resource: Resource | None) -> None:
        super().__init__(resource)
        logger.debug(f"Initializing KeithleyDMM6500 with {resource}")
        self.buffer_size = 100
        self.me_cmds = []

    def _reset_target(self) -> None:
        """复位万用表"""
        self.run_cmds(["*RST", "*CLS"])

        cnt = 0
        while cnt < 5:
            resp = self.query("*OPC?")
            if resp and resp.startswith("+0"):
                break
            cnt += 1
            time.sleep(0.1)

    def _read_statistics(self, buffer_name: str) -> dict[str, float] | None:
        """从数据缓冲区读取统计值"""
        statistics_values = {}
        for el in ("MINimum", "AVERage", "MAXimum", "STDDev"):
            cmd = f':TRACe:STATistics:{el}? "{buffer_name}"'
            resp = self.query(cmd)
            if resp:
                statistics_values[el.lower()] = float(resp)
        return statistics_values

    def _wait_buffer_ready(
        self, buffer_name: str, element_cnt: int, timeout: int = 10
    ) -> bool:
        """检查缓存区数据是否足够"""
        end_idx = 0
        seconds = time.time()
        while end_idx != element_cnt:
            resp = self.query(f':TRACe:ACTual:END? "{buffer_name}"')
            if resp:
                try:
                    end_idx = int(resp)
                except Exception as ex:
                    logger.error(f"Fail to read buffer END: {ex}")
                    self.run_cmds(["*CLS"])

            if time.time() - seconds > timeout:
                logger.error(f"Timeout, no enough element in buffer {buffer_name}")
                return False
            time.sleep(0.01)
        return True

    def _setup(self, key: str, param: dict) -> None:
        """配置测量参数"""
        key = key.lower()
        if key not in _SUPPORTED_FUNCS:
            raise ValueError(f"Unsupported measurement type: {key}")

        range_ = param.get("range")
        if range_ is not None and (
            not isinstance(range_, (int, float)) or range_ < 1e-12
        ):
            raise ValueError("'range' parameter must be a positive number or None")

        power_line_cycles = param.get("power_line_cycles")
        if power_line_cycles is not None:
            if not isinstance(power_line_cycles, (int, float)):
                raise ValueError("'power_line_cycles' parameter must be a number")
            if not (0.0005 <= power_line_cycles <= 12):
                raise ValueError("'power_line_cycles' out of range (0.0005 - 12)")

        autozero = param.get("autozero", True)
        if not isinstance(autozero, bool):
            raise TypeError("'autozero' parameter must be a boolean")

        filter_opt = param.get("filter")
        if filter_opt is not None and not (
            isinstance(filter_opt, dict)
            and "type" in filter_opt
            and "count" in filter_opt
        ):
            raise ValueError(
                "'filter' parameter must be a dict with 'type' and 'count'"
            )

        func = _SUPPORTED_FUNCS[key]
        buffer_size = param.get("buffer_size", 100)
        if not isinstance(buffer_size, int) or buffer_size <= 0:
            raise ValueError("'buffer_size' parameter must be a positive integer")
        self.buffer_size = buffer_size

        self.me_cmds = [
            "*RST",
            "*CLS",
            f':SENS:FUNC "{func}"',
        ]

        if key not in ("temperature", "frequency"):
            if range_ is None:
                self.me_cmds.append(f":SENS:{func}:RANG:AUTO ON")
            else:
                self.me_cmds.append(f":SENS:{func}:RANG {range_}")

            if power_line_cycles:
                self.me_cmds.append(f":SENS:{func}:NPLC {power_line_cycles}")

            if autozero:
                self.me_cmds.append(f":SENS:{func}:AZER ON")
            else:
                self.me_cmds.append(f":SENS:{func}:AZER OFF")

        if filter_opt:
            self.me_cmds.extend(
                [
                    f':SENS:{func}:AVER:TCON {filter_opt["type"]}',
                    f':SENS:{func}:AVER:COUN {filter_opt["count"]}',
                    f":SENS:{func}:AVER ON",
                ]
            )

        self.me_cmds.extend(
            [
                f':TRACe:MAKE "MyBuffer", {self.buffer_size}',
                ':TRACe:CLE "MyBuffer"',
                f":SENS:COUN {self.buffer_size}",
                ':TRACe:TRIG "MyBuffer"',
            ]
        )

    def read_voltage(self, params: dict | None = None) -> float | None:
        """读取直流电压，测量失败时返回 None"""
        params = params or {}
        self._setup("voltage_dc", params)
        return self._measure("voltage_dc")

    def read_current(self, params: dict | None = None) -> float | None:
        """读取直流电流，测量失败时返回 None"""
        params = params or {}
        self._setup("current_dc", params)
        return self._measure("current_dc")

    def _measure(self, key: str) -> float | None:
        """执行测量并返回平均值，失败时返回 None"""
        self._reset_target()
        if not self.run_cmds(self.me_cmds):
            return None

        if not self._wait_buffer_ready(
            "MyBuffer", self.buffer_size, int(self.buffer_size / 5)
        ):
            return None

        statistics = self._read_statistics("MyBuffer")
        self.run_cmds([':TRACe:DELete "MyBuffer"'])

        if statistics:
            return statistics.get("average")
        return None

    def _close(self) -> None:
        """复位仪器并释放 VISA 连接"""
        try:
            self._reset_target()
        except Exception as ex:
            logger.warning(f"Error during close: {ex}")
        super()._close()


# 注册到仪器注册表
InstrumentRegistry.register_dmm(
    "KEITHLEY::DMM6500",
    KeithleyDMM6500,
    supported=("VOLTAGE_DC", "CURRENT_DC", "RESISTANCE", "VOLTAGE_AC", "CURRENT_AC"),
)
