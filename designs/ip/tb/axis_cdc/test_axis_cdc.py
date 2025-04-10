import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles
from cocotbext.axi import (AxiStreamBus, AxiStreamFrame,
                           AxiStreamSource, AxiStreamSink)
import logging
import itertools


class TB:
    def __init__(self, dut):
        dut._log.setLevel(logging.INFO)
        self.dut = dut
        self.source = AxiStreamSource(
            AxiStreamBus.from_prefix(dut, "s_axis"),
            dut.s_axis_aclk, dut.s_axis_aresetn, reset_active_level=False)
        self.sink = AxiStreamSink(
            AxiStreamBus.from_prefix(dut, "m_axis"),
            dut.m_axis_aclk, dut.m_axis_aresetn, reset_active_level=False)

        cocotb.start_soon(Clock(dut.s_axis_aclk, 4, units="ns").start())
        cocotb.start_soon(Clock(dut.m_axis_aclk, 2, units="ns").start())

    async def cycle_reset_s(self):
        self.dut.s_axis_aresetn.setimmediatevalue(1)
        await ClockCycles(self.dut.s_axis_aclk, 2)
        self.dut.s_axis_aresetn.value = 0
        await RisingEdge(self.dut.s_axis_aclk)
        self.dut.s_axis_aresetn.value = 1
        await RisingEdge(self.dut.s_axis_aclk)

    async def cycle_reset_m(self):
        self.dut.m_axis_aresetn.setimmediatevalue(1)
        await ClockCycles(self.dut.m_axis_aclk, 2)
        self.dut.m_axis_aresetn.value = 0
        await RisingEdge(self.dut.m_axis_aclk)
        self.dut.m_axis_aresetn.value = 1
        await RisingEdge(self.dut.m_axis_aclk)


def gen_payload(length):
    return bytearray(itertools.islice(itertools.cycle(range(256)), length))

@cocotb.test(timeout_time=1, timeout_unit='us')
async def test_axis_cdc(dut, length=8, DATA_WIDTH=256):
    tb = TB(dut)
    await tb.cycle_reset_s()
    await tb.cycle_reset_m()

    test_data = gen_payload(DATA_WIDTH // 8)
    test_frames = [AxiStreamFrame(test_data) for _ in range(length)]

    for frame in test_frames:
        await tb.source.send(frame)

    for frame in test_frames:
        rx_frame = await tb.sink.recv()
        assert rx_frame.tdata == frame.tdata, "Data mismatch"
    assert tb.sink.empty()
