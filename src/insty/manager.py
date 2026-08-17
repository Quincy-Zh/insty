"""仪器管理器：封装仪器发现、连接与生命周期管理，并提供按类别的角色化接口"""

from __future__ import annotations

import logging
import os
import subprocess
import time

from typing_extensions import Self

from .device_table import DeviceTable
from .instrument_types import InstrumentBase, InstrumentInfo
from .roles import (
    _ROLES,
    DMMRole,
    FrequencyCounterRole,
    OscilloscopeRole,
    PowerSupplyRole,
    ThermalChamberRole,
    WaveformGeneratorRole,
)
from .transport_backend import TransportBackend
from .visa_backend import VisaTransportBackend

logger = logging.getLogger(__name__)

_DEFAULT_PERSISTENT_STORE = os.path.join(
    os.path.expanduser("~"), ".insty", "known_devices.json"
)


def frange(start, stop, step=1.0) -> list[float]:
    """浮点等差数列（含端点），行为与 JSON 版 ``start~end,step`` 语法一致"""
    if step == 0:
        raise ValueError("step 不能为 0")
    n = max(0, round((stop - start) / step) + 1)
    return [round(start + i * step, 12) for i in range(n)]


class InstrumentManager:
    """仪器管理器

    负责发现已连接的仪器、建立连接、管理仪器实例的生命周期，并按仪器类别
    提供角色化访问接口（``get_power_supply()`` 等），无需关心具体地址与型号。
    支持同时注册多个 ``TransportBackend``，实现多协议仪器的统一管理。

    - 默认内置 ``VisaTransportBackend``
    - 通过 ``register_backend()`` 注册更多后端
    - ``discover()`` 返回 ``List[InstrumentInfo]``，含仪器能力信息
    - ``get_dmm()`` 等角色接口按类别匹配并返回角色封装实例

    设备信息按地址类型分两类存储：

    - 运行时设备表（``device_table``）：串口（ASRL）等地址会漂移的设备
    - 持久设备存储（``persistent_store``）：USB/TCPIP 等地址稳定唯一的设备，
      默认 ``~/.insty/known_devices.json``（可用环境变量 ``INSTY_DEVICE_STORE`` 覆盖）

    Example:
        >>> mgr = InstrumentManager()
        >>> mgr.register_backend(SerialBackend())
        >>> info_list = mgr.discover()
        >>> for info in info_list:
        ...     print(info.address, info.label, info.inst_type, info.supported)
        >>> inst = mgr.open("COM3", "MOCK::DEVICE")
        >>> ps = mgr.get_power_supply()          # 按类别获取，无需地址/型号
        >>> ps.set_voltage(3.3).output_enable()  # 角色封装支持链式调用
        >>> mgr.close()
    """

    def __init__(
        self,
        device_table: str | DeviceTable | None = None,
        persistent_store: str | DeviceTable | None = None,
        backends: list[TransportBackend] | None = None,
    ) -> None:
        """初始化仪器管理器

        Args:
            device_table: 运行时设备信息表。可以是：

                - ``str``: JSON 文件路径，自动加载
                - ``DeviceTable``: 已有实例
                - ``None``: 创建空的内存表（不读写文件）

            persistent_store: 持久设备存储（USB/TCPIP 等地址稳定唯一的设备）。
                可以是 ``str`` / ``DeviceTable``；为 ``None`` 时使用默认路径
                ``~/.insty/known_devices.json``（环境变量 ``INSTY_DEVICE_STORE`` 可覆盖）

            backends: 传输后端列表，默认为 ``[VisaTransportBackend()]``
        """
        if isinstance(device_table, str):
            self._device_table = DeviceTable(device_table)
        elif isinstance(device_table, DeviceTable):
            self._device_table = device_table
        else:
            self._device_table = DeviceTable()

        if isinstance(persistent_store, str):
            self._persistent_store = DeviceTable(persistent_store)
        elif isinstance(persistent_store, DeviceTable):
            self._persistent_store = persistent_store
        else:
            self._persistent_store = DeviceTable(
                os.environ.get("INSTY_DEVICE_STORE", _DEFAULT_PERSISTENT_STORE)
            )

        if backends is None:
            backends = [
                VisaTransportBackend(
                    device_table=self._device_table,
                    persistent_store=self._persistent_store,
                )
            ]

        self._backends: list[TransportBackend] = list(backends)
        # 后端未显式指定存储时，共享管理器的两张表
        for backend in self._backends:
            if backend._device_table is None:
                backend._device_table = self._device_table
            if backend._persistent_store is None:
                backend._persistent_store = self._persistent_store
        self._connections: dict[str, InstrumentBase] = {}
        self._connection_backend: dict[str, TransportBackend] = {}

        # 在线仪器列表惰性发现：首次 get_* 时 discover，之后缓存；匹配失败自动刷新一次
        self._infos: list[InstrumentInfo] | None = None

    @property
    def persistent_store(self) -> DeviceTable:
        """持久设备存储（USB/TCPIP 等地址稳定唯一的设备）"""
        return self._persistent_store

    def save_device_table(self, path: str | None = None) -> None:
        """持久化设备信息表

        Args:
            path: 目标路径。为 ``None`` 时使用当前关联路径（如果也没有则静默跳过）
        """
        if path is not None:
            self._device_table.path = path
        self._device_table.save()

    @property
    def backends(self) -> list[TransportBackend]:
        """当前已注册的所有后端"""
        return list(self._backends)

    def register_backend(self, backend: TransportBackend) -> None:
        """注册一个新的传输后端

        Args:
            backend: 传输后端实例
        """
        self._backends.append(backend)
        logger.info(f"Registered backend: {backend.name}")

    def resolve(self, address: str) -> InstrumentInfo | None:
        """解析仪器地址，返回仪器信息

        按地址类型查对应存储（USB/TCPIP → 持久存储，串口 → 运行时表），
        未命中时回退到实时 ``*IDN?`` 查询；查询成功时自动写入对应存储
        （按 label 去重）。

        Args:
            address: 仪器 VISA 地址

        Returns:
            InstrumentInfo，无法识别时返回 ``None``
        """
        # 地址类型判定以后端为准（默认 VisaTransportBackend：非 ASRL 前缀 → 持久存储）
        if self._backends:
            store = (
                self._persistent_store
                if self._backends[0]._allow_auto_identify(address)
                else self._device_table
            )
            info = store.build_info(address)
            if info is not None:
                return info

        for backend in self._backends:
            try:
                info = backend._identify(address)
                if info is not None:
                    store = (
                        self._persistent_store
                        if backend._allow_auto_identify(address)
                        else self._device_table
                    )
                    store.set(
                        address,
                        info.label,
                        serial_baud=backend._serial_baud(address),
                        inst_type=info.inst_type.value,
                        supported=list(info.supported),
                        dedup_label=not backend._allow_auto_identify(address),
                    )
                    return info
            except Exception:
                continue

        return None

    def discover(self) -> list[InstrumentInfo]:
        """遍历所有后端，发现当前在线且身份已知的仪器（存在性检查）

        运行时默认路径，不做 `*IDN?`（除非后端允许自动识别，如 USB）。
        需要全量识别（尤其串口）时调用 :meth:`full_scan`。

        Returns:
            可用仪器列表，每个元素包含地址、标识、类别和支持能力。
            地址重复时，后面后端的发现结果覆盖前面的。
        """
        seen: dict[str, int] = {}
        rc: list[InstrumentInfo] = []

        for backend in self._backends:
            try:
                logger.info("Discovering instruments...")
                found = backend.discover()
                logger.info("Discovery complete.")
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

    def full_scan(self) -> list[InstrumentInfo]:
        """显式全量识别所有枚举到的设备并写回设备表

        与 ``discover()`` 不同，本方法会对每个地址执行 ``*IDN?``
        （串口还需逐档波特率试探），耗时较高。仅在设备连接变化
        （尤其串口换口、新增设备）后由用户显式调用，用于重建设备表。

        Returns:
            识别出的仪器列表，地址重复时后面后端的扫描结果覆盖前面的。
        """
        seen: dict[str, int] = {}
        rc: list[InstrumentInfo] = []

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

        self._infos = list(rc)
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

        last_ex: Exception | None = None
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

    # ── 角色化接口 ──────────────────────────────────────────────────

    def refresh(self) -> list[InstrumentInfo]:
        """重新发现当前在线的仪器并更新缓存, 存在性检查，不做 "*IDN?"

        设备连接变化（尤其串口换口）后请调用 :meth:`full_scan` 重建设备表。
        """
        self._infos = self.discover()
        return list(self._infos)

    def _ensure_infos(self) -> None:
        """确保在线仪器列表已发现（惰性）"""
        if self._infos is None:
            self._infos = self.discover()

    def _find_info(
        self, role: str, address: str | None, _retried: bool = False
    ) -> InstrumentInfo:
        inst_type, capability, _ = _ROLES[role]
        self._ensure_infos()

        if address:
            for info in self._infos:
                if info.address == address:
                    if not info.supports(inst_type, capability):
                        raise RuntimeError(
                            f'{info.label}[{address}] 不支持 "{capability}"'
                        )
                    return info
            # 地址不在当前在线列表：自动重新发现一次再匹配
            if not _retried:
                self.refresh()
                return self._find_info(role, address, _retried=True)
            raise RuntimeError(f'仪器地址不存在或未连接: "{address}"')

        candidates = [
            info for info in self._infos if info.supports(inst_type, capability)
        ]
        if not candidates:
            # 当前在线列表无匹配仪器：自动重新发现一次再匹配
            if not _retried:
                self.refresh()
                return self._find_info(role, address, _retried=True)
            raise RuntimeError(f'未找到可用 "{capability}" 的仪器（{role}）')
        if len(candidates) > 1:
            raise RuntimeError(
                f'找到多台 "{capability}" 仪器，请通过 address 参数指定: '
                + ", ".join(c.address for c in candidates)
            )
        return candidates[0]

    def _open_role(self, role: str, address: str | None, timeout: int = 30000):
        info = self._find_info(role, address)
        inst = self.open(info.address, info.label, timeout=timeout)
        _, _, role_class = _ROLES[role]
        return role_class(inst, info)

    # ── 角色获取 ────────────────────────────────────────────────────

    def get_power_supply(
        self, address: str | None = None, timeout: int = 30000
    ) -> PowerSupplyRole:
        """获取数字电源实例

        Args:
            address: 仪器地址；为 ``None`` 时自动匹配唯一在线实例，
                存在多台同类仪器时报错要求指定
            timeout: 连接超时（毫秒）
        """
        return self._open_role("power_supply", address, timeout)

    def get_thermal(
        self, address: str | None = None, timeout: int = 30000
    ) -> ThermalChamberRole:
        """获取高低温发生器实例，并完成开机检查与 DUT 模式配置

        Args:
            address: 仪器地址；为 ``None`` 时自动匹配唯一在线实例
            timeout: 连接超时（毫秒）
        """
        return self._open_role("thermal", address, timeout)

    def get_dmm(
        self, address: str | None = None, timeout: int = 30000
    ) -> DMMRole:
        """获取数字万用表实例

        Args:
            address: 仪器地址；为 ``None`` 时自动匹配唯一在线实例
            timeout: 连接超时（毫秒）
        """
        return self._open_role("dmm", address, timeout)

    def get_waveform_generator(
        self, address: str | None = None, timeout: int = 30000
    ) -> WaveformGeneratorRole:
        """获取波形发生器实例

        Args:
            address: 仪器地址；为 ``None`` 时自动匹配唯一在线实例
            timeout: 连接超时（毫秒）
        """
        return self._open_role("waveform_generator", address, timeout)

    def get_oscilloscope(
        self, address: str | None = None, timeout: int = 30000
    ) -> OscilloscopeRole:
        """获取示波器实例

        Args:
            address: 仪器地址；为 ``None`` 时自动匹配唯一在线实例
            timeout: 连接超时（毫秒）
        """
        return self._open_role("oscilloscope", address, timeout)

    def get_frequency_counter(
        self, address: str | None = None, timeout: int = 30000
    ) -> FrequencyCounterRole:
        """获取频率计实例

        Args:
            address: 仪器地址；为 ``None`` 时自动匹配唯一在线实例
            timeout: 连接超时（毫秒）
        """
        return self._open_role("frequency_counter", address, timeout)

    # ── 工具方法 ────────────────────────────────────────────────────

    @staticmethod
    def hold(seconds: float) -> None:
        """保持当前状态等待指定时间"""
        time.sleep(seconds)

    def run_cmd(self, args, check: bool = True, timeout: float | None = None) -> bool:
        """执行外部命令（如 DUT 串口命令）"""
        cmd = [str(a) for a in args]
        logger.info(f'Run: {" ".join(cmd)}')
        try:
            subprocess.run(cmd, shell=False, check=True, timeout=timeout)
            return True
        except subprocess.CalledProcessError as ex:
            logger.error(f"命令执行失败: {ex}")
            if check:
                raise RuntimeError(f"命令执行失败: {ex}") from ex
            return False

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc) -> None:
        self.shutdown()
