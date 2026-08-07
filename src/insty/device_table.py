"""设备信息表

存储已知设备的标识、能力和连接参数，用于快速发现。
所有设备（串口 / 非串口）统一存储。
由扫描模块（``scan.py``）生成，也可手动维护。
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

from .instrument_types import InstrumentInfo

logger = logging.getLogger(__name__)


class DeviceTable:
    """设备信息表

    以 JSON 文件持久化，存储每个地址的已知信息：

    - ``label``: 仪器标识（如 "KEITHLEY::DMM6500"）
    - ``serial_baud``: 串口波特率（非串口设备为 null）
    - ``inst_type``: 仪器类型名（如 "dmm" / "oscilloscope"）
    - ``supported``: 支持的能力列表

    不传 ``path`` 时工作在纯内存模式，不读写文件。

    Example:
        >>> table = DeviceTable("project/.device_table.json")
        >>> entry = table.get("ASRL18::INSTR")
        >>> if entry:
        ...     print(entry["label"])
    """

    def __init__(self, path: Optional[str] = None) -> None:
        """初始化设备表

        Args:
            path: JSON 文件路径，为 ``None`` 时不加载/保存文件
        """
        self._path = path
        self._data: Dict[str, dict] = {}
        if path is not None:
            self._load()

    def _load(self) -> None:
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
            logger.debug(
                f"Loaded device table from {self._path} ({len(self._data)} entries)"
            )
        except (FileNotFoundError, json.JSONDecodeError):
            self._data = {}

    def save(self) -> None:
        if self._path is None:
            return
        try:
            os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except OSError as ex:
            logger.warning(f"Failed to save device table: {ex}")

    @property
    def path(self) -> Optional[str]:
        """当前关联的文件路径，``None`` 表示纯内存模式"""
        return self._path

    @path.setter
    def path(self, value: Optional[str]) -> None:
        self._path = value

    def get(self, address: str) -> Optional[dict]:
        """获取指定地址的缓存信息

        Args:
            address: 仪器地址

        Returns:
            缓存字典，含 ``label``、``serial_baud``、``inst_type``、``supported``
        """
        return self._data.get(address)

    def set(
        self,
        address: str,
        label: str,
        serial_baud: Optional[int] = None,
        inst_type: Optional[str] = None,
        supported: Optional[List[str]] = None,
    ) -> None:
        """更新指定地址的信息

        自动清除同 label 但不同地址的旧条目（应对 USB 换口等场景）。

        Args:
            address: 仪器地址
            label: 仪器标识（如 "KEITHLEY::DMM6500"）
            serial_baud: 串口波特率，非串口设备传 None
            inst_type: 仪器类型名（如 "dmm"）
            supported: 支持的能力列表
        """
        for existing_addr in list(self._data.keys()):
            if existing_addr != address and self._data[existing_addr].get("label") == label:
                del self._data[existing_addr]
                logger.info(f"Removed stale entry {existing_addr} -> {label}")
        entry: Dict[str, Any] = {
            "label": label,
            "serial_baud": serial_baud,
        }
        if inst_type is not None:
            entry["inst_type"] = inst_type
        if supported is not None:
            entry["supported"] = supported
        self._data[address] = entry
        self.save()

    def remove(self, address: str) -> None:
        """移除指定地址的缓存"""
        self._data.pop(address, None)
        self.save()

    def addresses(self) -> set:
        """返回所有缓存的地址集合"""
        return set(self._data.keys())

    def build_info(self, address: str) -> Optional[InstrumentInfo]:
        """从缓存数据构造 InstrumentInfo

        优先从注册表按 label 解析类型与能力（始终与驱动一致），
        未知 label 时回退到表中存储的 ``inst_type`` / ``supported``。

        Args:
            address: 仪器地址

        Returns:
            InstrumentInfo，构造失败时返回 None
        """
        entry = self._data.get(address)
        if entry is None:
            return None

        label = entry.get("label", "Unknown")

        # 优先：从注册表按 label 解析
        try:
            from .instrument_types import InstrumentRegistry
            inst_type, supported = InstrumentRegistry.get_info(label)
            return InstrumentInfo(
                address=address,
                label=label,
                inst_type=inst_type,
                supported=supported,
            )
        except ValueError:
            pass

        # 回退：使用表中存储的 inst_type / supported
        inst_type_str = entry.get("inst_type")
        supported_list = entry.get("supported")
        if inst_type_str is not None and supported_list is not None:
            from .instrument_types import InstrumentType
            return InstrumentInfo(
                address=address,
                label=label,
                inst_type=InstrumentType(inst_type_str),
                supported=tuple(supported_list),
            )

        return None
