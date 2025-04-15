import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles
from cocotbext.axi import (AxiStreamBus, AxiStreamFrame,
                           AxiStreamSource, AxiStreamSink)
import logging
import itertools
import numpy as np

CORDIC_GAIN = 1.646760258


class TB:
    def __init__(self, dut):
        dut._log.setLevel(logging.INFO)
        self.dut = dut
        self.source0 = AxiStreamSource(
            AxiStreamBus.from_prefix(dut, "s0_axis"),
            dut.clk, dut.axis_aresetn, reset_active_level=False)
        self.source1 = AxiStreamSource(
            AxiStreamBus.from_prefix(dut, "s1_axis"),
            dut.clk, dut.axis_aresetn, reset_active_level=False)

        self.sink = AxiStreamSink(
            AxiStreamBus.from_prefix(dut, "m_axis"),
            dut.clk, dut.axis_aresetn, reset_active_level=False)

        cocotb.start_soon(Clock(dut.clk, 4, units="ns").start())

    async def cycle_reset(self):
        self.dut.axis_aresetn.setimmediatevalue(1)
        self.dut.dsp_reset.setimmediatevalue(0)
        await ClockCycles(self.dut.clk, 2)
        self.dut.axis_aresetn.value = 0
        self.dut.dsp_reset.value = 1
        await RisingEdge(self.dut.clk)
        self.dut.axis_aresetn.value = 1
        self.dut.dsp_reset.value = 0
        await RisingEdge(self.dut.clk)

    async def init_llrf(self, amp_setp=10000, phs_setp=0):
        self.dut.trigger.value = 0
        self.dut.rf_permit.value = 1
        self.dut.pulse_length.value = 32
        self.dut.amp_loop_enable.value = 0
        self.dut.amp_loop_reset.value = 0
        self.dut.amp_loop_setpoint.value = amp_setp
        self.dut.amp_loop_kp.value = 2
        self.dut.amp_loop_ki.value = 0
        self.dut.phs_loop_enable.value = 0
        self.dut.phs_loop_reset.value = 0
        self.dut.phs_loop_setpoint.value = phs_setp
        self.dut.phs_loop_kp.value = 2
        self.dut.phs_loop_ki.value = 0
        await RisingEdge(self.dut.clk)

    async def reset_amp_loop(self):
        for val in [1, 0]:
            self.dut.amp_loop_enable.value = val
            await RisingEdge(self.dut.clk)

    async def reset_phs_loop(self):
        for val in [1, 0]:
            self.dut.phs_loop_enable.value = val
            await RisingEdge(self.dut.clk)


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
        rx_frame = await tb.sink.recv()
        rx_arr = np.frombuffer(rx_frame.tdata, dtype=np.int16)
        assert np.allclose(rx_arr, rx_expect), \
            f"Data mismatch: {rx_arr} != {rx_expect}"
    assert tb.sink.empty()
