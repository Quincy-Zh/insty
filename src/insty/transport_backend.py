"""传输后端抽象基类

模板方法模式：`discover()` 在基类实现，子类只需提供：

- `_enum()`: 枚举当前可达的地址列表
- `_identify()`: 通过 I/O 查询识别单台设备
- `_serial_baud()`: （可选）串口设备返回波特率
- `_allow_auto_identify()`: （可选）discover 时是否对该地址自动识别；
  同时决定该地址的设备信息存储在哪张表（稳定唯一 → 持久存储）

存储分派：地址稳定唯一的设备（如 USB/TCPIP，`_allow_auto_identify` 为 True）
走持久存储（跨项目保留）；串口等地址会漂移的设备走运行时设备表。

存在性检查（`discover()`，运行时默认路径，无 *IDN?*）→
查表回退识别（仅地址稳定唯一的设备，如 USB）→
显式全量识别（`scan()`，用户触发，针对串口等地址会漂移的设备）。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from .device_table import DeviceTable
from .instrument_types import Instrument, InstrumentInfo

logger = logging.getLogger(__name__)


class TransportBackend(ABC):
    """传输后端抽象基类"""

    def __init__(
        self,
        device_table: str | None = None,
        persistent_store: str | None = None,
    ) -> None:
        """初始化传输后端

        Args:
            device_table: 运行时设备信息表 JSON 文件路径（串口等地址会漂移的设备）。
                为 ``None`` 时不持表（由 InstrumentManager 注入共享表）
            persistent_store: 持久设备存储 JSON 文件路径（USB/TCPIP 等地址稳定唯一的设备）。
                为 ``None`` 时不持表（由 InstrumentManager 注入共享表）
        """
        self._device_table = (
            DeviceTable(device_table) if isinstance(device_table, str) else None
        )
        self._persistent_store = (
            DeviceTable(persistent_store) if isinstance(persistent_store, str) else None
        )

    def _storage_for(self, address: str) -> DeviceTable | None:
        """按地址类型选择存储：稳定唯一（如 USB/TCPIP）→ 持久存储；其余 → 运行时表"""
        if self._allow_auto_identify(address):
            return self._persistent_store
        return self._device_table

    @property
    def name(self) -> str:
        """后端名称（用于日志），默认为类名"""
        return type(self).__name__

    # ── 子类需实现的抽象方法 ────────────────────────────

    @abstractmethod
    def _enum(self) -> list[str]:
        """枚举当前可达的仪器地址列表

        Returns:
            地址列表
        """

    @abstractmethod
    def _identify(self, address: str) -> InstrumentInfo | None:
        """通过 I/O 查询识别单台设备（discover 回退 / scan 时调用）

        Args:
            address: 仪器地址

        Returns:
            识别成功返回 InstrumentInfo，否则返回 None
        """

    @abstractmethod
    def open(self, address: str, label: str, timeout: int) -> Instrument:
        """打开仪器连接

        Args:
            address: 仪器地址
            label: 仪器标识，如 "KEITHLEY::DMM6500"
            timeout: 超时时间（毫秒）

        Returns:
            仪器实例
        """

    # ── 可选钩子 ────────────────────────────────────────

    def _serial_baud(self, address: str) -> int | None:
        """返回串口设备的波特率（非串口返回 None）

        子类可重写此方法以提供波特率信息。
        """
        return None

    def _allow_auto_identify(self, address: str) -> bool:
        """``discover()`` 存在性检查阶段是否允许对该地址自动 ``*IDN?``

        默认 ``False``（存在性检查不做任何识别 I/O）。
        地址稳定唯一的设备（如 USB 内嵌序列号）可返回 ``True`` 实现即插即用；
        串口等地址会漂移的设备保持 ``False``，由显式 ``scan()`` 识别。

        该返回值同时兼作存储分派（见 :meth:`_storage_for`）：
        ``True`` 表示地址稳定唯一，设备信息持久化存储。

        Args:
            address: 仪器地址

        Returns:
            允许自动识别返回 True
        """
        return False

    # ── 模板方法 ────────────────────────────────────────

    def discover(self) -> list[InstrumentInfo]:
        """发现当前在线且身份已知的仪器（存在性检查，默认不做 *IDN?）

        模板方法：
        1. `_enum()` 枚举地址
        2. 按地址类型查对应存储（`_storage_for()`，命中则跳过 I/O）
        3. 未命中且 ``_allow_auto_identify()`` 允许时调用 ``_identify()`` 识别并写表

        需要全量识别（尤其串口）时调用 ``scan()``。

        Returns:
            可用仪器列表，每项包含地址、标识、类别和支持能力
        """
        rc: list[InstrumentInfo] = []

        for addr in self._enum():
            store = self._storage_for(addr)
            info: InstrumentInfo | None = None

            if store is not None:
                info = store.build_info(addr)

            if info is None and self._allow_auto_identify(addr):
                info = self._identify(addr)
                if info is not None and store is not None:
                    store.set(
                        addr,
                        info.label,
                        serial_baud=self._serial_baud(addr),
                        inst_type=info.inst_type.value,
                        supported=list(info.supported),
                        dedup_label=not self._allow_auto_identify(addr),
                    )

            if info is not None:
                logger.info(f"Discovered {addr} -> {info.label}")
                rc.append(info)
            else:
                logger.debug(f"{addr} -> Unknown")

        return rc

    def scan(self) -> list[InstrumentInfo]:
        """显式全量识别（对枚举到的每个地址执行 ``*IDN?`` 并写表）

        耗时较高（串口还需逐档波特率试探），仅在设备连接变化
        （尤其串口换口）时由用户显式调用，重建设备表。
        识别结果按地址类型写入对应存储（稳定唯一 → 持久存储）。

        Returns:
            识别出的仪器列表
        """
        rc: list[InstrumentInfo] = []

        for addr in self._enum():
            try:
                info = self._identify(addr)
            except Exception as ex:
                logger.warning(f"[{self.name}] Failed to identify {addr}: {ex}")
                info = None

            if info is not None:
                store = self._storage_for(addr)
                if store is not None:
                    store.set(
                        addr,
                        info.label,
                        serial_baud=self._serial_baud(addr),
                        inst_type=info.inst_type.value,
                        supported=list(info.supported),
                        dedup_label=not self._allow_auto_identify(addr),
                    )
                logger.info(f"Scanned {addr} -> {info.label}")
                rc.append(info)
            else:
                logger.info(f"{addr} -> Unknown")

        return rc

    def close(self, inst: Instrument) -> None:
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
