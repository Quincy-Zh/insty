# Contributing to Insty

首先，感谢你愿意为 `Insty` 贡献代码、文档或建议！我们非常欢迎来自社区的任何形式的贡献。

这份指南旨在帮助你了解如何参与项目，并确保你的贡献能顺利被合并。

## 行为准则

本项目遵循 [Python 社区行为准则](https://www.python.org/psf/codeofconduct/)。请确保你的言行友善、尊重、包容。

## 如何贡献

### 1. 报告 Bug 或提出新功能

- 在提交 Issue 前，请先搜索[现有 Issues](https://github.com/your-username/insty/issues)，避免重复。
- **Bug 报告**：请使用 Issue 模板（如果已配置），并附上：
  - 你的操作系统和 Python 版本
  - 完整的错误堆栈信息
  - 最小可复现示例代码
  - 仪器型号和 VISA 后端（如 NI-VISA / pyvisa-py）
- **新功能建议**：请清晰描述你的使用场景和期望的 API 行为。

### 2. 提交代码（Pull Request）

我们非常欢迎驱动扩展、Bug 修复和性能改进！请遵循以下流程：

1. **Fork 本仓库** 并克隆到本地。
2. **创建新分支**：`git checkout -b feature/your-feature-name` 或 `fix/your-bug-fix`。
3. **编写代码**：请遵循以下代码规范。
4. **编写或更新测试**：确保你的代码有对应的测试用例（如果可能）。
5. **更新文档**：在 `README.md` 或 docstring 中更新相关说明。
6. **提交前检查**：运行 lint 和测试（见下方“本地开发环境”）。
7. **发起 Pull Request (PR)**：
   - 标题清晰，例如：`feat: add support for Keysight E36313A power supply`
   - 描述中关联相关的 Issue（如 `Closes #123`）
   - 确保 PR 不是从你的 `main` 分支发出，而是从功能分支发出

**注意**：对于新增仪器驱动的 PR，我们会在合并前尽可能寻求硬件实测验证。

## 代码风格与规范

- **Python 版本**：我们支持 Python 3.9 及以上版本，请确保你的代码兼容。
- **格式化**：使用 [`black`](https://github.com/psf/black) 进行代码格式化（我们使用默认配置）。
- **导入排序**：使用 [`isort`](https://github.com/PyCQA/isort) 整理导入顺序（与 `black` 兼容的配置）。
- **类型注解**：所有公共 API 必须包含完整的类型注解（`typing` 或 `typing-extensions`）。
- **命名约定**：
  - 类名：`CamelCase`
  - 函数/方法名：`snake_case`
  - 常量：`UPPER_SNAKE_CASE`
- **文档字符串**：公共类和方法必须包含描述性 docstring，建议使用 Google 风格或 NumPy 风格。

## 本地开发环境

### 安装开发依赖

```bash
# 克隆项目后，创建并激活虚拟环境（推荐）
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 以可编辑模式安装项目及开发依赖
pip install -e .[dev]
```

如果 `pyproject.toml` 中还没有定义 `[project.optional-dependencies]`，可以临时手动安装：

```bash
pip install black isort pytest pytest-cov
```

### 运行测试

**重要**：由于 `Insty` 控制真实硬件，大部分测试需要连接实际仪器。我们在 CI 中会使用模拟后端进行基础测试。

- **运行所有测试**：
  ```bash
  pytest tests/
  ```
- **运行特定测试**：
  ```bash
  pytest tests/test_power_supply.py
  ```
- **查看测试覆盖率**：
  ```bash
  pytest --cov=insty tests/
  ```

### 模拟硬件环境（重要）

如果你没有真实仪器，可以：

1. 使用 `pyvisa-py` 的 `@sim` 模拟资源（参考 `pyvisa-py` 文档）。
2. 在 `tests/conftest.py` 中，我们提供了一个 `MockTransportBackend`，你可以继承 `TransportBackend` 并模拟读写行为来编写单元测试。

## 新增仪器驱动的特别指南

这是对 `Insty` 最重要的贡献形式。请确保：

1. **继承正确的基类**：例如新增数字电源驱动，继承 `PowerSupplyBase`。
2. **在 `__init__` 中调用 `super().__init__`**。
3. **实现所有抽象方法**（如 `set_voltage`、`measure_current`）。
4. **在 `InstrumentRegistry` 中注册你的驱动**，并提供厂商和型号匹配规则（例如通过 `*IDN?` 返回的字符串前缀）。
5. **在 `README.md` 的“支持的仪器”表格中**，添加你的厂商和型号作为示例。

## 提交消息规范

我们推荐使用 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/v1.0.0/) 风格，使提交历史更清晰：

- `feat:` 新功能
- `fix:` Bug 修复
- `docs:` 仅文档更改
- `style:` 代码格式（不影响代码运行的更改）
- `refactor:` 代码重构
- `test:` 添加或修改测试
- `chore:` 构建过程或辅助工具的变动

**示例**：
```
feat: add SCPI command wrapper for frequency measurement
fix: handle timeout exception in serial port scanning
docs: update installation guide for Windows users
```

## 需要帮助？

如果你在贡献过程中有任何疑问，欢迎在 Issue 中提问或直接联系维护者。

再次感谢你的贡献！🎉
