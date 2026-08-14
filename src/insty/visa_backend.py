"""VISA 传输后端实现

:meth:discover 由基类模板方法统一调度：
先查 `DeviceTable`（无 I/O），未命中时通过 `_identify` 回退扫描。
"""

from __future__ import annotations

import logging
import time

from .device_table import DeviceTable
from .instrument_types import InstrumentBase, InstrumentInfo
from .transport_backend import TransportBackend

logger = logging.getLogger(__name__)

_SERIAL_BAUD_RATES = (
    115200,
    9600,
    38400,
    19200,
    57600,
)


class VisaTransportBackend(TransportBackend):
    """VISA 传输后端"""

    @staticmethod
    def format_idn(idn: str) -> str:
        """格式化 *IDN? 响应字符串为 VENDOR::MODEL 格式"""
        cleaned = "".join(c for c in idn if c.isprintable())
        sp = cleaned.split(",")
        vendor = sp[0].strip() if len(sp) > 0 else "Unknown"
        model = sp[1].strip() if len(sp) > 1 else "Unknown"
        model = model.replace("MODEL", "").strip()
        vendor_items = vendor.split(" ")
        if len(vendor_items) > 1:
            vendor = vendor_items[0]
        return f"{vendor}::{model}"

    def __init__(
        self,
        device_table: DeviceTable | None = None,
        persistent_store: DeviceTable | None = None,
    ) -> None:
        super().__init__(device_table, persistent_store)
        self._rm: object | None = None
        self._discovered_bauds: dict[str, int] = {}

    def _resource_manager(self):
        """惰性创建 VISA ResourceManager：无默认后端时回退 pyvisa-py

        构造后端不触发任何 VISA 初始化，避免无后端环境（如 CI 无
        NI-VISA / pyvisa-py）下创建管理器即失败；真正执行 I/O 时才创建。
        """
        if self._rm is None:
            import pyvisa
            try:
                self._rm = pyvisa.ResourceManager()
            except Exception:
                self._rm = pyvisa.ResourceManager('@py')
        return self._rm

    def _enum(self) -> list[str]:
        return list(self._resource_manager().list_resources("?*"))

    def _identify(self, addrress: str) -> InstrumentInfo | None:
        if addrress.startswith("ASRL"):
            return self._identify_serial(addrress)
        return self._identify_non_serial(addrress)

    def _serial_baud(self, addrress: str) -> int | None:
        return self._discovered_bauds.get(addrress)

    def _allow_auto_identify(self, addrress: str) -> bool:
        # USB 等地址内嵌硬件序列号、唯一稳定，存在性检查时可自动 *IDN?* 实现即插即用，
        # 其设备信息持久化存储（不依赖运行时 device_table）；
        # 串口（ASRL）地址随 USB 插座漂移，不自动识别，设备信息存运行时表，
        # 由显式 scan() 确认
        return not addrress.startswith("ASRL")

    # ── 非串口设备 ─────────────────────────────────────

    def _identify_non_serial(self, addrress: str) -> InstrumentInfo | None:
        import pyvisa
        import pyvisa.constants

        try:
            inst = self._resource_manager().open_resource(addrress)
            inst.timeout = 2000
            idn = inst.query("*IDN?").strip()
            inst.close()

            if idn:
                label = self.format_idn(idn)
                return self._build_info(addrress, label)
        except pyvisa.VisaIOError as e:
            if e.error_code != pyvisa.constants.VI_ERROR_TMO:
                logger.warning(f"[VisaTransportBackend] VISA IO Error for {addrress}: {e}")
        except Exception as e:
            logger.warning(
                f"[VisaTransportBackend] Failed to query instrument at {addrress}: {e}"
            )
        return None

    # ── 串口设备 ───────────────────────────────────────

    def _identify_serial(self, addrress: str) -> InstrumentInfo | None:
        # 优先用设备表缓存的波特率（已知设备只试 1 次）
        if self._device_table is not None:
            entry = self._device_table.get(addrress)
            if entry is not None:
                cached_baud = entry.get("serial_baud")
                if cached_baud:
                    info = self._try_baud(addrress, cached_baud)
                    if info is not None:
                        self._discovered_bauds[addrress] = cached_baud
                        return info
        for baud in _SERIAL_BAUD_RATES:
            info = self._try_baud(addrress, baud)
            if info is not None:
                self._discovered_bauds[addrress] = baud
                return info
        return None

    def _try_baud(self, addrress: str, baud: int) -> InstrumentInfo | None:
        import pyvisa
        import pyvisa.constants

        try:
            inst = self._resource_manager().open_resource(addrress)
            inst.baud_rate = baud
            inst.timeout = 2000

            inst.write("")
            time.sleep(0.05)
            try:
                inst.read()
            except Exception:
                pass
            try:
                inst.flush(pyvisa.constants.VI_READ_BUF)
            except Exception:
                pass

            idn = inst.query("*IDN?").strip()
            inst.close()

            if idn:
                label = self.format_idn(idn)
                return self._build_info(addrress, label)
        except Exception:
            try:
                inst.close()
            except Exception:
                pass
        return None

    # ── 构建 InstrumentInfo ─────────────────────────────

    def _build_info(self, addrress: str, label: str) -> InstrumentInfo | None:
        try:
            from .instrument_types import InstrumentRegistry
            inst_type, supported = InstrumentRegistry.get_info(label)
            return InstrumentInfo(
                address=addrress,
                label=label,
                inst_type=inst_type,
                supported=supported,
            )
        except ValueError:
            logger.warning(f"[VisaTransportBackend] Unknown instrument: {label}")
            return None

    # ── 连接管理 ────────────────────────────────────────

    def open(self, address: str, label: str, timeout: int = 30000) -> InstrumentBase:
        from .instrument_types import make_instrument

        resource = self._resource_manager().open_resource(address)
        resource.timeout = timeout

        if address.startswith("ASRL") and self._device_table is not None:
            entry = self._device_table.get(address)
            if entry is not None:
                baud = entry.get("serial_baud")
                if baud:
                    resource.baud_rate = baud

        return make_instrument(label, resource)

    def shutdown(self) -> None:
        if self._rm is None:
            return
        try:
            self._rm.close()
        except Exception as ex:
            logger.warning(
                f"[VisaTransportBackend] Error closing ResourceManager: {ex}"
            )
