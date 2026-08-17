# Contributing to Insty

首先，感谢你愿意为 `Insty` 贡献代码、文档或建议！我们非常欢迎来自社区的任何形式的贡献。

这份指南旨在帮助你了解如何参与项目，并确保你的贡献能顺利被合并。

## 行为准则

本项目遵循 [Python 社区行为准则](https://www.python.org/psf/codeofconduct/)。请确保你的言行友善、尊重、包容。

## 如何贡献

### 1. 报告 Bug 或提出新功能

- 在提交 Issue 前，请先搜索[现有 Issues](https://github.com/Quincy-Zh/insty/issues)，避免重复。
- **Bug 报告**：请附上：
  - 你的操作系统和 Python 版本
  - 完整的错误堆栈信息
  - 最小可复现示例代码
  - 仪器型号和 VISA 后端（如 NI-VISA / pyvisa-py）
- **新功能建议**：请清晰描述你的使用场景和期望的 API 行为。

### 2. 提交代码（Pull Request）

1. **Fork 本仓库** 并克隆到本地。
2. **创建新分支**：`git checkout -b feature/your-feature-name` 或 `fix/your-bug-fix`。
3. **编写代码**：请遵循以下代码规范。
4. **编写或更新测试**：确保你的代码有对应的测试用例（如果可能）。
5. **更新文档**：在 `README.md` 或 docstring 中更新相关说明。
6. **提交前检查**：运行 ruff 和测试（见下方"本地开发环境"）。
7. **发起 Pull Request (PR)**：
   - 描述中关联相关的 Issue（如 `Closes #123`）
   - 确保 PR 不是从你的 `main` 分支发出，而是从功能分支发出

**注意**：对于新增仪器驱动的 PR，我们会在合并前尽可能寻求硬件实测验证。

## 代码风格与规范

- **Python 版本**：我们支持 Python 3.8 及以上版本，请确保你的代码兼容。
- **静态检测**：使用 [`ruff`](https://github.com/astral-sh/ruff)（配置见 `pyproject.toml`，按 Py3.8 规则检查）：
  ```bash
  ruff check src tests
  ```
- **类型注解**：所有公共 API 必须包含完整的类型注解。代码使用 `X | Y` / `dict[str, ...]` 等新式注解，依赖 `from __future__ import annotations` 保持 Py3.8 兼容——**新文件必须加该导入**。
- **命名约定**：
  - 类名：`CamelCase`
  - 函数/方法名：`snake_case`
  - 常量：`UPPER_SNAKE_CASE`
- **语言**：所有注释、docstring、提交消息使用中文（与仓库历史一致）。
- **提交消息**：简短中文短语（如 `新增串口扫描支持`），不要使用英文 Conventional Commits 格式。
- **文档字符串**：公共类和方法必须包含描述性 docstring。

## 本地开发环境

### 安装开发依赖

```bash
# 克隆项目后，创建并激活虚拟环境（推荐）
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 以可编辑模式安装项目及开发依赖
pip install -e .
pip install pytest ruff
```

### 运行测试

**重要**：单元测试全部使用 mock 模拟硬件（`tests/test_instrument.py`，通过 monkeypatch `pyvisa.ResourceManager`），无需连接真实仪器。

- **运行所有测试**：
  ```bash
  pytest tests/
  ```
- **运行特定测试**：
  ```bash
  pytest tests/test_instrument.py -k <name>
  ```

### 设备表与扫描

设备信息按地址类型分两张表：

- **持久存储**（USB/TCPIP）：默认 `~/.insty/known_devices.json`，环境变量 `INSTY_DEVICE_STORE` 可覆盖
- **运行时表**（串口 ASRL）：程序传入的 device_table（JSON 路径，缺省为空内存表）

重建设备表：

```bash
python -m insty.scan [device_table.json]   # 缺省仅更新持久存储
```

## 新增仪器驱动的特别指南

这是对 `Insty` 最重要的贡献形式。请确保：

1. **继承正确的基类**：例如新增数字电源驱动，继承 `PowerSupply`。
2. **在 `__init__` 中调用 `super().__init__`**。
3. **实现所有抽象方法**（如 `set_voltage`、`read_current`）。
4. **在 `InstrumentRegistry` 中注册你的驱动**，并提供厂商和型号匹配规则（例如通过 `*IDN?` 返回的字符串前缀）。
5. **在 `drivers/__init__.py` 的导入链中加入新驱动模块**（导入即触发注册，漏加会导致注册不生效）。
6. **在 `README.md` 的"支持的仪器"表格中**，添加你的厂商和型号作为示例。

## 需要帮助？

如果你在贡献过程中有任何疑问，欢迎在 Issue 中提问或直接联系维护者。

再次感谢你的贡献！
