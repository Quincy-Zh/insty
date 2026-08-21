"""完整工作流示例：电源 + 波形发生器 + 万用表联合测试

演示 InstrumentManager 按类别访问多台仪器的典型流程。
"""

from insty import InstrumentManager

mgr = InstrumentManager()

# 按类别获取各仪器（自动发现、惰性连接）
ps = mgr.get_power_supply()
wg = mgr.get_waveform_generator()
dmm = mgr.get_dmm()

# 1. 电源上电
ps.set_voltage(3.3)
print("电源已开启: 3.3 V")

# 2. 配置波形发生器输出 1 kHz 正弦波
wg.setup("SIN", freq=1e3, vpp=3.3, offset=1.65)
wg.output_enable()
print("波形已输出: 1 kHz / 3.3 Vpp")

# 3. 万用表读取验证
voltage = dmm.read_voltage()
print(f"实测电压: {voltage:.4f} V")

# 4. 清理（shutdown 逐通道关闭输出 + 释放 VISA + 关闭后端）
wg.output_disable()
ps.output_disable()
mgr.shutdown()
