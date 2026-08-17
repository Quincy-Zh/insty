from __future__ import annotations

import os
import tempfile

import pytest

from insty import (
    DeviceTable,
    InstrumentBase,
    InstrumentInfo,
    InstrumentManager,
    InstrumentRegistry,
    InstrumentType,
    TransportBackend,
    VisaTransportBackend,
    make_instrument,
)
from insty.visa_based_instrument import VisaBasedInstrument

# ── 工具函数 ──────────────────────────────────────────────

def make_info(
    address: str, label: str,
    inst_type: InstrumentType = InstrumentType.DMM,
    supported: tuple = ("VOLTAGE_DC",),
) -> InstrumentInfo:
    return InstrumentInfo(address=address, label=label,
                          inst_type=inst_type, supported=supported)


# ── 基础测试 ──────────────────────────────────────────────

def test_make_instances():
    _33512B = make_instrument("AGILENT::33512B", None)
    assert isinstance(_33512B, VisaBasedInstrument)

    ATS_710 = make_instrument("TEMPTRONIC::ATS-710", None)
    assert isinstance(ATS_710, VisaBasedInstrument)

    IT6302 = make_instrument("ITECH::IT6302", None)
    assert isinstance(IT6302, VisaBasedInstrument)

    assert isinstance(make_instrument("KEITHLEY::DMM6500", None), VisaBasedInstrument)
    reg = InstrumentRegistry._registry.get("KEITHLEY::DMM6500")
    assert reg is not None
    assert reg[0] == InstrumentType.DMM
    assert "VOLTAGE_DC" in reg[1]


def test_methods_no_error():
    a = make_instrument("AGILENT::33512B", None)
    b = make_instrument("ITECH::IT6302", None)
    c = make_instrument("TEMPTRONIC::ATS-710", None)
    d = make_instrument("KEITHLEY::DMM6500", None)

    assert a is not None
    assert b is not None
    assert c is not None
    assert d is not None


def test_oscilloscope_execute_mode():
    """示波器 execute(mode) 不应与 VisaBasedInstrument 的 SCPI 执行器冲突"""
    from insty.drivers.zhiyuan_zds1000 import ZDS1104

    writes = []

    class FakeResource:
        def write(self, cmd):
            writes.append(cmd)

        def query(self, cmd):
            return None

        def close(self):
            pass

    osc = ZDS1104(FakeResource())
    osc.execute("single")
    assert writes == [":SINGle"]

    writes.clear()
    osc.execute("run")
    assert writes == [":RUN"]

    writes.clear()
    osc.execute("stop")
    assert writes == [":STOP"]

    with pytest.raises(ValueError):
        osc.execute("bogus")


def test_invalid():
    with pytest.raises(ValueError):
        make_instrument("UNKNOWN", None)


def test_base_instrument():
    with pytest.raises(TypeError):
        InstrumentBase()  # type: ignore


def test_format_idn():
    from insty.visa_backend import VisaTransportBackend
    assert VisaTransportBackend.format_idn("KEITHLEY, MODEL DMM6500") == "KEITHLEY::DMM6500"
    assert VisaTransportBackend.format_idn("AGILENT, 33512B") == "AGILENT::33512B"


def test_registry_accessible():
    assert "KEITHLEY::DMM6500" in InstrumentRegistry._registry
    assert "AGILENT::33512B" in InstrumentRegistry._registry


def test_register_type_methods():
    """每类 register_* 显式方法应设置正确的类型"""
    from insty.instrument_types import InstrumentRegistry

    class DummyOsc:
        pass

    InstrumentRegistry.register_oscilloscope(
        "TEST::DUMMY_OSC", DummyOsc, supported=("FREQUENCY",)
    )
    inst_type, supported = InstrumentRegistry.get_info("TEST::DUMMY_OSC")
    assert inst_type == InstrumentType.OSCILLOSCOPE
    assert supported == ("FREQUENCY",)
    assert InstrumentRegistry.get_driver("TEST::DUMMY_OSC") is DummyOsc

    InstrumentRegistry.register_power_supply(
        "TEST::DUMMY_PS", DummyOsc, supported=("VOLTAGE",)
    )
    inst_type, _ = InstrumentRegistry.get_info("TEST::DUMMY_PS")
    assert inst_type == InstrumentType.POWER_SUPPLY


# ── InstrumentType ─────────────────────────────────────────

def test_instrument_type_values():
    assert InstrumentType.DMM.value == "dmm"
    assert InstrumentType.OSCILLOSCOPE.value == "oscilloscope"


