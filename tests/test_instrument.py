from __future__ import annotations

import os
import tempfile

import pytest

from insty import (
    DMM,
    Instrument,
    InstrumentInfo,
    InstrumentManager,
    InstrumentRegistry,
    InstrumentType,
    Oscilloscope,
    PowerSupply,
    ThermalChamber,
    TransportBackend,
    VisaTransportBackend,
    WaveformGenerator,
    make_instrument,
)
from insty.device_table import DeviceTable
from insty.visa_based_instrument import VisaBasedInstrument


@pytest.fixture(autouse=True)
def _isolate_persistent_store(tmp_path, monkeypatch):
    """隔离持久存储：测试默认写入临时目录，避免污染用户 ~/.insty"""
    monkeypatch.setenv("INSTY_DEVICE_STORE", str(tmp_path / "known_devices.json"))


@pytest.fixture(autouse=True)
def _no_real_visa(monkeypatch):
    """隔离真实 VISA 资源：ResourceManager 无资源且打开失败，避免测试接触真机

    个别测试（如 scan 系列）会自行覆盖 pyvisa.ResourceManager。
    """
    from unittest.mock import MagicMock

    import pyvisa

    mock_rm = MagicMock()
    mock_rm.list_resources.return_value = []
    mock_rm.open_resource.side_effect = ValueError("No real VISA hardware")
    monkeypatch.setattr(pyvisa, "ResourceManager", lambda: mock_rm)

# ── 工具函数 ──────────────────────────────────────────────

def make_info(
    address: str, label: str,
    inst_type: InstrumentType = InstrumentType.DMM,
    supported: tuple = ("VOLTAGE_DC",),
) -> InstrumentInfo:
    return InstrumentInfo(address=address, label=label,
                          inst_type=inst_type, supported=supported)


def test_frange():
    """frange 生成含端点的浮点等差数列，step 为 0 抛 ValueError"""
    from insty import frange
    assert frange(0, 1, 0.25) == [0.0, 0.25, 0.5, 0.75, 1.0]
    assert frange(1, 3) == [1.0, 2.0, 3.0]
    assert frange(1, 0.25, -0.25) == [1.0, 0.75, 0.5, 0.25]
    assert frange(0, 1, 0.3) == [0.0, 0.3, 0.6, 0.9, 1.0]
    # 端点不在网格上时追加补上，保证 stop 一定包含
    assert frange(1.8, 3.6, 0.25) == [1.8, 2.05, 2.3, 2.55, 2.8, 3.05, 3.3, 3.55, 3.6]
    with pytest.raises(ValueError):
        frange(0, 1, 0)


# ── 基础测试 ──────────────────────────────────────────────

def test_make_instances():
    _33522B = make_instrument("AGILENT::33522B", None)
    assert isinstance(_33522B, VisaBasedInstrument)

    ATS_710 = make_instrument("TEMPTRONIC::ATS-710", None)
    assert isinstance(ATS_710, VisaBasedInstrument)

    IT6302 = make_instrument("ITECH::IT6302", None)
    assert isinstance(IT6302, VisaBasedInstrument)

    assert isinstance(make_instrument("KEITHLEY::DMM6500", None), VisaBasedInstrument)
    reg = InstrumentRegistry._registry.get("KEITHLEY::DMM6500")
    assert reg is not None
    assert reg[0] == InstrumentType.DMM
    assert "VOLTAGE_DC" in reg[1]


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
        Instrument()  # type: ignore


def test_get_errors_drains_queue():
    """get_errors 循环查询 SYSTem:ERRor? 直到返回 +0,"No error" """
    responses = iter([
        '-222,"Data out of range"',
        '-113,"Undefined header"',
        '+0,"No error"',
    ])

    class FakeResource:
        def write(self, cmd):
            pass

        def query(self, cmd):
            assert cmd == "SYSTem:ERRor?"
            return next(responses)

        def close(self):
            pass

    inst = VisaBasedInstrument(FakeResource())
    assert inst.get_errors() == [
        '-222,"Data out of range"',
        '-113,"Undefined header"',
    ]


def test_get_errors_no_error():
    """设备无错误时 get_errors 返回空列表"""
    class FakeResource:
        def query(self, cmd):
            return '+0,"No error"'

        def close(self):
            pass

    inst = VisaBasedInstrument(FakeResource())
    assert inst.get_errors() == []


def test_get_errors_exposed_on_type_classes():
    """get_errors 通过 Instrument 基类暴露给 DMM/频率计等类型，VISA 驱动走真实实现"""
    from insty.instrument_types import DMM, Instrument, ThermalChamber

    assert callable(DMM.get_errors)
    assert callable(Instrument.get_errors)
    assert ThermalChamber.get_errors is Instrument.get_errors

    from insty.drivers.keithley_dmm6500 import KeithleyDMM6500
    assert KeithleyDMM6500.get_errors is VisaBasedInstrument.get_errors


