"""波形发生器示例（Agilent 33500/33600 系列）

配置波形并启用输出。
"""

from insty import InstrumentManager

# 连接仪器
mgr = InstrumentManager()
wg = mgr.get_waveform_generator()

# 配置通道1：1 kHz 正弦波，3.3 Vpp，1.65 V 偏置
# 立即输出
wg.setup("SIN", channel=1, freq=1e3, vpp=3.3, offset=1.65).output_enable(1)
print(wg.get_errors())

# 配置通道2：10 kHz 方波，50% 占空比
# 立即输出
if wg.channels > 1:
    wg.setup("SQU", channel=2, freq=10e3, vpp=5.0, offset=0.0, duty_cycle=50.0).output_enable(2)

# 增量修改：把通道1频率改为 2 kHz（不影响其他参数）
wg.set_frequency(2e3, channel=1)

# 关闭全部输出并释放连接
wg.output_disable()
mgr.shutdown()