def test_instrument_type_from_str():
    assert InstrumentType("dmm") == InstrumentType.DMM
    assert InstrumentType("power_supply") == InstrumentType.POWER_SUPPLY


# ── InstrumentInfo ─────────────────────────────────────────

def test_instrument_info():
    info = make_info("addr", "VENDOR::M", InstrumentType.DMM, ("VOLTAGE_DC",))
    assert info.address == "addr"
    assert info.label == "VENDOR::M"
    assert info.inst_type == InstrumentType.DMM


def test_instrument_info_supports_with_enum():
    info = make_info("addr", "VENDOR::M", InstrumentType.DMM,
                     ("VOLTAGE_DC", "CURRENT_DC", "FREQUENCY|DUTY_CYCLE"))

    assert info.supports(InstrumentType.DMM, "VOLTAGE_DC") is True
    assert info.supports(InstrumentType.DMM, "FREQUENCY|DUTY_CYCLE") is True
    assert info.supports(InstrumentType.POWER_SUPPLY, "VOLTAGE_DC") is False


def test_instrument_info_supports_with_str():
    info = make_info("addr", "VENDOR::M", InstrumentType.DMM,
                     ("VOLTAGE_DC", "CURRENT_DC"))

    assert info.supports("dmm", "voltage_dc") is True
    assert info.supports("DMM", "VOLTAGE_DC") is True
    assert info.supports("power_supply", "current_dc") is False


def test_instrument_info_supports_with_type_tuple():
    info = make_info("addr", "VENDOR::M", InstrumentType.OSCILLOSCOPE,
                     ("FREQUENCY", "DUTY_CYCLE"))

    assert info.supports(
        (InstrumentType.OSCILLOSCOPE, InstrumentType.FREQUENCY_COUNTER),
        "FREQUENCY",
    ) is True
    assert info.supports(
        (InstrumentType.OSCILLOSCOPE,), "PERIOD"
    ) is False


def test_instrument_info_frozen():
    info = make_info("a", "L", InstrumentType.DMM)
    with pytest.raises(AttributeError):
        info.address = "b"  # type: ignore


def test_instrument_info_to_dict():
    info = make_info("addr", "VENDOR::M", InstrumentType.DMM, ("VOLTAGE_DC",))
    d = info.to_dict()
    assert d["address"] == "addr"
    assert d["label"] == "VENDOR::M"
    assert d["inst_type"] == "dmm"
    assert d["supported"] == ("VOLTAGE_DC",)


# ── VTS discover 返回 List[InstrumentInfo] ─────────────────

def test_vts_discover_returns_info(monkeypatch):
    from unittest.mock import MagicMock

    import pyvisa

    mock_rm = MagicMock()
    mock_rm.list_resources.return_value = ["USB0::123::INSTR"]
    monkeypatch.setattr(pyvisa, "ResourceManager", lambda: mock_rm)

    tmp = tempfile.mkdtemp()
    tbl_path = os.path.join(tmp, ".device_table.json")
    persist = DeviceTable(tbl_path)
    persist.set("USB0::123::INSTR", "KEITHLEY::DMM6500", serial_baud=None)

    backend = VisaTransportBackend(persistent_store=persist)
    result = backend.discover()

    assert len(result) == 1
    info = result[0]
    assert isinstance(info, InstrumentInfo)
    assert info.address == "USB0::123::INSTR"
    assert info.label == "KEITHLEY::DMM6500"
    assert info.inst_type == InstrumentType.DMM
    assert "VOLTAGE_DC" in info.supported


# ── 存在性检查（discover 不做 *IDN?） vs 显式全量识别（scan） ──

def test_vts_allow_auto_identify_usb_only(monkeypatch):
    """USB 地址自动识别，串口（ASRL）不自动识别"""
    from unittest.mock import MagicMock

    import pyvisa

    mock_rm = MagicMock()
    monkeypatch.setattr(pyvisa, "ResourceManager", lambda: mock_rm)
    backend = VisaTransportBackend(device_table=None)

    assert backend._allow_auto_identify("USB0::123::INSTR") is True
    assert backend._allow_auto_identify("TCPIP0::1.2.3.4::INSTR") is True
    assert backend._allow_auto_identify("ASRL3::INSTR") is False