def test_setup_default_and_driver_impl():
    """setup 由 Instrument 提供默认实现，具体驱动可重写（ZDS 透传 configure）"""
    from insty.drivers.agilent_53220_53230 import Agilent53220A
    from insty.drivers.zhiyuan_zds1000 import ZDS1104

    class FakeResource:
        def query(self, cmd):
            return None

        def write(self, cmd):
            pass

        def set_visa_attribute(self, attr, val):
            pass

        def close(self):
            pass

    cnt = Agilent53220A(FakeResource())
    assert cnt.setup() is cnt

    osc = ZDS1104(FakeResource())
    assert osc.setup(baudrate=115200) is osc


def test_waveform_setup_wave_conditional_params():
    """setup 的 wave 为必选位置参数，其余参数按波形取舍：DC 只需 vpp，freq/offset 忽略"""
    from insty.drivers.agilent_33500_33600 import Agilent33522B

    writes = []

    class FakeResource:
        def write(self, cmd):
            writes.append(cmd)

        def close(self):
            pass

    inst = Agilent33522B(FakeResource())
    with pytest.raises(TypeError):
        inst.setup()

    inst.setup("DC", offset=2.5)
    assert any("VOLTage:OFFSet 2.5" in c for c in writes)
    assert not any("FREQuency" in c for c in writes)

    with pytest.raises(KeyError):
        inst.setup("DC")
    # 非 DC 波形仍需 freq/vpp/offset
    with pytest.raises(KeyError):
        inst.setup("SIN", freq=1000.0, vpp=3.3)
    # channel 为 keyword-only，不能按位置传
    with pytest.raises(TypeError):
        inst.setup("SIN", 2, freq=1000.0, vpp=3.3, offset=0.0)
    # channel 关键字传参 + wave 位置传参
    writes.clear()
    inst.setup("SIN", channel=2, freq=1000.0, vpp=3.3, offset=0.0)
    assert any("SOURce2:FREQuency 1000.0" in c for c in writes)


def test_waveform_channels_and_channel_param():
    """基类 channels 属性与 channel 参数校验"""
    from insty.drivers.agilent_33500_33600 import Agilent33519B, Agilent33522B

    class FakeResource:
        def write(self, cmd):
            pass

        def close(self):
            pass

    inst = Agilent33522B(FakeResource())
    assert inst.channels == 2
    with pytest.raises(ValueError):
        inst.setup(channel=3, wave="SIN", freq=1000.0, vpp=3.3, offset=0.0)

    inst19 = Agilent33519B(FakeResource())
    assert inst19.channels == 1
    with pytest.raises(ValueError):
        inst19.output_enable(channel=2)


def test_waveform_output_all_channels_via_close():
    """channel=0 不再支持，close() 逐通道关闭全部输出（33522B 双通道）"""
    from insty.drivers.agilent_33500_33600 import Agilent33522B

    writes = []

    class FakeResource:
        def write(self, cmd):
            writes.append(cmd)

        def close(self):
            writes.append("_closed")

    inst = Agilent33522B(FakeResource())
    with pytest.raises(ValueError):
        inst.output_disable(0)
    with pytest.raises(ValueError):
        inst.output_enable(0)
    # 先开启两通道，close() 逐通道关闭已开启的输出
    inst.output_enable(1)
    inst.output_enable(2)
    inst.close()
    assert writes == [
        "OUTPut1 ON",
        "OUTPut2 ON",
        "SOURce1:VOLTage MIN",
        "SOURce1:VOLTage:OFFSet 0",
        "OUTPut1 OFF",
        "SOURce2:VOLTage MIN",
        "SOURce2:VOLTage:OFFSet 0",
        "OUTPut2 OFF",
        "_closed",
    ]


def test_waveform_output_state_tracking():
    """output_enable/disable 状态幂等（重复调用不重复下发），setup 先关闭全部通道"""
    from insty.drivers.agilent_33500_33600 import Agilent33522B

    writes = []

    class FakeResource:
        def write(self, cmd):
            writes.append(cmd)

        def close(self):
            pass

    inst = Agilent33522B(FakeResource())
    # 幂等：已开启的通道重复 enable 不重复下发；已关闭的通道重复 disable 不重复下发
    inst.output_enable(1)
    inst.output_enable(1)
    assert writes == ["OUTPut1 ON"]
    writes.clear()
    inst.output_disable(1)
    inst.output_disable(1)
    assert writes == ["SOURce1:VOLTage MIN", "SOURce1:VOLTage:OFFSet 0", "OUTPut1 OFF"]

    # setup 会先关闭全部通道，再配置当前通道
    writes.clear()
    inst.setup(wave="SIN", freq=1000.0, vpp=3.3, offset=0.0)
    assert writes[0] == "OUTPut1 OFF"
    assert writes[1] == "OUTPut2 OFF"
    # setup 后状态已重置，重新 enable 需再下发
    writes.clear()
    inst.output_enable(2)
    assert writes == ["OUTPut2 ON"]


