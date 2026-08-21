"""数字电源 + 数字万用表联合验证示例

随机生成输出电压设定值，由 ITECH IT6302 数字电源输出，
Keithley DMM6500 读取并对比设定值与实测值。

注意：运行前请把电源输出通道（CH1）接到 DMM6500 的 INPUT HI/LO 端子。
"""

import os
import random
import time

from insty import InstrumentManager

device_tbl = os.path.join(
    os.path.expanduser("~"), ".insty", "visa_devices.json"
)

mgr = InstrumentManager(device_tbl)
# mgr.full_scan()
ps = mgr.get_power_supply()
dmm = mgr.get_dmm()

print("请确认 DMM6500 已设置为电压测量模式...")
dmm.read_voltage()

header = f"{'设定电压':>10} {'实测电压':>10} " f"{'电压偏差':>10} {'相对偏差':>10}"
print(header)
print("-" * 52)

for _ in range(10):

    volt = random.randint(1, 30)
    ps.set_voltage(volt, 1)
    err = ps.get_errors()
    if err:
        print(err)
        break

    time.sleep(2)

    meas = dmm.read_voltage()
    if meas is None:
        print("电压读取失败")
        break

    deviation = f"{meas - volt:+.3f}"
    percent = f"{meas / volt * 100 - 100:+.2f}%"

    print(f"{volt:>10} {meas:>10.6f} {deviation:>10} " f"{percent:>10}")

ps.output_disable(0)
mgr.shutdown()

os.remove(device_tbl)