def test_discover_presence_only_skips_unknown():
    """默认后端不对表外地址自动 *IDN?*，discover 只返回身份已知设备"""
    class Fake(TransportBackend):
        def _enum(self) -> list[str]:
            return ["dev"]
        def _identify(self, address: str) -> InstrumentInfo | None:
            return make_info("dev", "VENDOR::X")
        def open(self, address, label, timeout=30000):
            raise RuntimeError("No hardware")

    mgr = InstrumentManager(backends=[Fake()])
    assert mgr.discover() == []
    mgr.shutdown()


def test_discover_respects_allow_auto_identify():
    """后端允许时，discover 会识别表外地址并写回设备表（隔离持久存储，避免污染用户目录）"""
    class Fake(TransportBackend):
        def _enum(self) -> list[str]:
            return ["USB0::dev::INSTR"]
        def _identify(self, address: str) -> InstrumentInfo | None:
            return make_info(address, "VENDOR::X")
        def _allow_auto_identify(self, address: str) -> bool:
            return True
        def open(self, address, label, timeout=30000):
            raise RuntimeError("No hardware")

    mgr = InstrumentManager(
        backends=[Fake()], persistent_store=DeviceTable()
    )
    result = mgr.discover()
    assert len(result) == 1
    assert result[0].label == "VENDOR::X"
    mgr.shutdown()


def test_full_scan_writes_device_table():
    """显式 scan 对每个地址执行 _identify 并写回设备表"""
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "table.json")
    tbl = DeviceTable(path)

    class Fake(TransportBackend):
        def __init__(self, table):
            super().__init__(table)
        def _enum(self) -> list[str]:
            return ["ASRL1::INSTR"]
        def _identify(self, address: str) -> InstrumentInfo | None:
            return make_info(address, "MOCK::SERIAL")
        def open(self, address, label, timeout=30000):
            raise RuntimeError("No hardware")

    mgr = InstrumentManager(backends=[Fake(tbl)])
    result = mgr.full_scan()
    assert len(result) == 1
    assert result[0].label == "MOCK::SERIAL"
    assert tbl.get("ASRL1::INSTR")["label"] == "MOCK::SERIAL"
    mgr.shutdown()


# ── 双存储：USB/TCPIP 持久存储 vs 串口运行时表 ───────────

def test_discover_writes_persistent_store_for_stable_addr():
    """稳定唯一地址（USB/TCPIP）discover 自动识别并写入持久存储，不写运行时表"""
    class Fake(TransportBackend):
        def _enum(self) -> list[str]:
            return ["USB0::dev::INSTR"]
        def _identify(self, address: str) -> InstrumentInfo | None:
            return make_info(address, "VENDOR::X")
        def _allow_auto_identify(self, address: str) -> bool:
            return True
        def open(self, address, label, timeout=30000):
            raise RuntimeError("No hardware")

    runtime = DeviceTable()
    persist = DeviceTable()
    mgr = InstrumentManager(
        device_table=runtime, persistent_store=persist, backends=[Fake()]
    )
    result = mgr.discover()
    assert len(result) == 1
    assert persist.get("USB0::dev::INSTR")["label"] == "VENDOR::X"
    assert runtime.get("USB0::dev::INSTR") is None
    mgr.shutdown()


def test_scan_writes_persistent_store_for_stable_addr():
    """显式 scan 对稳定唯一地址写持久存储，串口地址写运行时表"""
    class Fake(TransportBackend):
        def _enum(self) -> list[str]:
            return ["USB0::dev::INSTR", "ASRL1::INSTR"]
        def _identify(self, address: str) -> InstrumentInfo | None:
            return make_info(address, "VENDOR::X")
        def _allow_auto_identify(self, address: str) -> bool:
            return not address.startswith("ASRL")
        def open(self, address, label, timeout=30000):
            raise RuntimeError("No hardware")

    runtime = DeviceTable()
    persist = DeviceTable()
    mgr = InstrumentManager(
        device_table=runtime, persistent_store=persist, backends=[Fake()]
    )
    result = mgr.full_scan()
    assert len(result) == 2
    assert persist.get("USB0::dev::INSTR")["label"] == "VENDOR::X"
    assert persist.get("ASRL1::INSTR") is None
    assert runtime.get("ASRL1::INSTR")["label"] == "VENDOR::X"
    assert runtime.get("USB0::dev::INSTR") is None
    mgr.shutdown()