def test_waveform_channel_specific_command():
    """多通道按 channel 下发命令，单通道无数字后缀"""
    from insty.drivers.agilent_33500_33600 import Agilent33519B, Agilent33522B

    writes_22b = []

    class Fake22B(Agilent33522B):
        def run_cmds(self, cmds):
            writes_22b.extend(cmds)
            return True

    inst = Fake22B(None)
    inst.output_enable(channel=2)
    assert writes_22b == ["OUTPut2 ON"]
    inst.set_frequency(1000.0, channel=2)
    assert "SOURce2:FREQuency 1000.0" in writes_22b

    writes_19b = []

    class Fake19B(Agilent33519B):
        def run_cmds(self, cmds):
            writes_19b.extend(cmds)
            return True

    inst19 = Fake19B(None)
    inst19.output_enable()
    assert writes_19b == ["OUTPut ON"]


def test_waveform_setup_lowercase_params():
    """波形发生器 setup 参数名必须为小写，参数值大小写不敏感"""
    from insty.drivers.agilent_33500_33600 import Agilent33522B

    writes = []

    class FakeResource:
        def write(self, cmd):
            writes.append(cmd)

        def close(self):
            pass

    inst = Agilent33522B(FakeResource())
    inst.setup(wave="SIN", freq=1000.0, vpp=3.3, offset=0.0)
    assert any("FREQuency 1000.0" in c for c in writes)


def test_waveform_parameter_validation():
    """setup 参数校验：偏置上限/直流电平/频率幅度下界/占空比范围"""
    from insty.drivers.agilent_33500_33600 import Agilent33522B

    class FakeResource:
        def write(self, cmd):
            pass

        def close(self):
            pass

    inst = Agilent33522B(FakeResource())

    # |offset| 必须小于 Vmax - vpp/2（高阻 10V 峰值，vpp=3.3 时上限 8.35）
    with pytest.raises(ValueError):
        inst.setup(wave="SIN", freq=1000.0, vpp=3.3, offset=9.0)
    # 频率/幅度必须为正
    with pytest.raises(ValueError):
        inst.setup(wave="SIN", freq=0.0, vpp=3.3, offset=0.0)
    with pytest.raises(ValueError):
        inst.setup(wave="SIN", freq=1000.0, vpp=-1.0, offset=0.0)
    # DC 电平不超过 ±Vmax
    with pytest.raises(ValueError):
        inst.setup(wave="DC", offset=12.0)
    # SQU 占空比 0.01~99.99
    with pytest.raises(ValueError):
        inst.setup(wave="SQU", freq=1000.0, vpp=3.3, offset=0.0, duty_cycle=0.0)
    with pytest.raises(ValueError):
        inst.setup(wave="SQU", freq=1000.0, vpp=3.3, offset=0.0, duty_cycle=100.0)
    # RAMP 对称性 0~100 允许 100
    inst.setup(wave="RAMP", freq=1000.0, vpp=3.3, offset=0.0, duty_cycle=100.0)


def test_waveform_setter_incremental_validation():
    """set_offset/set_amplitude 增量修改时复用偏置上限校验"""
    from insty.drivers.agilent_33500_33600 import Agilent33522B

    class FakeResource:
        def write(self, cmd):
            pass

        def close(self):
            pass

    inst = Agilent33522B(FakeResource())
    inst.setup(wave="SIN", freq=1000.0, vpp=3.3, offset=0.0)
    # setup 后单独加大偏置应被拦截（10 - 3.3/2 = 8.35）
    with pytest.raises(ValueError):
        inst.set_offset(9.0)
    # 增大幅度使现有偏置越界应被拦截
    inst.setup(wave="SIN", freq=1000.0, vpp=3.3, offset=5.0)
    with pytest.raises(ValueError):
        inst.set_amplitude(15.0)
    # DC 模式 set_offset 校验 ±Vmax
    inst.setup(wave="DC", offset=5.0)
    with pytest.raises(ValueError):
        inst.set_offset(11.0)
    # DC 模式无幅度概念，set_amplitude 应被拒绝
    with pytest.raises(ValueError):
        inst.set_amplitude(2.0)


