"""仪器管理器：封装仪器发现、连接与生命周期管理"""

import logging
from typing import Dict, List, Optional, Union

from .device_table import DeviceTable
from .instrument_types import InstrumentBase, InstrumentInfo
from .transport_backend import TransportBackend
from .visa_backend import VisaTransportBackend

logger = logging.getLogger(__name__)


class InstrumentManager:
    """仪器管理器

    负责发现已连接的仪器、建立连接、管理仪器实例的生命周期。
    支持同时注册多个 ``TransportBackend``，实现多协议仪器的统一管理。

    - 默认内置 ``VisaTransportBackend``
    - 通过 ``register_backend()`` 注册更多后端
    - ``discover()`` 返回 ``List[InstrumentInfo]``，含仪器能力信息

    Example:
        >>> mgr = InstrumentManager()
        >>> mgr.register_backend(SerialBackend())
        >>> info_list = mgr.discover()
        >>> for info in info_list:
        ...     print(info.address, info.label, info.inst_type, info.supported)
        >>> inst = mgr.open("COM3", "MOCK::DEVICE")
    """

    def __init__(
        self,
        device_table: Optional[Union[str, "DeviceTable"]] = None,
        backends: Optional[List[TransportBackend]] = None,
    ) -> None:
        """初始化仪器管理器

        Args:
            device_table: 设备信息表。可以是：

                - ``str``: JSON 文件路径，自动加载
                - ``DeviceTable``: 已有实例
                - ``None``: 创建空的内存表（不读写文件）

            backends: 传输后端列表，默认为 ``[VisaTransportBackend()]``
        """
        if isinstance(device_table, str):
            self._device_table = DeviceTable(device_table)
        elif isinstance(device_table, DeviceTable):
            self._device_table = device_table
        else:
            self._device_table = DeviceTable()

        if backends is None:
            backends = [VisaTransportBackend(device_table=self._device_table)]

        self._backends: List[TransportBackend] = list(backends)
        self._connections: Dict[str, InstrumentBase] = {}
        self._connection_backend: Dict[str, TransportBackend] = {}

    def save_device_table(self, path: Optional[str] = None) -> None:
        """持久化设备信息表

        Args:
            path: 目标路径。为 ``None`` 时使用当前关联路径（如果也没有则静默跳过）
        """
        if path is not None:
            self._device_table.path = path
        self._device_table.save()

    @property
    def backends(self) -> List[TransportBackend]:
        """当前已注册的所有后端"""
        return list(self._backends)

    def register_backend(self, backend: TransportBackend) -> None:
        """注册一个新的传输后端

        Args:
            backend: 传输后端实例
        """
        self._backends.append(backend)
        logger.info(f"Registered backend: {backend.name}")

    def resolve(self, address: str) -> Optional[InstrumentInfo]:
        """解析仪器地址，返回仪器信息

        优先查 DeviceTable 缓存，未命中时回退到实时 ``*IDN?`` 查询。
        查询成功时自动写入缓存（按 label 去重）。

        Args:
            address: 仪器 VISA 地址

        Returns:
            InstrumentInfo，无法识别时返回 ``None``
        """
        info = self._device_table.build_info(address)
        if info is not None:
            return info

        for backend in self._backends:
            try:
                info = backend._identify(address)
                if info is not None:
                    self._device_table.set(
                        address,
                        info.label,
                        serial_baud=backend._serial_baud(address),
                        inst_type=info.inst_type.value,
                        supported=list(info.supported),
                    )
                    return info
            except Exception:
                continue

        return None

    def discover(self) -> List[InstrumentInfo]:
        """遍历所有后端，发现当前在线且身份已知的仪器（存在性检查）

        运行时默认路径，不做 `*IDN?`（除非后端允许自动识别，如 USB）。
        需要全量识别（尤其串口）时调用 :meth:`full_scan`。

        Returns:
            可用仪器列表，每个元素包含地址、标识、类别和支持能力。
            地址重复时，后面后端的发现结果覆盖前面的。
        """
        seen: Dict[str, int] = {}
        rc: List[InstrumentInfo] = []

        for backend in self._backends:
            try:
                logger.info(f"Discovering instruments...")
                found = backend.discover()
                logger.info(f"Discovery complete.")
                if found:
                    logger.info(
                        f"Discovered {len(found)} instrument(s)"
                    )
                    for info in found:
                        idx = seen.get(info.address)
                        if idx is not None:
                            logger.warning(
                                f"Address {info.address} already discovered by "
                                f"another backend, overwriting with {backend.name}"
                            )
                            rc[idx] = info
                        else:
                            seen[info.address] = len(rc)
                            rc.append(info)
            except Exception as ex:
                logger.warning(f"[{backend.name}] discover failed: {ex}")

        return rc

    def full_scan(self) -> List[InstrumentInfo]:
        """显式全量识别所有枚举到的设备并写回设备表

        与 ``discover()`` 不同，本方法会对每个地址执行 ``*IDN?``
        （串口还需逐档波特率试探），耗时较高。仅在设备连接变化
        （尤其串口换口、新增设备）后由用户显式调用，用于重建设备表。

        Returns:
            识别出的仪器列表，地址重复时后面后端的扫描结果覆盖前面的。
        """
        seen: Dict[str, int] = {}
        rc: List[InstrumentInfo] = []

        for backend in self._backends:
            try:
                logger.info(f"Scanning instruments with {backend.name}...")
                found = backend.scan()
                if found:
                    logger.info(f"Scanned {len(found)} instrument(s)")
                    for info in found:
                        idx = seen.get(info.address)
                        if idx is not None:
                            logger.warning(
                                f"Address {info.address} already scanned by "
                                f"another backend, overwriting with {backend.name}"
                            )
                            rc[idx] = info
                        else:
                            seen[info.address] = len(rc)
                            rc.append(info)
            except Exception as ex:
                logger.warning(f"[{backend.name}] scan failed: {ex}")

        return rc

    def open(self, address: str, label: str, timeout: int = 30000) -> InstrumentBase:
        """打开仪器连接

        依次尝试每个后端，直到成功打开连接。

        Args:
            address: 仪器地址
            label: 仪器标识，如 "KEITHLEY::DMM6500"
            timeout: 超时时间（毫秒）

        Returns:
            仪器实例

        Raises:
            RuntimeError: 所有后端均无法打开连接
        """
        if address in self._connections:
            logger.warning(f"Instrument {label}@{address} already opened")
            return self._connections[address]

        last_ex: Optional[Exception] = None
        for backend in self._backends:
            try:
                inst = backend.open(address, label, timeout)
                self._connections[address] = inst
                self._connection_backend[address] = backend
                logger.info(f"[{backend.name}] Opened {label} @ {address}")
                return inst
            except Exception as ex:
                logger.debug(
                    f"[{backend.name}] Failed to open {label} @ {address}: {ex}"
                )
                last_ex = ex
                continue

        raise RuntimeError(
            f"Cannot open instrument {label} @ {address}: "
            f"no suitable backend (tried {len(self._backends)} backend(s))"
        ) from last_ex

    def close(self, address: str) -> None:
        """关闭指定仪器的连接

        Args:
            address: 仪器地址
        """
        if address not in self._connections:
            return

        inst = self._connections.pop(address)
        backend = self._connection_backend.pop(address)
        backend.close(inst)
        logger.debug(f"[{backend.name}] Closed {address}")

    def close_all(self) -> None:
        """关闭所有已打开的仪器连接"""
        for address in list(self._connections.keys()):
            self.close(address)

    def shutdown(self) -> None:
        """关闭管理器，释放所有资源

        依次关闭所有连接，并调用各后端的 ``shutdown()`` 方法。
        """
        self.close_all()
        for backend in self._backends:
            try:
                backend.shutdown()
                logger.debug(f"[{backend.name}] Shutdown complete")
            except Exception as ex:
                logger.warning(f"[{backend.name}] shutdown failed: {ex}")