def test_scan_keeps_same_label_devices_in_persistent_store():
    """持久存储（USB/TCPIP）：同 label 不同地址的多台设备互不删除（历史条目保留）"""
    class Fake(TransportBackend):
        def _enum(self) -> list[str]:
            return ["USB0::1::INSTR", "USB0::2::INSTR"]
        def _identify(self, address: str) -> InstrumentInfo | None:
            return make_info(address, "KEITHLEY::DMM6500")
        def _allow_auto_identify(self, address: str) -> bool:
            return not address.startswith("ASRL")
        def open(self, address, label, timeout=30000):
            raise RuntimeError("No hardware")

    persist = DeviceTable()
    persist.set("USB0::1::INSTR", "KEITHLEY::DMM6500", serial_baud=None)

    mgr = InstrumentManager(persistent_store=persist, backends=[Fake()])
    result = mgr.full_scan()
    assert len(result) == 2
    assert persist.get("USB0::1::INSTR")["label"] == "KEITHLEY::DMM6500"
    assert persist.get("USB0::2::INSTR")["label"] == "KEITHLEY::DMM6500"
    mgr.shutdown()


def test_scan_dedup_same_label_in_runtime_table():
    """运行时表（串口）：同 label 换口仍清除旧地址条目"""
    class Fake(TransportBackend):
        def _enum(self) -> list[str]:
            return ["ASRL5::INSTR"]
        def _identify(self, address: str) -> InstrumentInfo | None:
            return make_info(address, "KEITHLEY::DMM6500")
        def _allow_auto_identify(self, address: str) -> bool:
            return not address.startswith("ASRL")
        def open(self, address, label, timeout=30000):
            raise RuntimeError("No hardware")

    runtime = DeviceTable()
    runtime.set("ASRL3::INSTR", "KEITHLEY::DMM6500", serial_baud=115200)

    mgr = InstrumentManager(device_table=runtime, backends=[Fake()])
    result = mgr.full_scan()
    assert len(result) == 1
    assert runtime.get("ASRL3::INSTR") is None
    assert runtime.get("ASRL5::INSTR")["label"] == "KEITHLEY::DMM6500"
    mgr.shutdown()


def test_resolve_uses_persistent_store_for_usb():
    """resolve 对稳定唯一地址从持久存储解析，不查运行时表"""
    class Fake(TransportBackend):
        def _enum(self) -> list[str]:
            return []
        def _identify(self, address: str) -> InstrumentInfo | None:
            return None
        def _allow_auto_identify(self, address: str) -> bool:
            return not address.startswith("ASRL")
        def open(self, address, label, timeout=30000):
            raise RuntimeError("No hardware")

    runtime = DeviceTable()
    persist = DeviceTable()
    persist.set("USB0::1::INSTR", "KEITHLEY::DMM6500", serial_baud=None)

    mgr = InstrumentManager(
        device_table=runtime, persistent_store=persist, backends=[Fake()]
    )
    info = mgr.resolve("USB0::1::INSTR")
    assert info is not None
    assert info.label == "KEITHLEY::DMM6500"
    assert runtime.get("USB0::1::INSTR") is None
    mgr.shutdown()


def test_resolve_serial_writes_runtime_table():
    """resolve 对串口地址实时识别并写运行时表，不写持久存储"""
    class Fake(TransportBackend):
        def _enum(self) -> list[str]:
            return []
        def _identify(self, address: str) -> InstrumentInfo | None:
            return make_info(address, "MOCK::SERIAL")
        def open(self, address, label, timeout=30000):
            raise RuntimeError("No hardware")

    runtime = DeviceTable()
    persist = DeviceTable()
    mgr = InstrumentManager(
        device_table=runtime, persistent_store=persist, backends=[Fake()]
    )
    info = mgr.resolve("ASRL1::INSTR")
    assert info is not None
    assert info.label == "MOCK::SERIAL"
    assert runtime.get("ASRL1::INSTR")["label"] == "MOCK::SERIAL"
    assert persist.get("ASRL1::INSTR") is None
    mgr.shutdown()


def test_manager_finds_usb_from_persistent_store(monkeypatch):
    """InstrumentManager 不带 device_table 时，也能从持久存储发现 USB 设备"""
    from unittest.mock import MagicMock

    import pyvisa

    mock_rm = MagicMock()
    mock_rm.list_resources.return_value = ["USB0::1::INSTR"]
    monkeypatch.setattr(pyvisa, "ResourceManager", lambda: mock_rm)

    persist = DeviceTable()
    persist.set(
        "USB0::1::INSTR",
        "KEITHLEY::DMM6500",
        serial_baud=None,
        inst_type="dmm",
        supported=["VOLTAGE_DC"],
    )

    mgr = InstrumentManager(persistent_store=persist)
    infos = mgr.refresh()
    assert any(i.address == "USB0::1::INSTR" for i in infos)
    mgr.shutdown()


