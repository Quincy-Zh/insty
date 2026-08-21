"""示波器示例（致远 ZDS1000 系列）

单次触发采集，读取频率和占空比。
"""

from insty import InstrumentManager

mgr = InstrumentManager()
osc = mgr.get_oscilloscope()

# 配置并单次触发
osc.setup(signal=1)
osc.execute("single")

# 读取测量结果
freq = osc.read_frequency(channel=1)
duty = osc.read_duty_cycle(channel=1)
print(f"频率: {freq:.2f} Hz")
print(f"占空比: {duty:.2%}")

# 截图保存到文件
img = osc.screenshot()
if img:
    with open("screenshot.bmp", "wb") as f:
        f.write(img)
    print("截图已保存: screenshot.bmp")

mgr.shutdown()
