"""传输后端抽象基类

模板方法模式：`discover()` 在基类实现，子类只需提供：

- `_enum()`: 枚举当前可达的地址列表
- `_identify()`: 通过 I/O 查询识别单台设备
- `_serial_baud()`: （可选）串口设备返回波特率
- `_allow_auto_identify()`: （可选）discover 时是否对该地址自动识别

存在性检查（`discover()`，运行时默认路径，无 *IDN?*）→
查表回退识别（仅地址稳定唯一的设备，如 USB）→
显式全量识别（`scan()`，用户触发，针对串口等地址会漂移的设备）。
"""

import logging
from abc import ABC, abstractmethod
from typing import List, Optional

from .device_table import DeviceTable
from .instrument_types import InstrumentBase, InstrumentInfo

logger = logging.getLogger(__name__)


class TransportBackend(ABC):
    """传输后端抽象基类"""

    def __init__(self, device_table: Optional[DeviceTable] = None) -> None:
        """初始化传输后端

        Args:
            device_table: 设备信息表，用于缓存已知设备的能力信息
        """
        self._device_table = device_table

    @property
    def name(self) -> str:
        """后端名称（用于日志），默认为类名"""
        return type(self).__name__

    # ── 子类需实现的抽象方法 ────────────────────────────

    @abstractmethod
    def _enum(self) -> List[str]:
        """枚举当前可达的仪器地址列表

        Returns:
            地址列表
        """
        pass

    @abstractmethod
    def _identify(self, address: str) -> Optional[InstrumentInfo]:
        """通过 I/O 查询识别单台设备（discover 回退 / scan 时调用）

        Args:
            address: 仪器地址

        Returns:
            识别成功返回 InstrumentInfo，否则返回 None
        """
        pass

    @abstractmethod
    def open(self, address: str, label: str, timeout: int) -> InstrumentBase:
        """打开仪器连接

        Args:
            address: 仪器地址
            label: 仪器标识，如 "KEITHLEY::DMM6500"
            timeout: 超时时间（毫秒）

        Returns:
            仪器实例
        """
        pass

    # ── 可选钩子 ────────────────────────────────────────

    def _serial_baud(self, address: str) -> Optional[int]:
        """返回串口设备的波特率（非串口返回 None）

        子类可重写此方法以提供波特率信息。
        """
        return None

    def _allow_auto_identify(self, address: str) -> bool:
        """``discover()`` 存在性检查阶段是否允许对该地址自动 ``*IDN?``

        默认 ``False``（存在性检查不做任何识别 I/O）。
        地址稳定唯一的设备（如 USB 内嵌序列号）可返回 ``True`` 实现即插即用；
        串口等地址会漂移的设备保持 ``False``，由显式 ``scan()`` 识别。

        Args:
            address: 仪器地址

        Returns:
            允许自动识别返回 True
        """
        return False

    # ── 模板方法 ────────────────────────────────────────

    def discover(self) -> List[InstrumentInfo]:
        """发现当前在线且身份已知的仪器（存在性检查，默认不做 *IDN?）

        模板方法：
        1. `_enum()` 枚举地址
        2. 查 `DeviceTable` 获取信息（命中则跳过 I/O）
        3. 未命中且 ``_allow_auto_identify()`` 允许时调用 ``_identify()`` 识别并写表

        需要全量识别（尤其串口）时调用 ``scan()``。

        Returns:
            可用仪器列表，每项包含地址、标识、类别和支持能力
        """
        rc: List[InstrumentInfo] = []

        for addr in self._enum():
            info: Optional[InstrumentInfo] = None

            if self._device_table is not None:
                info = self._device_table.build_info(addr)

            if info is None and self._allow_auto_identify(addr):
                info = self._identify(addr)
                if info is not None and self._device_table is not None:
                    self._device_table.set(
                        addr,
                        info.label,
                        serial_baud=self._serial_baud(addr),
                        inst_type=info.inst_type.value,
                        supported=list(info.supported),
                    )

            if info is not None:
                logger.info(f"Discovered {addr} -> {info.label}")
                rc.append(info)
            else:
                logger.debug(f"{addr} -> Unknown")

        return rc

    def scan(self) -> List[InstrumentInfo]:
        """显式全量识别（对枚举到的每个地址执行 ``*IDN?`` 并写表）

        耗时较高（串口还需逐档波特率试探），仅在设备连接变化
        （尤其串口换口）时由用户显式调用，重建设备表。

        Returns:
            识别出的仪器列表
        """
        rc: List[InstrumentInfo] = []

        for addr in self._enum():
            try:
                info = self._identify(addr)
            except Exception as ex:
                logger.warning(f"[{self.name}] Failed to identify {addr}: {ex}")
                info = None

            if info is not None:
                if self._device_table is not None:
                    self._device_table.set(
                        addr,
                        info.label,
                        serial_baud=self._serial_baud(addr),
                        inst_type=info.inst_type.value,
                        supported=list(info.supported),
                    )
                logger.info(f"Scanned {addr} -> {info.label}")
                rc.append(info)
            else:
                logger.info(f"{addr} -> Unknown")

        return rc

    def close(self, inst: InstrumentBase) -> None:
        """关闭仪器连接

        Args:
            inst: 仪器实例
        """
        try:
            inst.close()
        except Exception as ex:
            logger.warning(f"Error closing instrument: {ex}")

    def shutdown(self) -> None:
        """释放后端占用的资源（可选重写）"""
        pass