def test_default_persistent_store_path(monkeypatch):
    """persistent_store 默认路径：环境变量优先，否则 ~/.insty/known_devices.json"""
    tmp = tempfile.mkdtemp()
    env_path = os.path.join(tmp, "store.json")
    monkeypatch.setenv("INSTY_DEVICE_STORE", env_path)
    mgr = InstrumentManager()
    assert mgr.persistent_store.path == env_path
    mgr.shutdown()

    monkeypatch.delenv("INSTY_DEVICE_STORE")
    mgr2 = InstrumentManager()
    assert mgr2.persistent_store.path == os.path.join(
        os.path.expanduser("~"), ".insty", "known_devices.json"
    )
    mgr2.shutdown()


# ── scan 模块 ────────────────────────────────────────────────

def test_scan_no_arg_updates_persistent_store(monkeypatch):
    """python -m insty.scan 不带参数：识别结果写入持久存储（USB/TCPIP）"""
    import json
    from unittest.mock import MagicMock

    import pyvisa

    from insty.scan import scan

    tmp = tempfile.mkdtemp()
    store_path = os.path.join(tmp, "known_devices.json")
    monkeypatch.setenv("INSTY_DEVICE_STORE", store_path)

    mock_rm = MagicMock()
    mock_rm.list_resources.return_value = ["USB0::1::INSTR"]
    mock_inst = mock_rm.open_resource.return_value
    mock_inst.query.return_value = "KEITHLEY, MODEL DMM6500"
    monkeypatch.setattr(pyvisa, "ResourceManager", lambda: mock_rm)

    found = scan()
    assert found == 1

    with open(store_path, encoding="utf-8") as f:
        data = json.load(f)
    assert data["USB0::1::INSTR"]["label"] == "KEITHLEY::DMM6500"


def test_scan_with_arg_writes_runtime_table(monkeypatch):
    """python -m insty.scan <path>：串口识别结果写入传入的运行时表"""
    import json
    from unittest.mock import MagicMock

    import pyvisa

    from insty.scan import scan

    tmp = tempfile.mkdtemp()
    store_path = os.path.join(tmp, "known_devices.json")
    table_path = os.path.join(tmp, "device_table.json")
    monkeypatch.setenv("INSTY_DEVICE_STORE", store_path)

    mock_rm = MagicMock()
    mock_rm.list_resources.return_value = ["ASRL1::INSTR"]
    mock_inst = mock_rm.open_resource.return_value
    mock_inst.query.return_value = "KEITHLEY, MODEL DMM6500"
    monkeypatch.setattr(pyvisa, "ResourceManager", lambda: mock_rm)

    found = scan(table_path)
    assert found == 1

    with open(table_path, encoding="utf-8") as f:
        data = json.load(f)
    assert data["ASRL1::INSTR"]["label"] == "KEITHLEY::DMM6500"
    assert not os.path.exists(store_path)


# ── Manager ────────────────────────────────────────────────

def test_manager():
    mgr = InstrumentManager()
    assert mgr is not None
    mgr.shutdown()
    mgr2 = InstrumentManager()
    mgr2.shutdown()


def test_manager_without_visa_backend(monkeypatch):
    """无任何 VISA 实现时（如 CI 无 NI-VISA / pyvisa-py），构造与 shutdown 不应失败"""
    import pyvisa

    def boom():
        raise ValueError("Could not locate a VISA implementation")

    monkeypatch.setattr(pyvisa, "ResourceManager", boom)
    mgr = InstrumentManager()
    assert mgr is not None
    mgr.shutdown()


def test_transport_backend():
    with pytest.raises(TypeError):
        TransportBackend()  # type: ignore


def test_custom_backend():
    class MockBackend(TransportBackend):
        def _enum(self) -> list[str]:
            return ["COM3"]
        def _identify(self, address: str) -> InstrumentInfo | None:
            return make_info("COM3", "MOCK::DEVICE") if address == "COM3" else None
        def open(self, address: str, label: str, timeout: int = 30000):
            raise RuntimeError("No hardware")

    mgr = InstrumentManager(backends=[MockBackend()])
    result = mgr.full_scan()
    assert len(result) == 1
    assert result[0].address == "COM3"
    assert result[0].label == "MOCK::DEVICE"
    mgr.shutdown()


