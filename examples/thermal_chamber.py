"""高低温箱示例（Temptronic ATS-710）

设置目标温度，等待温控稳定，读取当前温度。
"""

from insty import InstrumentManager

mgr = InstrumentManager()
thermal = mgr.get_thermal()

# 初始化温控箱
thermal.setup()

# 设置目标温度 -40°C，等待稳定（最长 300 秒）
thermal.set_temperature(-40, soak=15)
reached = thermal.wait(timeout=300)

if reached:
    temp = thermal.get_temperature()
    print(f"温度已稳定: {temp:.1f} °C")
else:
    print("等待超时，温度未稳定")

# 升温到 85°C
thermal.set_temperature(85, soak=30)
thermal.wait(timeout=300)
temp = thermal.get_temperature()
print(f"温度已稳定: {temp:.1f} °C")

# 抬起热头
thermal.execute("head up")

mgr.shutdown()
