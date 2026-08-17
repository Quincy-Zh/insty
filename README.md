# Insty

[![PyPI version](https://badge.fury.io/py/insty.svg)](https://badge.fury.io/py/insty)
[![Python Versions](https://img.shields.io/pypi/pyversions/insty.svg)](https://pypi.org/project/insty/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Downloads](https://static.pepy.tech/badge/insty)](https://pepy.tech/project/insty)

> Stop writing vendor-specific drivers. Just talk to your instruments.

**Insty** 是一个基于 VISA 协议的 Python 库，为测试自动化提供**统一的仪器访问接口**。通过将仪器抽象为类型基类（数字电源、万用表、示波器等），你只需几行 Python 代码就能控制不同厂商的仪器，无需记忆各厂商差异化的驱动 API。

## 特性

- 🎯 **按类别访问**：按仪器类型获取控制对象，语义清晰（`get_power_supply()`、`get_dmm()` 等）
- 🔌 **厂商无关**：屏蔽 Keysight、R&S、Keithley、Tektronix 等不同品牌的驱动差异
- 🚀 **惰性发现**：仪器按需连接，启动快速；USB/TCPIP 设备信息自动持久化，即插即用；支持全量扫描和手动刷新设备表
- 🔧 **可扩展**：支持自定义传输后端（默认使用 VISA）和注册新仪器驱动
- 🐍 **Pythonic**：API 设计符合 Python 习惯，简洁直观

## 安装

```bash
pip install insty
```

### 首次使用前的环境准备

`insty` 依赖 `pyvisa` 和一个可用的 VISA 后端。推荐按以下顺序选择：

1. **NI-VISA**（最稳定，推荐）：从 [NI 官网](https://www.ni.com/visa) 下载安装
2. **R&S VISA**：罗德与施瓦茨提供的 VISA 实现
3. **pyvisa-py**（纯 Python 实现，无需安装驱动）：
   ```bash
   pip install pyvisa-py
   ```

验证后端是否正常工作：

```python
import pyvisa
rm = pyvisa.ResourceManager()
print(rm.list_resources())  # 应列出所有可用的仪器地址
```

## 快速开始

### 按类别访问（推荐）

测试脚本通过 `InstrumentManager` 按仪器类别获取实例：

```python
from insty import InstrumentManager

mngr = InstrumentManager(device_table=".device_table.json")

# 获取数字电源并设置电压
ps = mngr.get_power_supply(address="USB0::0x0957::0x2C07::MY12345678::0::INSTR")
ps.set_voltage(3.3).output_enable()  # 支持链式调用

# 获取高低温箱并设定温度
thermal = mngr.get_thermal()
thermal.set_temperature(-40)
thermal.wait(timeout=300)  # 等待温度稳定
print("温度已稳定在 -40°C")

# 获取数字万用表读取电压
vm = mngr.get_dmm(address="USB0::0x0957::0x0B18::MY12345678::0::INSTR")
print(f"当前电压读数: {vm.read_voltage():.4f} V")  # 当前电压读数: 3.2962 V

# 获取示波器并触发单次采集
osc = mngr.get_oscilloscope()
osc.execute("single")
freq = osc.read_frequency()
print(f"信号频率: {freq:.2f} Hz")  # 信号频率: 1000.00 Hz

mngr.close_all()
```

**可用类别接口：**

- `get_power_supply()` — 数字电源
- `get_thermal()` — 高低温发生器
- `get_dmm()` — 数字万用表
- `get_waveform_generator()` — 信号发生器
- `get_oscilloscope()` — 示波器
- `get_frequency_counter()` — 频率计数器

不传 `address` 参数时，自动匹配唯一在线仪器；多台同类型仪器时会报错并提示使用 `address=` 指定。

仪器在首次调用 `get_*` 方法时惰性发现。设备连接变化后可随时调用 `mngr.full_scan()` 进行全量识别，重建设备表。

### 设备发现机制

仪器信息按地址类型分两张表存储：

| 地址类型 | 存储位置 | 说明 |
| :--- | :--- | :--- |
| USB / TCPIP | 持久存储 | 地址内嵌序列号、稳定唯一，IDN 固定不变，自动识别并持久化，跨项目即插即用 |
| 串口（ASRL） | 运行时设备表（`device_table`） | 地址随 USB 插口漂移，不自动识别，需显式 `scan()`；波特率逐档试探并缓存 |

- 持久存储默认位于 `~/.insty/known_devices.json`，可用环境变量 `INSTY_DEVICE_STORE` 覆盖；不依赖程序传入的 device_table
- `discover()` 仅做存在性检查（不做 `*IDN?`），USB/TCPIP 表外设备例外（自动识别并写入持久存储）
- 全量识别用 `scan()`：对每个地址执行 `*IDN?`（串口逐档波特率试探），结果按地址类型写入对应存储
- 命令行重建设备表：`python -m insty.scan [device_table.json]`（缺省仅更新持久存储）

### 细粒度控制（InstrumentManager）

除按类别的 `get_*` 接口外，`InstrumentManager` 还提供地址级别的细粒度控制：

```python
from insty import InstrumentManager

mgr = InstrumentManager(device_table=".device_table.json")  # 运行时设备表（串口设备）

# 发现在线仪器（仅做存在性检查，不做 *IDN?）
infos = mgr.discover()
for info in infos:
    print(info.address, info.label, info.inst_type, info.supported)

# 解析指定地址（表命中即用，否则实时 *IDN? 并写回对应存储）
info = mgr.resolve("USB0::0x0957::0x2C07::MY12345678::0::INSTR")

# 打开特定仪器
inst = mgr.open(info.address, info.label)
inst.write("SYSTem:REMote")
data = inst.query("MEASure:VOLTage?")
print(f"读取数据: {data}")

inst.close()
mgr.close_all()
```

**关键方法：**
- `discover()` — 快速检查哪些地址在线（USB/TCPIP 表外设备自动识别并持久化）
- `resolve(address)` — 解析指定地址，未命中时实时 `*IDN?` 识别并写入对应存储
- `full_scan()` — 对每个地址执行 `*IDN?`，串口设备还会逐档波特率试探，全量识别仪器类型
- `register_backend()` — 注册更多传输后端（默认内置 `VisaTransportBackend`）

## 支持的仪器

`Insty` 通过统一的抽象接口支持多厂商仪器，目前已覆盖以下类型：

| 仪器类型 | 抽象基类 | 已适配仪器 |
| :--- | :--- | :--- |
| 数字电源 | `PowerSupply` | ITECH::IT6302 |
| 数字万用表 | `DMM` | KEITHLEY::DMM6500 |
| 示波器 | `Oscilloscope` | ZHIYUAN::ZDS1000 |
| 高低温发生器 | `ThermalChamber` | TEMPTRONIC::ATS710 |
| 频率计数器 | `FrequencyCounter` | AGILENT::53220A |
| 信号发生器 | `WaveformGenerator` | AGILENT::33519, AGILENT::33519, AGILENT::33512B |

> 只要仪器支持标准 SCPI 指令集，`Insty` 就能通过 `InstrumentRegistry` 快速适配。欢迎提交 PR 新增厂商驱动！

## 导出 API 一览

`Insty` 提供清晰的模块化导出：

**面向用户的高层接口：**
- `InstrumentManager` — 仪器管理器（发现、连接、生命周期管理、按类别的访问接口 `get_power_supply()` / `get_dmm()` 等）

**核心管理器：**
- `InstrumentRegistry` — 驱动注册表，通过以下方法显式注册：
  - `register_power_supply()`
  - `register_thermal_chamber()`
  - `register_waveform_generator()`
  - `register_dmm()`
  - `register_oscilloscope()`
  - `register_frequency_counter()`

**数据类型与枚举：**
- `InstrumentType` — 仪器类型枚举
- `InstrumentInfo` — 已发现仪器信息（`address` / `label` / `inst_type` / `supported`）

**抽象基类（自定义驱动时继承）：**
- `PowerSupply`
- `ThermalChamber`
- `WaveformGenerator`
- `DMM`
- `Oscilloscope`
- `FrequencyCounter`

**传输层：**
- `TransportBackend` — 传输后端抽象基类
- `VisaTransportBackend` — VISA 默认实现

**工具函数：**
- `make_instrument(name, resource)` — 驱动工厂方法

## 贡献

欢迎提交 Issue、Feature Request 或 Pull Request！

- **新增仪器驱动**：继承对应的抽象基类并注册到 `InstrumentRegistry`
- **新增传输后端**：实现 `TransportBackend` 接口
- **报告问题**：请在 Issue 中附上完整的错误堆栈和仪器型号

详细指南请参考 [CONTRIBUTING.md](./CONTRIBUTING.md)。

## 感谢

最后感谢 deepseek 和 OpenCode，除了协助我写代码，还指导我把这份代码上传到 PyPi。

## License

Apache License 2.0，详见 [LICENSE](./LICENSE)。