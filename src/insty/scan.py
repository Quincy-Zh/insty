"""扫描 VISA 设备并生成设备信息表（显式全量识别）

运行时的 ``discover()`` 只做存在性检查（无 *IDN?*）；本模块对每个
VISA 地址执行 ``*IDN?``（串口逐档波特率试探），用于设备连接变化
（尤其串口换口）后重建设备信息表。

识别结果按地址类型分流写入：USB/TCPIP → 持久存储
（默认 ``~/.insty/known_devices.json``，可用环境变量 ``INSTY_DEVICE_STORE``
覆盖）；串口（ASRL）→ 传入的运行时设备表。

Usage:
    python -m insty.scan [device_table_path]
"""

from __future__ import annotations

import argparse
import os

from .manager import InstrumentManager

_DEFAULT_PERSISTENT_STORE = os.path.join(
    os.path.expanduser("~"), ".insty", "known_devices.json"
)


def scan(path: str | None = None) -> int:
    """扫描 VISA 设备（全量 *IDN?*），更新设备信息表

    Args:
        path: 运行时设备表 JSON 文件路径（串口设备归属）。
            为 ``None`` 时仅更新持久存储（USB/TCPIP 设备归属）

    Returns:
        本次扫描识别的仪器数量
    """
    mgr = InstrumentManager(device_table=path)
    try:
        infos = mgr.full_scan()
    finally:
        mgr.shutdown()
    mgr.save_device_table(path)

    for info in infos:
        print(f">>> {info.address} -> {info.label}")

    if path is not None:
        print(f"Runtime device table updated: {path}")
    store_path = os.environ.get("INSTY_DEVICE_STORE", _DEFAULT_PERSISTENT_STORE)
    print(f"Persistent store updated: {store_path}")
    return len(infos)


def main() -> None:
    parser = argparse.ArgumentParser(description="扫描并生成设备信息表")
    parser.add_argument(
        "device_table",
        nargs="?",
        default=None,
        help="运行时设备表路径（串口设备），缺省时仅更新持久存储"
        "（~/.insty/known_devices.json，环境变量 INSTY_DEVICE_STORE 可覆盖）",
    )
    args = parser.parse_args()

    print("Scanning VISA resources...")
    found = scan(args.device_table)
    print(f"\nFound {found} instrument(s)")


if __name__ == "__main__":
    main()
