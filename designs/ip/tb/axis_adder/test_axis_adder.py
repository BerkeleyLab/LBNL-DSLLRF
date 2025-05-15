import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles
from cocotbext.axi import AxiStreamBus, AxiStreamSource, AxiStreamSink
import logging
import itertools
import numpy as np


class TB:
    def __init__(self, dut):
        dut._log.setLevel(logging.WARNING)
        self.dut = dut
        self.source0 = AxiStreamSource(
            AxiStreamBus.from_prefix(dut, "s0_axis"),
            dut.axis_aclk, dut.axis_aresetn, reset_active_level=False)
        self.source1 = AxiStreamSource(
            AxiStreamBus.from_prefix(dut, "s1_axis"),
            dut.axis_aclk, dut.axis_aresetn, reset_active_level=False)

        self.sink = AxiStreamSink(
            AxiStreamBus.from_prefix(dut, "m_axis"),
            dut.axis_aclk, dut.axis_aresetn, reset_active_level=False)

        cocotb.start_soon(Clock(dut.axis_aclk, 4, units="ns").start())

    async def cycle_reset(self):
        self.dut.axis_aresetn.setimmediatevalue(1)
        await ClockCycles(self.dut.axis_aclk, 2)
        self.dut.axis_aresetn.value = 0
        await RisingEdge(self.dut.axis_aclk)
        self.dut.axis_aresetn.value = 1
        await RisingEdge(self.dut.axis_aclk)


def gen_payload(length):
    return bytearray(itertools.islice(itertools.cycle(range(256)), length))


@cocotb.test(timeout_time=1, timeout_unit='us')
async def test_axis_adder(dut, length=8, DATA_WIDTH=256):
    tb = TB(dut)
    await tb.cycle_reset()

    test_data = gen_payload(DATA_WIDTH // 8)
    test_frames = [test_data for _ in range(length)]

    for frame in test_frames:
        await tb.source0.write(frame)
        await tb.source1.write(frame)

    for frame in test_frames:
        rx_frame = await tb.sink.read()
        tx_arr = np.frombuffer(bytes(frame), dtype=np.uint16)
        rx_arr = np.frombuffer(bytes(rx_frame), dtype=np.uint16)
        for t_val, r_val in zip(tx_arr, rx_arr):
            tb.dut._log.warning(f"t_val: {hex(t_val)}, r_val: {hex(r_val)}")
            assert r_val == 2 * t_val, \
                f"Data mismatch: {hex(t_val)} != {hex(r_val)}"
    assert tb.sink.empty()