def test_waveform_output_load():
    """set_output_load 校验并下发 OUTPut:LOAD，setup 沿用当前负载"""
    from insty.drivers.agilent_33500_33600 import Agilent33522B

    writes = []

    class FakeResource:
        def write(self, cmd):
            writes.append(cmd)

        def close(self):
            pass

    inst = Agilent33522B(FakeResource())
    inst.set_output_load(50)
    assert "OUTPut1:LOAD 50" in writes
    inst.set_output_load("infinity", channel=2)
    assert "OUTPut2:LOAD INF" in writes
    with pytest.raises(ValueError):
        inst.set_output_load(0)
    with pytest.raises(ValueError):
        inst.set_output_load(20000)
    with pytest.raises(ValueError):
        inst.set_output_load("HIGH")

    writes.clear()
    inst.set_output_load(50)
    inst.setup(wave="SIN", freq=1000.0, vpp=3.3, offset=0.0)
    assert any("OUTPut1:LOAD 50" in c for c in writes)

    # setup 直接指定 output_load
    writes.clear()
    inst.setup(wave="SIN", freq=1000.0, vpp=3.3, offset=0.0, output_load=50)
    assert any("OUTPut1:LOAD 50" in c for c in writes)
    writes.clear()
    inst.setup(wave="SIN", freq=1000.0, vpp=3.3, offset=0.0, output_load="INFinity")
    assert any("OUTPut1:LOAD INF" in c for c in writes)
    with pytest.raises(ValueError):
        inst.setup(wave="SIN", freq=1000.0, vpp=3.3, offset=0.0, output_load=0)


def test_waveform_frequency_limit():
    """各波形频率上限校验：RAMP/TRI 200kHz，SIN 30MHz（33522B）/80MHz（33612A）"""
    from insty.drivers.agilent_33500_33600 import Agilent33522B, Agilent33612A

    class FakeResource:
        def write(self, cmd):
            pass

        def close(self):
            pass

    inst = Agilent33522B(FakeResource())
    # RAMP 超 200kHz 被拦截
    with pytest.raises(ValueError, match="exceeds RAMP max"):
        inst.setup(wave="RAMP", freq=300e3, vpp=3.3, offset=0.0)
    # SIN 超 30MHz 被拦截
    with pytest.raises(ValueError, match="exceeds SIN max"):
        inst.setup(wave="SIN", freq=31e6, vpp=3.3, offset=0.0)
    # set_frequency 同样校验
    inst.setup(wave="SIN", freq=1000.0, vpp=3.3, offset=0.0)
    with pytest.raises(ValueError, match="exceeds SIN max"):
        inst.set_frequency(31e6)

    # 33612A SIN 上限 80MHz
    inst3612 = Agilent33612A(FakeResource())
    inst3612.setup(wave="SIN", freq=50e6, vpp=3.3, offset=0.0)  # 50MHz 合法
    with pytest.raises(ValueError, match="exceeds SIN max"):
        inst3612.setup(wave="SIN", freq=81e6, vpp=3.3, offset=0.0)


def test_waveform_voltage_limit():
    """set_voltage_limit 校验并下发 VOLTage:LIMit:HIGH/LOW + STATe ON"""
    from insty.drivers.agilent_33500_33600 import Agilent33522B

    writes = []

    class FakeResource:
        def write(self, cmd):
            writes.append(cmd)

        def close(self):
            pass

    inst = Agilent33522B(FakeResource())
    # high <= low 报错
    with pytest.raises(ValueError, match="HIGH must be greater than LOW"):
        inst.set_voltage_limit(0.0, 5.0)
    # 超 Vmax 报错
    with pytest.raises(ValueError, match="Limit exceeds Vmax"):
        inst.set_voltage_limit(15.0, -15.0)

    writes.clear()
    inst.set_voltage_limit(3.3, -0.5)
    assert any("VOLTage:LIMit:HIGH 3.3" in c for c in writes)
    assert any("VOLTage:LIMit:LOW -0.5" in c for c in writes)
    assert any("VOLTage:LIMit:STATe ON" in c for c in writes)


def test_waveform_setup_dut_limit():
    """setup 支持 dut_high/dut_low 可选参数下发 VOLTage:LIMit"""
    from insty.drivers.agilent_33500_33600 import Agilent33522B

    writes = []

    class FakeResource:
        def write(self, cmd):
            writes.append(cmd)

        def close(self):
            pass

    inst = Agilent33522B(FakeResource())
    # 不传 dut_high/dut_low 时无 LIMit 命令
    inst.setup(wave="SIN", freq=1000.0, vpp=3.3, offset=0.0)
    assert not any("LIMit" in c for c in writes)

    # 传入后下发 LIMit 命令
    writes.clear()
    inst.setup(wave="SIN", freq=1000.0, vpp=3.3, offset=0.0, dut_high=3.3, dut_low=-0.5)
    assert any("VOLTage:LIMit:HIGH 3.3" in c for c in writes)
    assert any("VOLTage:LIMit:LOW -0.5" in c for c in writes)
    assert any("VOLTage:LIMit:STATe ON" in c for c in writes)


def test_waveform_polarity():
    """set_polarity 校验并下发 OUTPut:POLarity"""
    from insty.drivers.agilent_33500_33600 import Agilent33519B

    writes = []

    class FakeResource:
        def write(self, cmd):
            writes.append(cmd)

        def close(self):
            pass

    inst = Agilent33519B(FakeResource())
    inst.set_polarity("INVerted")
    assert writes == ["OUTPut:POLarity INVerted"]
    writes.clear()
    inst.set_polarity("NORM")
    assert writes == ["OUTPut:POLarity NORMal"]
    with pytest.raises(ValueError):
        inst.set_polarity("REVERSE")


