"""axis_idle_zero: valid beats pass through (one cycle later), cycles without a valid beat become zero words."""

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge


async def setup(dut):
    cocotb.start_soon(Clock(dut.aclk, 2, unit="ns").start())
    dut.aresetn.value = 0
    dut.s_axis_tvalid.value = 0
    dut.s_axis_tdata.value = 0
    dut.m_axis_tready.value = 1
    await ClockCycles(dut.aclk, 3)
    dut.aresetn.value = 1
    await RisingEdge(dut.aclk)


@cocotb.test()
async def test_gaps_become_zero(dut):
    """Random valid/gap pattern: output = input word if valid else 0, one cycle later; tvalid always high."""
    await setup(dut)
    width = len(dut.s_axis_tdata)
    rng = random.Random(1)
    expected = []
    for _ in range(300):
        valid = rng.random() < 0.6
        data = rng.getrandbits(width) | 1  # never zero, so a gap is distinguishable
        dut.s_axis_tvalid.value = int(valid)
        dut.s_axis_tdata.value = data
        await RisingEdge(dut.aclk)
        expected.append(data if valid else 0)
        if len(expected) > 1:
            assert dut.m_axis_tvalid.value == 1, "tvalid low"
            got = int(dut.m_axis_tdata.value)
            assert got == expected[-2], f"cycle {len(expected)}: got {got:#x}, expected {expected[-2]:#x}"
        assert dut.s_axis_tready.value == 1


@cocotb.test()
async def test_idle_after_burst_is_zero(dut):
    """After a burst the output returns to zero and stays there (the DAC does not hold the last word)."""
    await setup(dut)
    dut.s_axis_tvalid.value = 1
    dut.s_axis_tdata.value = 0x1234
    await RisingEdge(dut.aclk)
    dut.s_axis_tvalid.value = 0
    await RisingEdge(dut.aclk)
    for _ in range(20):
        await RisingEdge(dut.aclk)
        assert int(dut.m_axis_tdata.value) == 0, "non-zero after the burst"


@cocotb.test()
async def test_ready_passthrough(dut):
    """s_axis_tready follows m_axis_tready, and the output holds while the DAC is not ready."""
    await setup(dut)
    dut.s_axis_tvalid.value = 1
    dut.s_axis_tdata.value = 0xABC
    await RisingEdge(dut.aclk)
    dut.m_axis_tready.value = 0
    dut.s_axis_tdata.value = 0xDEF
    await RisingEdge(dut.aclk)
    await RisingEdge(dut.aclk)
    assert dut.s_axis_tready.value == 0
    assert int(dut.m_axis_tdata.value) == 0xABC, "output changed while not ready"
    dut.m_axis_tready.value = 1
    await RisingEdge(dut.aclk)
    await RisingEdge(dut.aclk)
    assert int(dut.m_axis_tdata.value) == 0xDEF