def test_multiple_backends():
    class BackendA(TransportBackend):
        def _enum(self) -> list[str]:
            return ["addr_a1"]
        def _identify(self, address: str) -> InstrumentInfo | None:
            return make_info("addr_a1", "VENDOR::A1") if address == "addr_a1" else None
        def open(self, address: str, label: str, timeout: int = 30000):
            raise RuntimeError("No hardware")

    class BackendB(TransportBackend):
        def _enum(self) -> list[str]:
            return ["addr_b1", "addr_b2"]
        def _identify(self, address: str) -> InstrumentInfo | None:
            return {
                "addr_b1": make_info("addr_b1", "VENDOR::B1", InstrumentType.POWER_SUPPLY),
                "addr_b2": make_info("addr_b2", "VENDOR::B2"),
            }.get(address)
        def open(self, address: str, label: str, timeout: int = 30000):
            raise RuntimeError("No hardware")

    mgr = InstrumentManager(backends=[BackendA(), BackendB()])
    result = mgr.full_scan()

    by_addr = {i.address: i for i in result}
    assert by_addr["addr_a1"].inst_type == InstrumentType.DMM
    assert by_addr["addr_b1"].inst_type == InstrumentType.POWER_SUPPLY
    assert by_addr["addr_b2"].inst_type == InstrumentType.DMM
    assert len(result) == 3
    mgr.shutdown()


def test_multiple_backends_with_connection():
    opened_by = {}

    class BackendA(TransportBackend):
        def _enum(self) -> list[str]:
            return ["port_a"]
        def _identify(self, address: str) -> InstrumentInfo | None:
            return make_info("port_a", "VENDOR::A") if address == "port_a" else None
        def open(self, address: str, label: str, timeout: int = 30000):
            if address != "port_a":
                raise RuntimeError(f"BackendA cannot open {address}")
            opened_by[address] = "A"
            class FakeInst(InstrumentBase):
                def configure(self, *args, **kwargs): return 0
                def get(self, *args, **kwargs): return None
                def set(self, *args, **kwargs): return 0
                def stop(self): return 0
                def close(self): return 0
            return FakeInst()

    class BackendB(TransportBackend):
        def _enum(self) -> list[str]:
            return ["port_b"]
        def _identify(self, address: str) -> InstrumentInfo | None:
            return make_info("port_b", "VENDOR::B", InstrumentType.POWER_SUPPLY) if address == "port_b" else None
        def open(self, address: str, label: str, timeout: int = 30000):
            if address != "port_b":
                raise RuntimeError(f"BackendB cannot open {address}")
            opened_by[address] = "B"
            class FakeInst(InstrumentBase):
                def configure(self, *args, **kwargs): return 0
                def get(self, *args, **kwargs): return None
                def set(self, *args, **kwargs): return 0
                def stop(self): return 0
                def close(self): return 0
            return FakeInst()

    mgr = InstrumentManager(backends=[BackendA(), BackendB()])

    inst_a = mgr.open("port_a", "VENDOR::A")
    assert opened_by["port_a"] == "A"
    assert inst_a is mgr.open("port_a", "VENDOR::A")

    mgr.open("port_b", "VENDOR::B")
    assert opened_by["port_b"] == "B"

    mgr.close("port_a")
    mgr.close("port_b")
    mgr.shutdown()


def test_register_backend():
    class ExtraBackend(TransportBackend):
        def _enum(self) -> list[str]:
            return ["extra"]
        def _identify(self, address: str) -> InstrumentInfo | None:
            return make_info("extra", "EXTRA::DEVICE") if address == "extra" else None
        def open(self, address: str, label: str, timeout: int = 30000):
            raise RuntimeError("No hardware")

    mgr = InstrumentManager(backends=[])
    assert len(mgr.backends) == 0

    mgr.register_backend(ExtraBackend())
    assert len(mgr.backends) == 1

    result = mgr.full_scan()
    assert result[0].inst_type == InstrumentType.DMM
    mgr.shutdown()


def test_discover_overlap_address():
    class BackendA(TransportBackend):
        def _enum(self) -> list[str]:
            return ["shared"]
        def _identify(self, address: str) -> InstrumentInfo | None:
            return make_info("shared", "VENDOR::A") if address == "shared" else None
        def open(self, address, label, timeout=30000):
            raise RuntimeError("No hardware")

    class BackendB(TransportBackend):
        def _enum(self) -> list[str]:
            return ["shared"]
        def _identify(self, address: str) -> InstrumentInfo | None:
            return make_info("shared", "VENDOR::B", InstrumentType.POWER_SUPPLY) if address == "shared" else None
        def open(self, address, label, timeout=30000):
            raise RuntimeError("No hardware")

    mgr = InstrumentManager(backends=[BackendA(), BackendB()])
    result = mgr.full_scan()
    assert len(result) == 1
    assert result[0].label == "VENDOR::B"
    assert result[0].inst_type == InstrumentType.POWER_SUPPLY
    mgr.shutdown()


