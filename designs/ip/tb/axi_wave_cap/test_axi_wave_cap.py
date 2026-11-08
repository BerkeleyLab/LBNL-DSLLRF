"""
Testbench for axi_wave_cap: a stream of ROW_WIDTH-bit rows is captured on trigger and read back over AXI4.

Every int16 sample of the stream carries its own index (valid beats only), so a read-back shows exactly which beats
were captured: they must be consecutive, start right after the trigger and fill rows 0 .. n_rows-1.
"""

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, with_timeout
from cocotbext.axi import AxiBus, AxiMaster


class AxiWaveCapTB:
    def __init__(self, dut):
        self.dut = dut
        self.log = dut._log
        self.row_width = int(dut.ROW_WIDTH.value)
        self.depth = int(dut.DEPTH.value)
        self.spr = self.row_width // 16  # samples per row
        self.row_bytes = self.row_width // 8
        self.beat = 0  # index of the next valid beat on the stream
        self.p_gap = 0.0
        self.rng = random.Random(1)
        cocotb.start_soon(Clock(dut.axis_clk, 4, unit="ns").start())
        self.axi = AxiMaster(AxiBus.from_prefix(dut, "s_axi"), dut.axis_clk, dut.axis_aresetn, reset_active_level=False)
        self.trigger_beat = None

    def row_value(self, beat):
        value = 0
        for s in range(self.spr):
            value |= ((beat * self.spr + s) & 0xFFFF) << (16 * s)
        return value

    async def stream(self):
        """Drive one row per clock (or a gap with probability p_gap); count valid beats."""
        while True:
            valid = self.rng.random() >= self.p_gap
            self.dut.s_axis_tvalid.value = int(valid)
            self.dut.s_axis_tdata.value = self.row_value(self.beat)
            await RisingEdge(self.dut.axis_clk)
            if valid:
                self.beat += 1

    async def reset(self):
        self.dut.axis_aresetn.value = 0
        self.dut.trigger.value = 0
        self.dut.n_rows.value = 0
        self.dut.s_axis_tvalid.value = 0
        await ClockCycles(self.dut.axis_clk, 10)
        self.dut.axis_aresetn.value = 1
        await ClockCycles(self.dut.axis_clk, 5)
        cocotb.start_soon(self.stream())
        await ClockCycles(self.dut.axis_clk, 20)

    async def capture(self, n_rows, timeout_us=50):
        """Pulse the trigger and wait for write_done; returns the first beat index after the trigger."""
        self.dut.n_rows.value = n_rows
        self.dut.trigger.value = 1
        await RisingEdge(self.dut.axis_clk)
        first = self.beat
        self.dut.trigger.value = 0

        async def done():
            while True:
                await RisingEdge(self.dut.axis_clk)
                if self.dut.write_done.value == 1:
                    return

        await with_timeout(done(), timeout_us, "us")
        return first

    def expected_bytes(self, first_beat, n_rows):
        return b"".join(self.row_value(first_beat + r).to_bytes(self.row_bytes, "little") for r in range(n_rows))

    def captured_start(self, data):
        """Beat index of row 0, from its first sample."""
        return int.from_bytes(data[0:2], "little") // self.spr


async def check_capture(tb, n_rows, p_gap=0.0, rows_expected=None):
    tb.p_gap = p_gap
    first = await tb.capture(n_rows)
    rows = rows_expected if rows_expected is not None else n_rows
    data = bytes((await tb.axi.read(0, rows * tb.row_bytes)).data)
    start = tb.captured_start(data)
    # Sample indices stay below 2**16 in these tests (< 3276 beats after reset). The capture must start on the first
    # beats after the trigger.
    assert start - first in range(0, 3), f"capture started at beat {start}, trigger at beat {first}"
    assert data == tb.expected_bytes(start, rows), "captured rows are not consecutive beats"
    return start - first


@cocotb.test(timeout_time=200, timeout_unit="us")
async def test_capture_full_rate(dut):
    """Continuous stream (one row per clock, as from the RFDC): 100 consecutive rows from right after the trigger."""
    tb = AxiWaveCapTB(dut)
    await tb.reset()
    lag = await check_capture(tb, 100)
    tb.log.info(f"first captured beat = trigger beat + {lag}")


@cocotb.test(timeout_time=400, timeout_unit="us")
async def test_capture_with_gaps(dut):
    """Gaps in tvalid do not leave holes: the rows are the next n_rows *valid* beats."""
    tb = AxiWaveCapTB(dut)
    await tb.reset()
    await check_capture(tb, 300, p_gap=0.3)


@cocotb.test(timeout_time=2000, timeout_unit="us")
async def test_full_depth_and_clamp(dut):
    """n_rows larger than DEPTH captures exactly DEPTH rows, with one write_done."""
    tb = AxiWaveCapTB(dut)
    await tb.reset()
    await check_capture(tb, tb.depth + 100, rows_expected=tb.depth)


