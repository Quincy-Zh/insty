"""频率计数器示例（Agilent 53220A）

测量输入信号的频率和占空比。
"""

from insty import InstrumentManager

mgr = InstrumentManager()
fc = mgr.get_frequency_counter()

try:
    fc.setup(channel=1, impedance=50, threshold='50%', range=50)
    freq = fc.read_frequency(channel=1)
    duty = fc.read_duty_cycle(channel=1)

    if freq:
        print(f"频率: {freq:.6f} Hz")
    else:
        print('Fail to fetch "freq"')
        print(fc.get_errors())

    if duty:
        print(f"占空比: {duty:.4%}")
    else:
        print('Fail to fetch "duty_cycle"')
        print(fc.get_errors())

except Exception as ex:
    print(ex, fc.get_errors())



mgr.shutdown()
