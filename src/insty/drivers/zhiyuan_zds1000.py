# 示波器: ZHIYUAN::ZDS1000
# 致远电子 ZDS1000 系列示波器

from __future__ import annotations

import logging
import math
import time

from pyvisa.constants import VI_ATTR_ASRL_BAUD, VI_ATTR_TMO_VALUE
from pyvisa.resources import Resource
from typing_extensions import Self

from ..instrument_types import (
    InstrumentRegistry,
    Oscilloscope,
)
from ..visa_based_instrument import VisaBasedInstrument

logger = logging.getLogger(__name__)

_MEAS_MAP = {
    "frequency": "FREQuency",
    "duty_cycle": "PDUTy",
    "pulse_width_p": "PWIDth",
    "pulse_width_n": "NWIDth",
}


class ZDS1104(VisaBasedInstrument, Oscilloscope):
    """致远 ZDS1104 示波器驱动"""

    def __init__(self, resource: Resource | None) -> None:
        super().__init__(resource)
        logger.debug(f"Initializing ZHIYUAN::ZDS1104 with {resource}")
        self.channel = 1
        self.params = {}
        self.timeout = 300
        self.me_count = 100
        self.clear_before_execute_mesure = True

    def configure(self, **kwargs) -> Self:
        """配置示波器参数"""
        for key, value in kwargs.items():
            key_ = key.lower()
            if key_ == "baudrate":
                assert self.visa_inst is not None
                self.visa_inst.set_visa_attribute(VI_ATTR_TMO_VALUE, 10000)  # type: ignore
                self.visa_inst.set_visa_attribute(VI_ATTR_ASRL_BAUD, value)  # type: ignore
            elif key_ == "signal":
                if value == 1:
                    self.execute("single")
                    time.sleep(0.5)
            elif key_ == "key":
                if "pulse_width_p" in value or "pulse_width_n" in value:
                    self.me_count = 1
                    self.clear_before_execute_mesure = False
                    self.timeout = 10
                else:
                    self.me_count = 100
                    self.clear_before_execute_mesure = True
                    self.timeout = 300

        return self

    def _measure(
        self, key: str, channel: int = 1, count_min: int | None = None
    ) -> float:
        """执行单项测量并返回平均值"""
        if count_min is None:
            count_min = self.me_count

        arg_low = key.lower()
        if arg_low not in _MEAS_MAP:
            raise ValueError(f"Unsupported measurement type: {key}")

        if self.clear_before_execute_mesure:
            self.run_cmds([":CLEar"])

        item = _MEAS_MAP[arg_low]
        if not self.run_cmds([f":MEASure:{item} CHANnel{channel}"]):
            raise RuntimeError(f"Failed to start measurement for {key}")

        # 等待测量 count 个数足够
        count = 0
        ts = time.time()
        while count < count_min:
            count_str = self.query(f":MEASure:{item}:COUNt? CHANnel{channel}")
            if count_str:
                count_str = count_str.replace("\x00", "").strip()
                try:
                    count = int(count_str)
                except ValueError:
                    logger.warning(f"Invalid count value: {count_str}")

            if time.time() - ts > self.timeout:
                logger.warning(
                    f"Measurement timeout after {self.timeout} seconds. Collected count: {count} of {count_min}."
                )
                break
            time.sleep(0.5)

        v = self.query(f":MEASure:{item}:AVERage? CHANnel{channel}")
        if v:
            v = v.replace("\x00", "").strip()
            return float(v) if v else math.nan
        logger.warning(f"No value returned for {key}")
        return math.nan

    def read_frequency(self, channel: int = 1) -> float:
        """测量波形频率"""
        return self._measure("frequency", channel)

    def read_duty_cycle(self, channel: int = 1) -> float:
        """测量波形占空比"""
        return self._measure("duty_cycle", channel)

    def read_pulse(self, channel: int = 1) -> float:
        """测量波形脉宽"""
        return self._measure("pulse_width_p", channel)

    def execute(self, mode: str) -> Self:
        """切换运行模式: single/run/stop"""
        mode_lower = mode.lower()
        cmds = {"single": ":SINGle", "run": ":RUN", "stop": ":STOP"}

        if mode_lower not in cmds:
            raise ValueError(f"Unsupported mode: {mode}")

        if not self.run_cmds([cmds[mode_lower]]):
            logger.warning(f'Fail to exec "{mode}"')
        return self

    def read_image(self) -> bytes:

        # current timeout value, milliseconds
        timeout_ = self.visa_inst.timeout  # type: ignore
        self.visa_inst.timeout = 20000  # type: ignore

        data_ = bytearray()

        try:
            data = self.visa_inst.read_bytes(11)  # type: ignore
            logger.debug(f"Image head: {data}")

            if data[:2] == b"#9":
                sz = int(data[2:])

                block_sz = 1024 * 1024

                while sz > 0:

                    if sz > block_sz:
                        s = block_sz
                    else:
                        s = sz

                    data = self.visa_inst.read_bytes(s)  # type: ignore
                    data_ += data
                    sz -= len(data)

                self.visa_inst.read_bytes(1)  # type: ignore # 文件尾 '\n'(0x0A)
            else:
                logger.warning(f'Invalid resp: {data[:16].hex(" ")}')
        except Exception as ex:
            logger.warning(f"Fail to read image data: {ex}")
            data_.clear()

        self.visa_inst.timeout = timeout_  # type: ignore

        return bytes(data_)

    def screenshot(self) -> bytes:
        """截屏，返回图片字节数据"""
        try:
            self.run_cmds([":PRINt"])
            time.sleep(8)
            self.run_cmds([":DISPlay:DATA?"])
            data = self.read_image()
            if data == b"":
                data = self.read_image()

            return data

        except Exception as ex:
            logger.error(f"Screenshot failed: {ex}")
            return b""

    def get_status(self) -> str:
        s = self.query(":GLOBal:RUN:STATe?")
        return s.strip().lower() if s else ""

    def close(self) -> None:
        """释放 VISA 连接"""
        super().close()


# 注册到仪器注册表
InstrumentRegistry.register_oscilloscope(
    "ZHIYUAN::ZDS1104",
    ZDS1104,
    supported=("FREQUENCY", "DUTY_CYCLE", "PULSE_WIDTH"),
)