def test_waveform_set_phase():
    """set_phase 校验范围并下发 PHASe（多通道带通道号）"""
    from insty.drivers.agilent_33500_33600 import Agilent33519B, Agilent33522B

    writes = []

    class FakeResource:
        def write(self, cmd):
            writes.append(cmd)

        def close(self):
            pass

    inst = Agilent33519B(FakeResource())
    inst.set_phase(45.0)
    assert writes == ["SOURce:PHASe 45.0"]
    with pytest.raises(ValueError):
        inst.set_phase(361.0)
    with pytest.raises(ValueError):
        inst.set_phase(-361.0)

    inst22 = Agilent33522B(FakeResource())
    writes.clear()
    inst22.set_phase(30.0, channel=2)
    assert writes == ["SOURce2:PHASe 30.0"]


def test_waveform_vmax_follows_load():
    """Vmax 随终止负载变化：50Ω 峰值 5V，偏置上限收窄"""
    from insty.drivers.agilent_33500_33600 import Agilent33522B

    class FakeResource:
        def write(self, cmd):
            pass

        def close(self):
            pass

    inst = Agilent33522B(FakeResource())
    inst.set_output_load(50)
    # 50Ω 下 |offset| < 5 - vpp/2 = 3.35
    with pytest.raises(ValueError):
        inst.setup(wave="SIN", freq=1000.0, vpp=3.3, offset=4.0)
    inst.setup(wave="SIN", freq=1000.0, vpp=3.3, offset=3.0)
    with pytest.raises(ValueError):
        inst.set_offset(4.0)


def test_53220a_read_frequency_invalid_returns_none():
    """53220A 读取到 INFinity 或 >= 9.9E+37 视为无效，返回 None"""
    from insty.drivers.agilent_53220_53230 import Agilent53220A

    class FakeResource:
        def __init__(self, resp):
            self._resp = resp

        def query(self, cmd):
            return self._resp

        def close(self):
            pass

    for bad in ("INFinity", "+9.9E+37", "9.900000E+37"):
        inst = Agilent53220A(FakeResource(bad))
        assert inst.read_frequency() is None

    inst = Agilent53220A(FakeResource("1000.0"))
    assert inst.read_frequency() == 1000.0


def test_format_idn():
    from insty.visa_backend import VisaTransportBackend
    assert VisaTransportBackend.format_idn("KEITHLEY, MODEL DMM6500") == "KEITHLEY::DMM6500"
    assert VisaTransportBackend.format_idn("AGILENT, 33522B") == "AGILENT::33522B"


def test_registry_accessible():
    assert "KEITHLEY::DMM6500" in InstrumentRegistry._registry
    assert "AGILENT::33522B" in InstrumentRegistry._registry


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
    info = make_info("addr", "VENDOR::M", InstrumentType.OSCILLOSCOPE,
                     ("FREQUENCY", "FREQUENCY|DUTY_CYCLE"))

    assert info.supports(InstrumentType.OSCILLOSCOPE, "FREQUENCY") is True
    assert info.supports(InstrumentType.OSCILLOSCOPE, "FREQUENCY|DUTY_CYCLE") is True
    assert info.supports(InstrumentType.POWER_SUPPLY, "FREQUENCY") is False


def test_instrument_info_supports_with_str():
    info = make_info("addr", "VENDOR::M", InstrumentType.DMM,
                     ("VOLTAGE_DC", "CURRENT_DC"))

    assert info.supports("dmm", "voltage_dc") is True
    assert info.supports("DMM", "VOLTAGE_DC") is True
    assert info.supports("power_supply", "current_dc") is False


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
    DeviceTable(tbl_path).set("USB0::123::INSTR", "KEITHLEY::DMM6500", serial_baud=None)

    backend = VisaTransportBackend(persistent_store=tbl_path)
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

    mgr = InstrumentManager()
    mgr.register_backend(Fake())
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

    mgr = InstrumentManager()
    mgr.register_backend(Fake())
    result = mgr.discover()
    assert len(result) == 1
    assert result[0].label == "VENDOR::X"
    mgr.shutdown()


