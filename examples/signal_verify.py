"""信号发生器 + 频率计联合验证示例

随机生成频率值和占空比值，由信号发生器发出，频率计读取并对比结果。

注意：运行前请用 BNC 线缆将信号发生器输出端与频率计输入端连接。
"""
import random
import time

from insty import InstrumentManager

mgr = InstrumentManager()
wg = mgr.get_waveform_generator()
fc = mgr.get_frequency_counter()

fc.setup()

header = (
    f"{'设定频率':>10} {'设定占空比':>10} "
    f"{'实测频率':>12} {'频率偏差':>10} "
    f"{'实测占空比':>10} {'占空比偏差':>10}"
)
print(header)
print("-" * 66)

for _ in range(15):
    
    freq = random.randint(1_000, 10_000_000)
    duty = random.randint(15, 90)
    wg.setup("SQU", channel=1, freq=freq, vpp=5.0, offset=1.0, duty_cycle=duty).output_enable(1)
    err = wg.get_errors()
    if err:
        print(err)
        break

    time.sleep(2)

    meas_freq = fc.read_frequency(channel=1)

    if not meas_freq:
        print(wg.get_errors())
        break

    meas_duty = fc.read_duty_cycle(channel=1)
    if not meas_duty:
        print(fc.get_errors)
        break

    freq_str = f"{meas_freq:.3f}" if meas_freq else "读取失败"
    duty_str = f"{meas_duty * 100:.2f}%" if meas_duty else "读取失败"

    if meas_freq:
        freq_err = f"{meas_freq - freq:+.3f}"
    else:
        freq_err = "-"

    if meas_duty:
        duty_err = f"{meas_duty * 100 - duty:+.2f}%"
    else:
        duty_err = "-"

    print(
        f"{freq:>10.0f} {duty:>9}% "
        f"{freq_str:>12} {freq_err:>10} "
        f"{duty_str:>10} {duty_err:>10}"
    )

wg.output_disable(1)
mgr.shutdown()
