"""数字万用表示例（Keithley DMM6500）

读取直流电压和电流，支持自定义量程与滤波参数。
"""

from insty import InstrumentManager

mgr = InstrumentManager()
dmm = mgr.get_dmm(address="USB0::0x0957::0x0B18::MY12345678::0::INSTR")

# 读取直流电压（默认自动量程）
voltage = dmm.read_voltage()
print(f"电压: {voltage:.4f} V")

# 自定义参数：指定量程、积分时间、滤波
voltage = dmm.read_voltage(params={
    "range": 10,             # 10 V 量程
    "power_line_cycles": 10, # 10 PLC 积分
    "filter": True,          # 启用滤波
    "buffer_size": 5,        # 5 次读取取平均
})
print(f"电压（定制参数）: {voltage:.6f} V")

# 读取直流电流
current = dmm.read_current()
print(f"电流: {current:.6f} A")

mgr.shutdown()