def test_full_scan_writes_device_table():
    """显式 scan 对每个地址执行 _identify 并写回设备表"""
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "table.json")

    class Fake(TransportBackend):
        def __init__(self, table_path):
            super().__init__(table_path)
        def _enum(self) -> list[str]:
            return ["ASRL1::INSTR"]
        def _identify(self, address: str) -> InstrumentInfo | None:
            return make_info(address, "MOCK::SERIAL")
        def open(self, address, label, timeout=30000):
            raise RuntimeError("No hardware")

    mgr = InstrumentManager()
    mgr.register_backend(Fake(path))
    result = mgr.full_scan()
    assert len(result) == 1
    assert result[0].label == "MOCK::SERIAL"
    assert DeviceTable(path).get("ASRL1::INSTR")["label"] == "MOCK::SERIAL"
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

    mgr = InstrumentManager()
    mgr.register_backend(Fake())
    result = mgr.discover()
    assert len(result) == 1
    assert mgr._persistent_store.get("USB0::dev::INSTR")["label"] == "VENDOR::X"
    assert mgr._device_table.get("USB0::dev::INSTR") is None
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

    mgr = InstrumentManager()
    mgr.register_backend(Fake())
    result = mgr.full_scan()
    assert len(result) == 2
    assert mgr._persistent_store.get("USB0::dev::INSTR")["label"] == "VENDOR::X"
    assert mgr._persistent_store.get("ASRL1::INSTR") is None
    assert mgr._device_table.get("ASRL1::INSTR")["label"] == "VENDOR::X"
    assert mgr._device_table.get("USB0::dev::INSTR") is None
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

    DeviceTable(os.environ["INSTY_DEVICE_STORE"]).set(
        "USB0::1::INSTR", "KEITHLEY::DMM6500", serial_baud=None
    )

    mgr = InstrumentManager()
    mgr.register_backend(Fake())
    result = mgr.full_scan()
    assert len(result) == 2
    assert mgr._persistent_store.get("USB0::1::INSTR")["label"] == "KEITHLEY::DMM6500"
    assert mgr._persistent_store.get("USB0::2::INSTR")["label"] == "KEITHLEY::DMM6500"
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

    mgr = InstrumentManager()
    mgr.register_backend(Fake())
    mgr._device_table.set("ASRL3::INSTR", "KEITHLEY::DMM6500", serial_baud=115200)
    result = mgr.full_scan()
    assert len(result) == 1
    assert mgr._device_table.get("ASRL3::INSTR") is None
    assert mgr._device_table.get("ASRL5::INSTR")["label"] == "KEITHLEY::DMM6500"
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

    DeviceTable(os.environ["INSTY_DEVICE_STORE"]).set(
        "USB0::1::INSTR", "KEITHLEY::DMM6500", serial_baud=None
    )

    mgr = InstrumentManager()
    mgr.register_backend(Fake())
    info = mgr.resolve("USB0::1::INSTR")
    assert info is not None
    assert info.label == "KEITHLEY::DMM6500"
    assert mgr._device_table.get("USB0::1::INSTR") is None
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

    mgr = InstrumentManager()
    mgr.register_backend(Fake())
    info = mgr.resolve("ASRL1::INSTR")
    assert info is not None
    assert info.label == "MOCK::SERIAL"
    assert mgr._device_table.get("ASRL1::INSTR")["label"] == "MOCK::SERIAL"
    assert mgr._persistent_store.get("ASRL1::INSTR") is None
    mgr.shutdown()


def test_manager_finds_usb_from_persistent_store(monkeypatch):
    """InstrumentManager 不带 device_table 时，也能从持久存储发现 USB 设备"""
    from unittest.mock import MagicMock

    import pyvisa

    mock_rm = MagicMock()
    mock_rm.list_resources.return_value = ["USB0::1::INSTR"]
    monkeypatch.setattr(pyvisa, "ResourceManager", lambda: mock_rm)

    DeviceTable(os.environ["INSTY_DEVICE_STORE"]).set(
        "USB0::1::INSTR",
        "KEITHLEY::DMM6500",
        serial_baud=None,
        inst_type="dmm",
        supported=["VOLTAGE_DC"],
    )

    mgr = InstrumentManager()
    infos = mgr.refresh()
    assert any(i.address == "USB0::1::INSTR" for i in infos)
    mgr.shutdown()


