"""数字电源示例（ITECH IT6302）

设置输出电压，启用/关闭输出。
"""

from insty import InstrumentManager

mgr = InstrumentManager()
ps = mgr.get_power_supply()

# 设置电压（自动启用输出）
ps.set_voltage(3.3)

# 关闭输出
ps.output_disable()

# 重新启用
ps.output_enable()

# 关闭连接
mgr.shutdown()
