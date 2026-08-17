# AGENTS.md

基于 VISA 的统一仪器控制库（src 布局，Python >=3.8）。所有注释、docstring、提交消息用中文；
提交消息沿用仓库历史风格（简短中文短语），不要按 CONTRIBUTING.md 的英文 Conventional Commits 格式。

## 命令
- 测试：`pytest tests/`（唯一文件 tests/test_instrument.py，纯 mock 模拟硬件，无需真机）
- 单测：`pytest tests/test_instrument.py -k <name>`
- 静态检测：`ruff check src tests`（pyproject 已配置 [tool.ruff]，target-version py38；BLE001/S110/S112 有意忽略）
- 无 typecheck 配置；pyproject 未定义 [project.optional-dependencies]（CONTRIBUTING 中的 `pip install -e .[dev]` 不可用）
- 设备表重建：`python -m insty.scan <device_table.json>`（对每个地址执行 *IDN?，串口逐档波特率试探；缺省参数时仅更新持久存储）

## 架构：设备发现（双存储，按地址类型分派）
- 驱动在 import 时注册：insty/__init__.py → visa_based_instrument.py → drivers/__init__.py 级联导入各驱动，驱动末尾调用 InstrumentRegistry.register_*。新驱动必须加入 drivers/__init__.py 导入链，否则注册不生效。
- label 格式 VENDOR::MODEL，由 VisaTransportBackend.format_idn() 解析 *IDN? 响应生成；注册表按 label 匹配（大小写不敏感）。
- 设备信息分两张表，由 _allow_auto_identify(address)（非 ASRL 前缀 → True）兼作存储分派（TransportBackend._storage_for）：
  - 持久存储（USB/TCPIP）：地址稳定唯一，discover 允许自动识别并写入；路径为环境变量 INSTY_DEVICE_STORE，缺省 ~/.insty/known_devices.json；不依赖程序传入的 device_table
  - 运行时表（device_table，串口 ASRL）：地址随 USB 插口漂移，不自动识别，须显式 scan；波特率按 _SERIAL_BAUD_RATES 逐档试探（有缓存波特率只试 1 次）
- 发现分三层：
  1. discover()（TransportBackend 模板方法，无 *IDN? 存在性检查）：按地址类型查对应存储，未命中且允许自动识别才实时识别并写表。
  2. resolve()（InstrumentManager）：按地址类型查对应存储，未命中逐后端 _identify() 回退，识别结果写对应存储。
  3. full_scan()/scan()（用户显式触发）：对每个地址强制 *IDN?，结果按地址类型写对应存储。
- InstrumentManager 构造：device_table 参数为 str 路径（默认 None=空内存表）；后端列表不可注入，内置 VisaTransportBackend，其余用 register_backend() 追加（注册时注入共享的两张表）；持久存储无参数，一律走 INSTY_DEVICE_STORE 或默认路径。DeviceTable 为内部实现类，不对外导出。
- DeviceTable.set() 的 label 去重（dedup_label=True）仅用于串口等地址漂移场景（运行时表）；USB/TCPIP 等稳定唯一地址由调用点显式传 dedup_label=False，同型号多台设备互不删除。

## 已知限制
- 不做旧表兼容回退：运行时表里残留的 USB 条目不会被查询（用户明确选择）。
- 存储分派依赖后端的 _allow_auto_identify 判定，自定义后端默认 False（全部走运行时表）。

## 坑
- visa_backend.py 的 _identify/_serial_baud 参数名拼写为 addrress（三个 r）
- 测试无 conftest.py（CONTRIBUTING.md 描述的 MockTransportBackend 不存在）
- .gitignore 末尾忽略 *.json —— 新增 JSON 持久化文件需 git add -f 或改 .gitignore
- 代码用 X | Y / dict[str, ...] 注解，靠 from __future__ import annotations 保持 py3.8 兼容，新代码注意
