from pathlib import Path
import json
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles
from cocotbext.axi import (AxiStreamBus, AxiStreamFrame,
                           AxiLiteBus, AxiLiteMaster,
                           AxiStreamSource, AxiStreamSink)
import logging
import itertools
import numpy as np

CORDIC_GAIN = 1.646760258


class TB:
    def __init__(self, dut):
        dut._log.setLevel(logging.INFO)
        self.dut = dut
        ip_path = Path(__file__).resolve().parent.parent.parent
        json_path = ip_path / 'rtl' / 'axil_rf_control.json'
        with open(json_path, 'r') as f:
            self.registers = json.load(f)

        self.source0 = AxiStreamSource(
            AxiStreamBus.from_prefix(dut, "s0_axis"),
            dut.clk, dut.s_axi_aresetn, reset_active_level=False)
        self.source1 = AxiStreamSource(
            AxiStreamBus.from_prefix(dut, "s1_axis"),
            dut.clk, dut.s_axi_aresetn, reset_active_level=False)

        self.sink = AxiStreamSink(
            AxiStreamBus.from_prefix(dut, "m_axis"),
            dut.clk, dut.s_axi_aresetn, reset_active_level=False)

        self.axil_master = AxiLiteMaster(
            AxiLiteBus.from_prefix(dut, "s_axi"),
            dut.clk, dut.s_axi_aresetn, reset_active_level=False)

        cocotb.start_soon(Clock(dut.clk, 4, units="ns").start())

        self.dut.rf_permit_in.value = 1
        self.dut.ext_trigger_in.value = 0
        self.dut.evr_trigger_in.value = 0

    async def cycle_reset(self):
        self.dut.s_axi_aresetn.setimmediatevalue(1)
        await ClockCycles(self.dut.clk, 2)
        self.dut.s_axi_aresetn.value = 0
        await RisingEdge(self.dut.clk)
        self.dut.s_axi_aresetn.value = 1
        await RisingEdge(self.dut.clk)

    async def write_register(self, register, value):
        await self.axil_master.write(
            self.registers[register]['address_offset'],
            value.to_bytes(4, 'little'))

    async def read_register(self, register):
        addr = self.registers[register]['address_offset']
        data = await self.axil_master.read(addr, 4)
        return int.from_bytes(data.data, 'little')

    async def init_llrf(self, amp_setp=10000, phs_setp=0):
        regs_dict = {
            'trig_sel': 0,
            'trig_period': 20,
            'trig_divide': 1,
            'pulse_length': 8,
            'dac_enable': 1,
            'amp_loop_enable': 0,
            'amp_loop_reset': 0,
            'amp_loop_setpoint': amp_setp,
            'amp_loop_kp': 2,
            'amp_loop_ki': 0,
            'phs_loop_enable': 0,
            'phs_loop_reset': 0,
            'phs_loop_kp': 2,
            'phs_loop_ki': 0,
            'phs_loop_setpoint': phs_setp,
        }
        for reg, val in regs_dict.items():
            await self.write_register(reg, val)

    async def read_m_axis(self):
        rx_frame = await self.sink.recv()
        return np.frombuffer(rx_frame.tdata, dtype=np.int16)


def gen_payload(length):
    return bytearray(itertools.islice(itertools.cycle(range(256)), length))


@cocotb.test(timeout_time=1, timeout_unit='us')
async def test(dut, length=1, DATA_WIDTH=256):
    tb = TB(dut)
    await tb.cycle_reset()
    amp_setp = 10000
    await tb.init_llrf(amp_setp=amp_setp)

    test_data = gen_payload(DATA_WIDTH // 8)
    test_frames = [AxiStreamFrame(test_data) for _ in range(length)]

    for frame in test_frames:
        await tb.source0.send(frame)
        await tb.source1.send(frame)

    # wait for cordic
    for _ in range(22):
        await RisingEdge(dut.clk)

    # flush sink
    while not tb.sink.empty():
        await tb.sink.recv()

    rx_expect = np.round(
        np.array([CORDIC_GAIN * amp_setp / 4] * 16)).astype(np.int16)
    rx_expect[1::2] = 0  # I part is zero
    for _ in range(length):
        rx_arr = await tb.read_m_axis()
        assert np.allclose(rx_arr, rx_expect), \
            f"Data mismatch: {rx_arr} != {rx_expect}"
    assert tb.sink.empty()