def test_multiple_backends_fallback():
    class BadBackend(TransportBackend):
        def _enum(self) -> list[str]:
            return ["dev"]
        def _identify(self, address: str) -> InstrumentInfo | None:
            return make_info("dev", "VENDOR::FAIL") if address == "dev" else None
        def open(self, address, label, timeout=30000):
            raise RuntimeError("BadBackend cannot open")

    class GoodBackend(TransportBackend):
        def _enum(self) -> list[str]:
            return ["dev"]
        def _identify(self, address: str) -> InstrumentInfo | None:
            return make_info("dev", "VENDOR::OK") if address == "dev" else None
        def open(self, address, label, timeout=30000):
            class FakeInst(InstrumentBase):
                def configure(self, *args, **kwargs): return 0
                def get(self, *args, **kwargs): return None
                def set(self, *args, **kwargs): return 0
                def stop(self): return 0
                def close(self): return 0
            return FakeInst()

    mgr = InstrumentManager(backends=[BadBackend(), GoodBackend()])
    inst = mgr.open("dev", "VENDOR::OK")
    assert inst is not None
    mgr.close("dev")
    mgr.shutdown()


# ── 角色化接口（按类别访问，替代原 TestBench） ─────────────────

def make_role_backend(infos):
    """构造按给定 InstrumentInfo 列表识别的 mock 后端，open 返回通用假仪器"""
    class FakeInst:
        def set_voltage(self, volt, channel=1): pass
        def output_enable(self, channel=0): pass
        def output_disable(self, channel=0): pass
        def read_voltage(self, params=None): return 3.3
        def read_current(self, params=None): return 0.1
        def configure(self, *args, **kwargs): return None
        def get_status(self): return "RUN"
        def execute(self, mode): pass
        def read_frequency(self, channel=1): return 1000.0
        def read_duty_cycle(self, channel=1): return 0.5
        def read_pulse(self, channel=1): return 0.01
        def read_image(self): return b""
        def screenshot(self): return b""
        def set_temperature(self, temp, soak=15): pass
        def get_temperature(self): return -40.0
        def close(self): pass

    class RoleBackend(TransportBackend):
        def __init__(self, infos):
            super().__init__(persistent_store=DeviceTable())
            self._infos = infos
            self.opened = []

        def _enum(self):
            return [i.address for i in self._infos]

        def _identify(self, address):
            return next((i for i in self._infos if i.address == address), None)

        def _allow_auto_identify(self, address):
            return True

        def open(self, address, label, timeout=30000):
            self.opened.append(address)
            return FakeInst()

    return RoleBackend(infos)


def test_get_dmm_role():
    """get_dmm 按类别自动匹配，返回 DMMRole 并透传底层方法"""
    from insty import DMMRole

    infos = [make_info("dmm_addr", "KEITHLEY::DMM6500",
                       InstrumentType.DMM, ("VOLTAGE_DC", "CURRENT_DC"))]
    mgr = InstrumentManager(backends=[make_role_backend(infos)])
    try:
        role = mgr.get_dmm()
        assert isinstance(role, DMMRole)
        assert role.address == "dmm_addr"
        assert role.label == "KEITHLEY::DMM6500"
        assert role.read_voltage() == 3.3
        assert role.read_current() == 0.1
    finally:
        mgr.shutdown()


def test_get_power_supply_chain():
    """get_power_supply 返回 PowerSupplyRole，支持链式调用"""
    from insty import PowerSupplyRole

    infos = [make_info("ps_addr", "ITECH::IT6302",
                       InstrumentType.POWER_SUPPLY, ("VOLTAGE",))]
    mgr = InstrumentManager(backends=[make_role_backend(infos)])
    try:
        ps = mgr.get_power_supply()
        assert isinstance(ps, PowerSupplyRole)
        assert ps.set_voltage(3.3).output_enable() is ps
    finally:
        mgr.shutdown()


def test_get_role_with_address():
    """指定 address 时按地址匹配并校验能力"""
    from insty import DMMRole

    infos = [
        make_info("dmm_a", "KEITHLEY::DMM6500",
                  InstrumentType.DMM, ("VOLTAGE_DC",)),
        make_info("dmm_b", "AGILENT::34461A",
                  InstrumentType.DMM, ("VOLTAGE_DC",)),
    ]
    mgr = InstrumentManager(backends=[make_role_backend(infos)])
    try:
        role = mgr.get_dmm(address="dmm_b")
        assert isinstance(role, DMMRole)
        assert role.address == "dmm_b"
        assert mgr.get_dmm(address="dmm_a").address == "dmm_a"
    finally:
        mgr.shutdown()