def test_default_persistent_store_path(monkeypatch):
    """persistent_store 默认路径：环境变量优先，否则 ~/.insty/known_devices.json"""
    tmp = tempfile.mkdtemp()
    env_path = os.path.join(tmp, "store.json")
    monkeypatch.setenv("INSTY_DEVICE_STORE", env_path)
    mgr = InstrumentManager()
    assert mgr._persistent_store.path == env_path
    mgr.shutdown()

    monkeypatch.delenv("INSTY_DEVICE_STORE")
    mgr2 = InstrumentManager()
    assert mgr2._persistent_store.path == os.path.join(
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

    mgr = InstrumentManager()
    mgr.register_backend(MockBackend())
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

    mgr = InstrumentManager()
    mgr.register_backend(BackendA())
    mgr.register_backend(BackendB())
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
            class FakeInst(Instrument):
                def get(self, *args, **kwargs): return None
                def set(self, *args, **kwargs): return 0
                def stop(self): return 0
                def _close(self): return 0
                def beep(self): return None
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
            class FakeInst(Instrument):
                def get(self, *args, **kwargs): return None
                def set(self, *args, **kwargs): return 0
                def stop(self): return 0
                def _close(self): return 0
                def beep(self): return None
            return FakeInst()

    mgr = InstrumentManager()
    mgr.register_backend(BackendA())
    mgr.register_backend(BackendB())

    inst_a = mgr.open("port_a", "VENDOR::A")
    assert opened_by["port_a"] == "A"
    assert inst_a is mgr.open("port_a", "VENDOR::A")

    mgr.open("port_b", "VENDOR::B")
    assert opened_by["port_b"] == "B"

    mgr.close("port_a")
    mgr.close("port_b")
    mgr.shutdown()


def test_manager_reopen_after_inst_close():
    """实例 close() 后缓存失效，再次 open 会建立新连接而非复用已关闭实例"""
    class ReopenBackend(TransportBackend):
        def __init__(self):
            super().__init__()
            self.opened = 0

        def _enum(self) -> list[str]:
            return ["dev"]

        def _identify(self, address: str) -> InstrumentInfo | None:
            return make_info("dev", "VENDOR::OK") if address == "dev" else None

        def open(self, address, label, timeout=30000):
            self.opened += 1

            class FakeInst(Instrument):
                def __init__(self):
                    self.visa_inst = object()

                def _close(self):
                    self.visa_inst = None

                def beep(self):
                    pass

            return FakeInst()

    mgr = InstrumentManager()
    backend = ReopenBackend()
    mgr.register_backend(backend)

    inst1 = mgr.open("dev", "VENDOR::OK")
    assert backend.opened == 1
    # 未关闭：命中缓存复用同一实例
    assert mgr.open("dev", "VENDOR::OK") is inst1
    assert backend.opened == 1
    # 实例 close() 后：重新打开，建立新连接
    inst1.close()
    inst2 = mgr.open("dev", "VENDOR::OK")
    assert backend.opened == 2
    assert inst2 is not inst1

    mgr.close("dev")
    mgr.shutdown()


def test_register_backend():
    class ExtraBackend(TransportBackend):
        def _enum(self) -> list[str]:
            return ["extra"]
        def _identify(self, address: str) -> InstrumentInfo | None:
            return make_info("extra", "EXTRA::DEVICE") if address == "extra" else None
        def open(self, address: str, label: str, timeout: int = 30000):
            raise RuntimeError("No hardware")

    mgr = InstrumentManager()
    assert len(mgr.backends) == 1

    mgr.register_backend(ExtraBackend())
    assert len(mgr.backends) == 2

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

    mgr = InstrumentManager()
    mgr.register_backend(BackendA())
    mgr.register_backend(BackendB())
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
            class FakeInst(Instrument):
                def get(self, *args, **kwargs): return None
                def set(self, *args, **kwargs): return 0
                def stop(self): return 0
                def _close(self): return 0
                def beep(self): return None
            return FakeInst()

    mgr = InstrumentManager()
    mgr.register_backend(BadBackend())
    mgr.register_backend(GoodBackend())
    inst = mgr.open("dev", "VENDOR::OK")
    assert inst is not None
    mgr.close("dev")
    mgr.shutdown()


# ── 按类别访问接口 ─────────────────────────────────────────

def make_mock_backend(infos):
    """构造按给定 InstrumentInfo 列表识别的 mock 后端，open 返回通用假仪器"""
    class FakeInst(
        DMM,
        PowerSupply,
        ThermalChamber,
        WaveformGenerator,
        Oscilloscope,
    ):
        def set_voltage(self, volt, channel=1): return self
        def output_enable(self, channel=0): return self
        def output_disable(self, channel=0): return self
        def read_voltage(self, params=None): return 3.3
        def read_current(self, params=None): return 0.1
        def get_run_state(self): return "RUN"
        def execute(self, mode): return self
        def read_frequency(self, channel=1): return 1000.0
        def read_duty_cycle(self, channel=1): return 0.5
        def read_pulse(self, channel=1): return 0.01
        def read_image(self): return b""
        def screenshot(self): return b""
        def set_temperature(self, temp, soak=15): pass
        def get_temperature(self): return -40.0
        def setup(self): return self
        def wait(self, timeout=150): return True
        def ready(self): return True
        def get_errors(self): return []
        def _close(self): pass
        def beep(self): pass

    class MockBackend(TransportBackend):
        def __init__(self, infos):
            super().__init__()
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

    return MockBackend(infos)


def test_get_dmm_by_category():
    """get_dmm 按类别自动匹配，返回 DMM 实例并注入 info"""
    infos = [make_info("dmm_addr", "KEITHLEY::DMM6500",
                       InstrumentType.DMM, ("VOLTAGE_DC", "CURRENT_DC"))]
    mgr = InstrumentManager()
    mgr.register_backend(make_mock_backend(infos))
    try:
        inst = mgr.get_dmm()
        assert isinstance(inst, DMM)
        assert inst.info.address == "dmm_addr"
        assert inst.info.label == "KEITHLEY::DMM6500"
        assert inst.read_voltage() == 3.3
        assert inst.read_current() == 0.1
    finally:
        mgr.shutdown()


def test_get_power_supply_chain():
    """get_power_supply 返回 PowerSupply 实例，支持链式调用"""
    infos = [make_info("ps_addr", "ITECH::IT6302",
                       InstrumentType.POWER_SUPPLY, ("VOLTAGE",))]
    mgr = InstrumentManager()
    mgr.register_backend(make_mock_backend(infos))
    try:
        ps = mgr.get_power_supply()
        assert isinstance(ps, PowerSupply)
        assert ps.set_voltage(3.3).output_enable() is ps
    finally:
        mgr.shutdown()


def test_get_by_address():
    """指定 address 时按地址匹配并校验能力"""
    infos = [
        make_info("dmm_a", "KEITHLEY::DMM6500",
                  InstrumentType.DMM, ("VOLTAGE_DC",)),
        make_info("dmm_b", "AGILENT::34461A",
                  InstrumentType.DMM, ("VOLTAGE_DC",)),
    ]
    mgr = InstrumentManager()
    mgr.register_backend(make_mock_backend(infos))
    try:
        inst = mgr.get_dmm(address="dmm_b")
        assert isinstance(inst, DMM)
        assert inst.info.address == "dmm_b"
        assert mgr.get_dmm(address="dmm_a").info.address == "dmm_a"
    finally:
        mgr.shutdown()


def test_get_multiple_conflicts():
    """未指定 address 且存在多台同类别仪器时要求指定地址"""
    infos = [
        make_info("dmm_a", "KEITHLEY::DMM6500",
                  InstrumentType.DMM, ("VOLTAGE_DC",)),
        make_info("dmm_b", "AGILENT::34461A",
                  InstrumentType.DMM, ("VOLTAGE_DC",)),
    ]
    mgr = InstrumentManager()
    mgr.register_backend(make_mock_backend(infos))
    try:
        with pytest.raises(RuntimeError, match="找到多台"):
            mgr.get_dmm()
    finally:
        mgr.shutdown()


def test_get_unsupported_address():
    """指定地址的仪器不支持所需能力时报错"""
    infos = [make_info("ps_addr", "ITECH::IT6302",
                       InstrumentType.POWER_SUPPLY, ("VOLTAGE",))]
    mgr = InstrumentManager()
    mgr.register_backend(make_mock_backend(infos))
    try:
        with pytest.raises(RuntimeError, match="不支持"):
            mgr.get_dmm(address="ps_addr")
    finally:
        mgr.shutdown()


def test_get_no_match():
    """在线列表无匹配仪器时自动重试一次后报错"""
    infos = [make_info("dmm_addr", "KEITHLEY::DMM6500",
                       InstrumentType.DMM, ("VOLTAGE_DC",))]
    mgr = InstrumentManager()
    mgr.register_backend(make_mock_backend(infos))
    try:
        with pytest.raises(RuntimeError, match="未找到可用"):
            mgr.get_power_supply()
    finally:
        mgr.shutdown()


def test_get_reuses_open_connection():
    """同一地址重复获取时复用管理器已打开的连接"""
    infos = [make_info("dmm_addr", "KEITHLEY::DMM6500",
                       InstrumentType.DMM, ("VOLTAGE_DC",))]
    backend = make_mock_backend(infos)
    mgr = InstrumentManager()
    mgr.register_backend(backend)
    try:
        r1 = mgr.get_dmm()
        r2 = mgr.get_dmm()
        assert r1 is r2
        assert backend.opened == ["dmm_addr"]
    finally:
        mgr.shutdown()


def test_manager_context_manager():
    """InstrumentManager 支持 with 语法，退出时自动关闭全部连接"""
    infos = [make_info("dmm_addr", "KEITHLEY::DMM6500",
                       InstrumentType.DMM, ("VOLTAGE_DC",))]
    with InstrumentManager() as mgr:
        mgr.register_backend(make_mock_backend(infos))
        inst = mgr.get_dmm()
        assert isinstance(inst, DMM)
        assert inst.read_voltage() == 3.3


def test_manager_refresh_and_full_scan_cache():
    """refresh/full_scan 均更新按类别匹配用的在线缓存"""
    infos = [make_info("dmm_addr", "KEITHLEY::DMM6500",
                       InstrumentType.DMM, ("VOLTAGE_DC",))]
    backend = make_mock_backend(infos)
    mgr = InstrumentManager()
    mgr.register_backend(backend)
    try:
        assert [i.address for i in mgr.refresh()] == ["dmm_addr"]
        assert mgr._infos is not None
        assert [i.address for i in mgr.full_scan()] == ["dmm_addr"]
        assert mgr._infos is not None
    finally:
        mgr.shutdown()
