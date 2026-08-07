"""扫描 VISA 设备并生成设备信息表（显式全量识别）

运行时的 ``discover()`` 只做存在性检查（无 *IDN?*）；本模块对每个
VISA 地址执行 ``*IDN?``（串口逐档波特率试探），用于设备连接变化
（尤其串口换口）后重建 ``.device_table.json``。

Usage:
    python -m insty.scan <device_table_path>
"""

import argparse

from . import visa_based_instrument  # 触发驱动注册
from .manager import InstrumentManager


def scan(path: str) -> int:
    """扫描 VISA 设备（全量 *IDN?*），更新设备信息表

    Args:
        path: 设备信息表 JSON 文件路径

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
    return len(infos)


def main() -> None:
    parser = argparse.ArgumentParser(description="扫描并生成设备信息表")
    parser.add_argument(
        "device_table",
        help="设备信息表路径",
    )
    args = parser.parse_args()

    print("Scanning VISA resources...")
    found = scan(args.device_table)
    print(f"\nFound {found} instrument(s), saved to {args.device_table}")


if __name__ == "__main__":
    main()