@cocotb.test(timeout_time=200, timeout_unit="us")
async def test_retrigger_ignored_while_capturing(dut):
    """A trigger during a capture neither restarts it nor shifts the rows."""
    tb = AxiWaveCapTB(dut)
    await tb.reset()
    tb.dut.n_rows.value = 200
    tb.dut.trigger.value = 1
    await RisingEdge(tb.dut.axis_clk)
    first = tb.beat
    tb.dut.trigger.value = 0
    await ClockCycles(tb.dut.axis_clk, 50)
    tb.dut.trigger.value = 1  # mid-capture
    await RisingEdge(tb.dut.axis_clk)
    tb.dut.trigger.value = 0
    n_done = 0
    for _ in range(400):
        await RisingEdge(tb.dut.axis_clk)
        n_done += int(tb.dut.write_done.value)
    assert n_done == 1, f"write_done pulsed {n_done} times"
    data = bytes((await tb.axi.read(0, 200 * tb.row_bytes)).data)
    start = tb.captured_start(data)
    assert start - first in range(0, 3), f"capture restarted: start {start}, first trigger at {first}"
    assert data == tb.expected_bytes(start, 200)


@cocotb.test(timeout_time=200, timeout_unit="us")
async def test_n_rows_zero_ignored(dut):
    """n_rows = 0 ignores the trigger (no write_done)."""
    tb = AxiWaveCapTB(dut)
    await tb.reset()
    tb.dut.n_rows.value = 0
    tb.dut.trigger.value = 1
    await RisingEdge(tb.dut.axis_clk)
    tb.dut.trigger.value = 0
    for _ in range(100):
        await RisingEdge(tb.dut.axis_clk)
        assert tb.dut.write_done.value == 0


@cocotb.test(timeout_time=400, timeout_unit="us")
async def test_narrow_and_random_reads(dut):
    """CPU-style reads (2..16 bytes, random addresses) return the captured samples at their byte offsets."""
    tb = AxiWaveCapTB(dut)
    await tb.reset()
    n_rows = 64
    first = await tb.capture(n_rows)
    full = bytes((await tb.axi.read(0, n_rows * tb.row_bytes)).data)
    start = tb.captured_start(full)
    assert start - first in range(0, 3)
    expected = tb.expected_bytes(start, n_rows)
    rng = random.Random(9)
    for _ in range(200):
        size = rng.choice((1, 2, 3, 4))
        nbytes = 1 << size
        addr = rng.randrange(0, len(expected) - nbytes + 1) & ~(nbytes - 1)
        got = bytes((await tb.axi.read(addr, nbytes, size=size)).data)
        assert got == expected[addr : addr + nbytes], f"read of {nbytes} B at {addr} differs"


CSR = (1 << 17) - 32  # last beat of the default 128 KiB window


async def csr_read(tb):
    return int.from_bytes(bytes((await tb.axi.read(CSR, 4, size=2)).data), "little")


async def csr_write(tb, value):
    await tb.axi.write(CSR, value.to_bytes(4, "little"), size=2)


@cocotb.test(timeout_time=400, timeout_unit="us")
async def test_oneshot_arm(dut):
    """One-shot mode: no capture until armed, exactly one capture per arm, done/armed/count in the CSR."""
    tb = AxiWaveCapTB(dut)
    await tb.reset()
    tb.dut.n_rows.value = 50

    async def pulse_trigger_and_count_done(cycles=200):
        tb.dut.trigger.value = 1
        await RisingEdge(tb.dut.axis_clk)
        first = tb.beat
        tb.dut.trigger.value = 0
        n = 0
        for _ in range(cycles):
            await RisingEdge(tb.dut.axis_clk)
            n += int(tb.dut.write_done.value)
        return n, first

    assert await csr_read(tb) == 0, "reset state: continuous mode, not armed, not done, count 0"
    await csr_write(tb, 0x1)  # oneshot, not armed
    assert await csr_read(tb) == 0x1
    n, _ = await pulse_trigger_and_count_done()
    assert n == 0, "captured without being armed"

    await csr_write(tb, 0x3)  # oneshot + arm
    assert await csr_read(tb) == 0x3, "armed bit not set"
    n, first = await pulse_trigger_and_count_done()
    assert n == 1, f"write_done pulsed {n} times"
    status = await csr_read(tb)
    assert status == (1 << 16) | 0x4 | 0x1, f"status 0x{status:08x}: expected count 1, done, oneshot"
    data = bytes((await tb.axi.read(0, 50 * tb.row_bytes)).data)
    start = tb.captured_start(data)
    assert start - first in range(0, 3) and data == tb.expected_bytes(start, 50)

    n, _ = await pulse_trigger_and_count_done()  # not re-armed: buffer must stay
    assert n == 0, "captured again without re-arming"
    assert bytes((await tb.axi.read(0, 50 * tb.row_bytes)).data) == data, "buffer overwritten"

    await csr_write(tb, 0x0)  # back to continuous
    n, _ = await pulse_trigger_and_count_done()
    assert n == 1 and (await csr_read(tb)) >> 16 == 2, "continuous mode capture not counted"