def test_get_role_multiple_conflicts():
    """未指定 address 且存在多台同类别仪器时要求指定地址"""
    infos = [
        make_info("dmm_a", "KEITHLEY::DMM6500",
                  InstrumentType.DMM, ("VOLTAGE_DC",)),
        make_info("dmm_b", "AGILENT::34461A",
                  InstrumentType.DMM, ("VOLTAGE_DC",)),
    ]
    mgr = InstrumentManager(backends=[make_role_backend(infos)])
    try:
        with pytest.raises(RuntimeError, match="找到多台"):
            mgr.get_dmm()
    finally:
        mgr.shutdown()


def test_get_role_unsupported_address():
    """指定地址的仪器不支持所需能力时报错"""
    infos = [make_info("ps_addr", "ITECH::IT6302",
                       InstrumentType.POWER_SUPPLY, ("VOLTAGE",))]
    mgr = InstrumentManager(backends=[make_role_backend(infos)])
    try:
        with pytest.raises(RuntimeError, match="不支持"):
            mgr.get_dmm(address="ps_addr")
    finally:
        mgr.shutdown()


def test_get_role_no_match():
    """在线列表无匹配仪器时自动重试一次后报错"""
    infos = [make_info("dmm_addr", "KEITHLEY::DMM6500",
                       InstrumentType.DMM, ("VOLTAGE_DC",))]
    mgr = InstrumentManager(backends=[make_role_backend(infos)])
    try:
        with pytest.raises(RuntimeError, match="未找到可用"):
            mgr.get_power_supply()
    finally:
        mgr.shutdown()


def test_get_oscilloscope_frequency_counter_role():
    """示波器可充当频率计角色，返回 FrequencyCounterRole"""
    from insty import FrequencyCounterRole

    infos = [make_info("osc_addr", "ZHIYUAN::ZDS1104",
                       InstrumentType.OSCILLOSCOPE, ("FREQUENCY", "DUTY_CYCLE"))]
    mgr = InstrumentManager(backends=[make_role_backend(infos)])
    try:
        fc = mgr.get_frequency_counter()
        assert isinstance(fc, FrequencyCounterRole)
        assert fc.read_frequency() == 1000.0
        assert fc.read_duty_cycle() == 0.5
    finally:
        mgr.shutdown()


def test_get_role_uses_open_connection_cache():
    """同一地址重复获取时复用管理器已打开的连接"""
    infos = [make_info("dmm_addr", "KEITHLEY::DMM6500",
                       InstrumentType.DMM, ("VOLTAGE_DC",))]
    backend = make_role_backend(infos)
    mgr = InstrumentManager(backends=[backend])
    try:
        r1 = mgr.get_dmm()
        r2 = mgr.get_dmm()
        assert r1.inst is r2.inst
        assert backend.opened == ["dmm_addr"]
    finally:
        mgr.shutdown()


def test_manager_context_manager():
    """InstrumentManager 支持 with 语法，退出时自动关闭全部连接"""
    from insty import DMMRole

    infos = [make_info("dmm_addr", "KEITHLEY::DMM6500",
                       InstrumentType.DMM, ("VOLTAGE_DC",))]
    with InstrumentManager(backends=[make_role_backend(infos)]) as mgr:
        role = mgr.get_dmm()
        assert isinstance(role, DMMRole)
        assert role.read_voltage() == 3.3


def test_manager_refresh_and_full_scan_cache():
    """refresh/full_scan 均更新角色匹配用的在线缓存"""
    infos = [make_info("dmm_addr", "KEITHLEY::DMM6500",
                       InstrumentType.DMM, ("VOLTAGE_DC",))]
    backend = make_role_backend(infos)
    mgr = InstrumentManager(backends=[backend])
    try:
        assert [i.address for i in mgr.refresh()] == ["dmm_addr"]
        assert mgr._infos is not None
        assert [i.address for i in mgr.full_scan()] == ["dmm_addr"]
        assert mgr._infos is not None
    finally:
        mgr.shutdown()


def test_frange():
    from insty import frange
    assert frange(0, 1, 0.25) == [0.0, 0.25, 0.5, 0.75, 1.0]
    with pytest.raises(ValueError):
        frange(0, 1, 0)
