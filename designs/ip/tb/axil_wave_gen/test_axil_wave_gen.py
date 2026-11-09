import json
import logging
import math
import random
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, with_timeout
from cocotbext.axi import AxiLiteBus, AxiLiteMaster, AxiStreamBus, AxiStreamSink


class AxilWaveGenTB:
    """Testbench for axil_wave_gen"""

    def __init__(self, dut):
        self.dut = dut
        self.log = dut._log
        self.log.setLevel(logging.INFO)

        # Get parameters (defaults for simulation)
        self.axi_data_width = self._get_param("C_S_AXI_DATA_WIDTH", 32)
        self.axi_addr_width = self._get_param("C_S_AXI_ADDR_WIDTH", 6)
        self.out_data_width = self._get_param("OUT_DATA_WIDTH", 320)
        self.granule = self._get_param("GRANULE", 64)
        self.bank_depth = self._get_param("BANK_DEPTH", 4096)
        self.ram_style = self._get_param("RAM_STYLE", "ultra")

        self.axi_bytes = self.axi_data_width // 8
        self.out_bytes = self.out_data_width // 8
        self.out_granules = self.out_data_width // self.granule
        self.axi_granules = self.axi_data_width // self.granule

        # Load register map from JSON
        ip_path = Path(__file__).resolve().parent.parent.parent
        json_path = ip_path / "rtl" / "axil_wave_gen.json"
        with open(json_path) as f:
            self.registers = json.load(f)

        # Map register names to addresses
        self.ADDR_CTRL = self.registers["ctrl"]["address_offset"]
        self.ADDR_LENGTH = self.registers["wave_length"]["address_offset"]
        self.ADDR_STATUS = self.registers["status"]["address_offset"]
        self.WAVEFORM_BASE_ADDR = self.registers["waveform_data"]["address_offset"]

        self.log.warning("Configuration:")
        self.log.warning(f"  AXI Data Width: {self.axi_data_width} bits")
        self.log.warning(f"  AXI Addr Width: {self.axi_addr_width} bits")
        self.log.warning(f"  Output Width:   {self.out_data_width} bits ({self.out_granules} granules)")
        self.log.warning(f"  Granule:        {self.granule} bits")
        self.log.warning(f"  Bank Depth:     {self.bank_depth}")
        self.log.warning(f"  Ram Style:      {self.ram_style}")

        # Create clock
        self.clock = Clock(dut.s_axi_aclk, 4, unit="ns")
        cocotb.start_soon(self.clock.start())

        # Create AXI-Lite Master
        self.axil_master = AxiLiteMaster(
            AxiLiteBus.from_prefix(dut, "s_axi"), dut.s_axi_aclk, dut.s_axi_aresetn, reset_active_level=False
        )

        # Create AXI-Stream Sink
        self.axis_sink = AxiStreamSink(
            AxiStreamBus.from_prefix(dut, "m_axis"),
            dut.s_axi_aclk,
            dut.s_axi_aresetn,
            reset_active_level=False,
            byte_size=self.out_data_width,
        )

    def _get_param(self, name, default):
        """Get parameter value from DUT or use default"""
        try:
            return int(getattr(self.dut, name).value)
        except (AttributeError, ValueError):
            return default

    async def reset(self):
        """Reset the DUT"""
        self.log.info("Resetting DUT...")

        self.dut.s_axi_aresetn.value = 0
        self.dut.trigger.value = 0
        self.dut.cw_apply.value = 0

        # Clear any pending data in sink
        while not self.axis_sink.empty():
            self.axis_sink.recv_nowait()

        await ClockCycles(self.dut.s_axi_aclk, 20)
        self.dut.s_axi_aresetn.value = 1
        await ClockCycles(self.dut.s_axi_aclk, 20)

        self.log.info("Reset complete")

    async def _wait_not_busy(self, timeout_cycles=1000):
        """Internal wait for not busy with timeout"""
        for _ in range(timeout_cycles):
            await RisingEdge(self.dut.s_axi_aclk)
            status = await self.read_status()
            if (status & 0x1) == 0:  # Bit 0 is busy flag
                return True
        return False

    async def write_register(self, address: int, data: int):
        """Write to a control register via AXI-Lite"""
        self.log.debug(f"Writing 0x{data:08x} to register 0x{address:02x}")
        await self.axil_master.write(address, data.to_bytes(self.axi_bytes, byteorder="little"))

    async def read_register(self, address: int) -> int:
        """Read from a control register via AXI-Lite"""
        data = await self.axil_master.read(address, self.axi_bytes)
        value = int.from_bytes(data, byteorder="little")
        self.log.debug(f"Read 0x{value:08x} from register 0x{address:02x}")
        return value

    async def write_waveform_data(self, data: bytes, address: int = 0):
        """Write waveform data via AXI-Lite"""
        self.log.info(f"Writing {len(data)} bytes to waveform address 0x{address:04x}")

        # Convert to waveform memory address space
        waveform_addr = self.WAVEFORM_BASE_ADDR + address

        # Perform AXI-Lite write
        await self.axil_master.write(waveform_addr, data)

        # Small delay for write to propagate
        await ClockCycles(self.dut.s_axi_aclk, 5)

    async def write_waveform_words(self, words: list, address: int = 0):
        """Write list of integer words as waveform data"""
        data = b""
        for word in words:
            data += word.to_bytes(self.axi_bytes, byteorder="little")

        await self.write_waveform_data(data, address)

    async def wait_idle(self, timeout_cycles=5000):
        """Wait until playback is not running (writes need no flush)"""
        assert await self._wait_not_busy(timeout_cycles), "Timeout waiting for idle"

    async def trigger_waveform(self, length: int):
        """Trigger waveform output"""
        self.log.info(f"Triggering waveform with length {length}")

        # Set length register
        await self.write_register(self.ADDR_LENGTH, length)

        # Write trigger bit to control register
        await self.write_register(self.ADDR_CTRL, 0x1)  # Bit 0 = trigger

    async def set_trigger_mode(self, external: bool):
        """Set trigger mode: 0=internal, 1=external"""
        mode_bit = 0x4 if external else 0x0
        # We read-modify-write if we wanted to be safe, but here we know the bits.
        # However, it's safer to just set the bit since we know the mapping.
        # Current mapping: Bit 0 = trigger (auto-clear), Bit 1 reserved, Bit 2 = trigger_mode
        await self.write_register(self.ADDR_CTRL, mode_bit)
        self.log.info(f"Trigger mode set to {'external' if external else 'internal'}")

    async def pulse_external_trigger(self):
        """Pulse the external trigger port"""
        self.log.info("Pulsing external trigger...")
        await RisingEdge(self.dut.s_axi_aclk)
        self.dut.trigger.value = 1
        await RisingEdge(self.dut.s_axi_aclk)
        self.dut.trigger.value = 0

    async def read_status(self) -> int:
        """Read status register"""
        return await self.read_register(self.ADDR_STATUS)

    async def collect_output(self, num_samples: int):
        """The playback rows of the next frame (up to tlast); any beat before them must be zero."""
        frame = await self.axis_sink.recv()
        data = list(frame.tdata)
        idle, rows = data[: len(data) - num_samples], data[len(data) - num_samples :]
        assert all(x == 0 for x in idle), f"non-zero idle beat before the playback: {[hex(x) for x in idle if x][:4]}"
        self.log.info(f"collected {len(rows)} rows after {len(idle)} idle beats")
        return rows

    def generate_test_pattern(self, num_samples: int, pattern: str = "counter") -> list:
        """Generate test pattern data"""
        samples = []
        mask = (1 << self.out_data_width) - 1

        for i in range(num_samples):
            if pattern == "counter":
                # Each granule contains incrementing value
                sample = 0
                for g in range(self.out_granules):
                    granule_val = (i * self.out_granules + g) & ((1 << self.granule) - 1)
                    sample |= granule_val << (g * self.granule)
                samples.append(sample & mask)

            elif pattern == "walking_one":
                bit_pos = i % self.out_data_width
                samples.append((1 << bit_pos) & mask)

            elif pattern == "random":
                samples.append(random.randint(0, mask))

            elif pattern == "all_ones":
                samples.append(mask)

            elif pattern == "all_zeros":
                samples.append(0)

            elif pattern == "index":
                # Simple incrementing index
                samples.append(i & mask)

            else:
                samples.append(i & mask)

        return samples

    def samples_to_axi_words(self, samples: list) -> list:
        """Convert output samples to AXI input words using gearbox logic"""
        if not samples:
            return []

        # Concatenate all sample bits into one big integer
        total_bits = len(samples) * self.out_data_width
        all_bits = 0
        for i, sample in enumerate(samples):
            all_bits |= (sample & ((1 << self.out_data_width) - 1)) << (i * self.out_data_width)

        # Calculate number of AXI words needed (round up)
        num_axi_words = (total_bits + self.axi_data_width - 1) // self.axi_data_width

        # Extract AXI words
        axi_words = []
        mask = (1 << self.axi_data_width) - 1
        for i in range(num_axi_words):
            word = (all_bits >> (i * self.axi_data_width)) & mask
            axi_words.append(word)

        self.log.debug(f"Converted {len(samples)} samples to {len(axi_words)} AXI words")
        return axi_words

    def verify_samples(self, received: list, expected: list) -> bool:
        """Verify received samples match expected"""
        if len(received) != len(expected):
            self.log.error(f"Sample count mismatch: got {len(received)}, expected {len(expected)}")
            return False

        for i, rx_int in enumerate(received):
            self.log.info(f"  Got {i}:   0x{rx_int:0{self.out_bytes * 2}x}")

        for i, (rx, exp) in enumerate(zip(received, expected, strict=True)):
            # Convert bytes to int for comparison
            if isinstance(rx, bytes):
                rx_int = int.from_bytes(rx, byteorder="little")
            else:
                rx_int = int(rx)
            # Mask to output width
            rx_int &= (1 << self.out_data_width) - 1
            exp &= (1 << self.out_data_width) - 1

            if rx_int != exp:
                self.log.error(f"Sample {i} mismatch:")
                self.log.error(f"  Got:      0x{rx_int:0{self.out_bytes * 2}x}")
                self.log.error(f"  Expected: 0x{exp:0{self.out_bytes * 2}x}")
                self.log.error(f"  XOR:      0x{(rx_int ^ exp):0{self.out_bytes * 2}x}")
                return False

        self.log.info(f"All {len(expected)} samples verified successfully")
        return True


# =============================================================================
# Test Cases
# =============================================================================


@cocotb.test(timeout_time=5, timeout_unit="us")
async def test_basic_write_read(dut):
    """Test basic write and read functionality via AXI-Lite"""
    tb = AxilWaveGenTB(dut)
    await tb.reset()

    # Small number of samples for basic test
    num_samples = 8
    expected_samples = tb.generate_test_pattern(num_samples, "counter")

    # Convert to AXI words
    axi_words = tb.samples_to_axi_words(expected_samples)
    tb.log.warning(f"Test: {len(axi_words)} AXI words -> {num_samples} samples")

    await tb.write_waveform_words(axi_words, address=0)
    await tb.wait_idle()
    await tb.trigger_waveform(num_samples)
    received = await tb.collect_output(num_samples)
    assert tb.verify_samples(received, expected_samples), "Sample verification failed"


@cocotb.test(timeout_time=5, timeout_unit="us")
async def test_register_read_write(dut):
    """Test AXI-Lite register read/write"""
    tb = AxilWaveGenTB(dut)
    await tb.reset()

    # Test writing and reading wave length register
    test_length = 42
    await tb.write_register(tb.ADDR_LENGTH, test_length)
    read_length = await tb.read_register(tb.ADDR_LENGTH)

    assert read_length == test_length, f"Length mismatch: wrote {test_length}, read {read_length}"
    tb.log.info(f"Register read/write test passed: {test_length} == {read_length}")


@cocotb.test(timeout_time=5, timeout_unit="us")
async def test_status_register(dut):
    """Test status register read"""
    tb = AxilWaveGenTB(dut)
    await tb.reset()

    # Status should be not busy after reset
    status = await tb.read_status()
    assert (status & 0x1) == 0, f"Expected not busy, got status 0x{status:08x}"
    tb.log.info(f"Status register test passed: busy bit = {status & 0x1}")


@cocotb.test(timeout_time=5, timeout_unit="us")
async def test_random_data(dut):
    """Test with random data pattern"""
    tb = AxilWaveGenTB(dut)
    await tb.reset()

    random.seed(42)  # Reproducible
    num_samples = 32
    expected_samples = tb.generate_test_pattern(num_samples, "random")
    axi_words = tb.samples_to_axi_words(expected_samples)

    await tb.write_waveform_words(axi_words, address=0)
    await tb.wait_idle()

    await tb.trigger_waveform(num_samples)
    received = await tb.collect_output(num_samples)

    assert tb.verify_samples(received, expected_samples), "Random data test failed"


@cocotb.test(timeout_time=5, timeout_unit="us")
async def test_multiple_triggers(dut):
    """Test multiple trigger sequences"""
    tb = AxilWaveGenTB(dut)
    await tb.reset()

    num_samples = 16
    expected_samples = tb.generate_test_pattern(num_samples, "counter")
    axi_words = tb.samples_to_axi_words(expected_samples)

    # Write once
    await tb.write_waveform_words(axi_words, address=0)
    await tb.wait_idle()

    # Trigger multiple times
    for iteration in range(3):
        tb.log.info(f"=== Trigger iteration {iteration + 1} ===")

        await tb.trigger_waveform(num_samples)
        received = await tb.collect_output(num_samples)

        assert tb.verify_samples(received, expected_samples), f"Iteration {iteration + 1} failed"

        # Wait for idle before next trigger
        await ClockCycles(dut.s_axi_aclk, 20)


@cocotb.test(timeout_time=5, timeout_unit="us")
async def test_partial_length(dut):
    """Test reading partial waveform length"""
    tb = AxilWaveGenTB(dut)
    await tb.reset()

    # Write more samples than we'll read
    num_write_samples = 32
    expected_samples = tb.generate_test_pattern(num_write_samples, "counter")
    axi_words = tb.samples_to_axi_words(expected_samples)

    await tb.write_waveform_words(axi_words, address=0)
    await tb.wait_idle()

    # Read only first 10 samples
    num_read_samples = 10
    await tb.trigger_waveform(num_read_samples)
    received = await tb.collect_output(num_read_samples)

    assert tb.verify_samples(received, expected_samples[:num_read_samples]), "Partial length test failed"


@cocotb.test(timeout_time=5, timeout_unit="us")
async def test_conversion_boundary(dut):
    """Test at gearbox conversion boundary (LCM of widths)"""
    tb = AxilWaveGenTB(dut)
    await tb.reset()

    # Calculate samples per conversion cycle
    gcd = math.gcd(tb.axi_granules, tb.out_granules)
    lcm_granules = (tb.axi_granules * tb.out_granules) // gcd
    samples_per_cycle = lcm_granules // tb.out_granules
    axi_per_cycle = lcm_granules // tb.axi_granules

    tb.log.info(f"Conversion: {axi_per_cycle} AXI words -> {samples_per_cycle} samples")

    # Test exact multiple of conversion cycle
    num_samples = samples_per_cycle * 4
    expected_samples = tb.generate_test_pattern(num_samples, "counter")
    axi_words = tb.samples_to_axi_words(expected_samples)

    await tb.write_waveform_words(axi_words, address=0)
    await tb.wait_idle()

    await tb.trigger_waveform(num_samples)
    received = await tb.collect_output(num_samples)

    assert tb.verify_samples(received, expected_samples), "Conversion boundary test failed"


@cocotb.test(timeout_time=5, timeout_unit="us")
async def test_single_sample(dut):
    """Test single sample write/read"""
    tb = AxilWaveGenTB(dut)
    await tb.reset()

    num_samples = 1
    expected_samples = [0xDEADBEEF & ((1 << tb.out_data_width) - 1)]
    axi_words = tb.samples_to_axi_words(expected_samples)

    await tb.write_waveform_words(axi_words, address=0)
    await tb.wait_idle()

    await tb.trigger_waveform(num_samples)
    received = await tb.collect_output(num_samples)

    assert tb.verify_samples(received, expected_samples), "Single sample test failed"


@cocotb.test(timeout_time=5, timeout_unit="us")
async def test_tlast_assertion(dut):
    """Verify TLAST is asserted correctly"""
    tb = AxilWaveGenTB(dut)
    await tb.reset()

    num_samples = 8
    expected_samples = tb.generate_test_pattern(num_samples, "counter")
    axi_words = tb.samples_to_axi_words(expected_samples)

    await tb.write_waveform_words(axi_words, address=0)
    await tb.wait_idle()

    await tb.trigger_waveform(num_samples)

    # Manually check TLAST
    sample_count = 0
    timeout = 10000

    while sample_count < num_samples and timeout > 0:
        await RisingEdge(dut.s_axi_aclk)
        timeout -= 1

        if play_beat(dut):
            sample_count += 1
            is_last = int(dut.m_axis_tlast.value)

            if sample_count == num_samples:
                assert is_last == 1, f"TLAST not asserted on final sample {sample_count}"
                tb.log.info(f"TLAST correctly asserted on sample {sample_count}")
            else:
                assert is_last == 0, f"TLAST incorrectly asserted on sample {sample_count}"

    assert sample_count == num_samples, f"Only received {sample_count}/{num_samples} samples"
    tb.log.info("TLAST assertion verified")


@cocotb.test(timeout_time=50, timeout_unit="us")
async def test_large_waveform(dut):
    """Test larger waveform"""
    tb = AxilWaveGenTB(dut)
    await tb.reset()

    num_samples = 128
    expected_samples = tb.generate_test_pattern(num_samples, "counter")
    axi_words = tb.samples_to_axi_words(expected_samples)

    await tb.write_waveform_words(axi_words, address=0)
    await tb.wait_idle()

    await tb.trigger_waveform(num_samples)
    received = await tb.collect_output(num_samples)

    assert tb.verify_samples(received, expected_samples), "Large waveform test failed"


@cocotb.test(timeout_time=10, timeout_unit="us")
async def test_external_trigger(dut):
    """Test external trigger functionality"""
    tb = AxilWaveGenTB(dut)
    await tb.reset()

    num_samples = 16
    expected_samples = tb.generate_test_pattern(num_samples, "counter")
    axi_words = tb.samples_to_axi_words(expected_samples)

    await tb.write_waveform_words(axi_words, address=0)
    await tb.wait_idle()

    # Enable external trigger mode
    await tb.set_trigger_mode(external=True)

    # Set length
    await tb.write_register(tb.ADDR_LENGTH, num_samples)

    # Wait a bit, then pulse external trigger
    await ClockCycles(dut.s_axi_aclk, 10)
    await tb.pulse_external_trigger()

    received = await tb.collect_output(num_samples)
    assert tb.verify_samples(received, expected_samples), "External trigger test failed"

    # Verify that internal trigger DOES NOT work in external mode
    tb.log.info("Verifying internal trigger is disabled in external mode...")
    await tb.write_register(tb.ADDR_CTRL, 0x5)  # trigger=1, trigger_mode=1

    # Wait to see if any data comes out (it shouldn't)
    await ClockCycles(dut.s_axi_aclk, 50)
    assert tb.axis_sink.empty(), "Internal trigger should be disabled in external mode"

    # Switch back to internal mode and verify internal trigger works
    await tb.set_trigger_mode(external=False)
    await tb.trigger_waveform(num_samples)
    received = await tb.collect_output(num_samples)
    assert tb.verify_samples(received, expected_samples), "Internal trigger failed after switching back"


@cocotb.test(timeout_time=20, timeout_unit="us")
async def test_write_completes_while_stream_stalled(dut):
    """A waveform write must complete even when playback is stalled by m_axis_tready = 0 (no CPU hang)."""
    tb = AxilWaveGenTB(dut)
    await tb.reset()
    samples = tb.generate_test_pattern(4, "counter")
    await tb.write_waveform_words(tb.samples_to_axi_words(samples))
    tb.axis_sink.pause = True
    await tb.trigger_waveform(4)
    await with_timeout(tb.write_waveform_data(bytes(8)), 2, "us")


@cocotb.test(timeout_time=50, timeout_unit="us")
async def test_32bit_writes_shuffled(dut):
    """32-bit stores (half of WSTRB) in random order, as a CPU memcpy may issue, give the same waveform."""
    tb = AxilWaveGenTB(dut)
    await tb.reset()
    rng = random.Random(3)
    num_samples = 9
    samples = tb.generate_test_pattern(num_samples, "random")
    data = b"".join(w.to_bytes(tb.axi_bytes, "little") for w in tb.samples_to_axi_words(samples))
    offsets = list(range(0, len(data), 4))
    rng.shuffle(offsets)
    for off in offsets:
        await tb.axil_master.write(tb.WAVEFORM_BASE_ADDR + off, data[off : off + 4])
    await tb.trigger_waveform(num_samples)
    received = await tb.collect_output(num_samples)
    assert tb.verify_samples(received, samples), "32-bit shuffled writes corrupted the waveform"


# =============================================================================
# Modes (register map version 2): single, loop, CW; staged values active on apply
# =============================================================================

MODE_SINGLE, MODE_LOOP, MODE_CW = 0, 1, 2


async def set_mode(tb, mode, cw_i=0, cw_q=0, apply="ctrl"):
    """Stage mode and CW value; apply with the ctrl bit, the cw_apply pin, or not at all (apply=None)."""
    await tb.write_register(tb.registers["mode"]["address_offset"], mode)
    await tb.write_register(tb.registers["cw_iq"]["address_offset"], ((cw_q & 0xFFFF) << 16) | (cw_i & 0xFFFF))
    if apply == "ctrl":
        await tb.write_register(tb.ADDR_CTRL, 0x8)
    elif apply == "pin":
        tb.dut.cw_apply.value = 1
        await RisingEdge(tb.dut.s_axi_aclk)
        tb.dut.cw_apply.value = 0
    await ClockCycles(tb.dut.s_axi_aclk, 2)


def play_beat(dut):
    """An accepted beat that is a playback row (CW beats are valid too)."""
    return dut.m_axis_tvalid.value == 1 and dut.m_axis_tready.value == 1 and dut.u_wave_gen.play_valid.value == 1


async def beats(tb, cycles, playback=False):
    """Accepted output beats over a number of cycles (only playback rows if playback): list of (tdata, tlast)."""
    out = []
    for _ in range(cycles):
        await RisingEdge(tb.dut.s_axi_aclk)
        if playback and not play_beat(tb.dut):
            continue
        if tb.dut.m_axis_tvalid.value == 1 and tb.dut.m_axis_tready.value == 1:
            out.append((int(tb.dut.m_axis_tdata.value), int(tb.dut.m_axis_tlast.value)))
    return out


def cw_row(tb, i, q):
    pair = ((q & 0xFFFF) << 16) | (i & 0xFFFF)
    return sum(pair << (32 * k) for k in range(tb.out_data_width // 32))


@cocotb.test(timeout_time=20, timeout_unit="us")
async def test_version_register(dut):
    """Register map version 2 is readable (the driver uses it to tell old bitstreams apart)."""
    tb = AxilWaveGenTB(dut)
    await tb.reset()
    v = await tb.read_register(tb.registers["version"]["address_offset"])
    assert v & 0xFFFFFFFF == 0x00020000, f"version 0x{v:08x}"


@cocotb.test(timeout_time=50, timeout_unit="us")
async def test_cw_mode(dut):
    """CW: every cycle a valid row of the repeated I/Q pair, no tlast; status shows mode 2; triggers do nothing."""
    tb = AxilWaveGenTB(dut)
    await tb.reset()
    await set_mode(tb, MODE_CW, cw_i=12345, cw_q=-2222)
    st = await tb.read_status()
    assert (st >> 4) & 3 == MODE_CW and st & 1 == 0, f"status 0x{st:x}"
    out = await beats(tb, 50)
    assert len(out) == 50, f"{len(out)} valid beats in 50 cycles"
    assert all(d == cw_row(tb, 12345, -2222) and last == 0 for d, last in out)
    await tb.trigger_waveform(8)  # ignored in CW
    out = await beats(tb, 20)
    assert all(d == cw_row(tb, 12345, -2222) for d, _ in out) and len(out) == 20


@cocotb.test(timeout_time=50, timeout_unit="us")
async def test_staged_until_apply(dut):
    """Mode and CW value stay staged until apply; the common cw_apply pin applies them too."""
    tb = AxilWaveGenTB(dut)
    await tb.reset()
    await set_mode(tb, MODE_CW, cw_i=100, cw_q=200, apply=None)
    assert (await tb.read_status() >> 4) & 3 == MODE_SINGLE
    assert not await beats(tb, 20), "output before apply"
    await set_mode(tb, MODE_CW, cw_i=100, cw_q=200, apply="pin")
    out = await beats(tb, 20)
    assert len(out) == 20 and all(d == cw_row(tb, 100, 200) for d, _ in out)
    # a new staged value does not change the output until the next apply
    await set_mode(tb, MODE_CW, cw_i=7, cw_q=8, apply=None)
    assert all(d == cw_row(tb, 100, 200) for d, _ in await beats(tb, 10))
    await set_mode(tb, MODE_CW, cw_i=7, cw_q=8, apply="pin")
    assert all(d == cw_row(tb, 7, 8) for d, _ in await beats(tb, 10))


@cocotb.test(timeout_time=100, timeout_unit="us")
async def test_loop_mode(dut):
    """Loop: one trigger plays the waveform pass after pass (tlast per pass); leaving loop completes the pass."""
    tb = AxilWaveGenTB(dut)
    await tb.reset()
    n = 6
    samples = tb.generate_test_pattern(n, "random")
    await tb.write_waveform_words(tb.samples_to_axi_words(samples))
    await set_mode(tb, MODE_LOOP)
    await tb.trigger_waveform(n)
    out = await beats(tb, 10 * n, playback=True)
    assert len(out) >= 4 * n, f"only {len(out)} beats"
    first = next(k for k, (d, _) in enumerate(out) if d == samples[0])
    for k, (d, last) in enumerate(out[first:]):
        assert d == samples[k % n], f"beat {k}: wrong row"
        assert last == (k % n == n - 1), f"beat {k}: tlast {last}"
    await set_mode(tb, MODE_SINGLE)
    assert await tb._wait_not_busy(4 * n + 50), "loop did not stop after leaving loop mode"
    tail = await beats(tb, 3 * n)
    assert not tail, "output after the loop stopped"


@cocotb.test(timeout_time=100, timeout_unit="us")
async def test_cw_entry_stops_playback(dut):
    """Applying CW during a playback stops it at once; back in single mode a trigger plays from row 0."""
    tb = AxilWaveGenTB(dut)
    await tb.reset()
    n = 64
    samples = tb.generate_test_pattern(n, "random")
    await tb.write_waveform_words(tb.samples_to_axi_words(samples))
    await tb.trigger_waveform(n)
    await ClockCycles(tb.dut.s_axi_aclk, 10)
    await set_mode(tb, MODE_CW, cw_i=1, cw_q=-1)
    assert (await tb.read_status()) & 1 == 0, "playback still busy in CW"
    assert all(d == cw_row(tb, 1, -1) for d, _ in await beats(tb, 10))
    await set_mode(tb, MODE_SINGLE)
    assert not await beats(tb, 10), "output in single mode without a trigger"
    trig = cocotb.start_soon(beats(tb, n + 40, playback=True))
    await tb.trigger_waveform(n)
    out = await trig
    assert [d for d, _ in out] == samples, "playback after CW not from row 0"


@cocotb.test(timeout_time=50, timeout_unit="us")
async def test_no_beats_between_playbacks(dut):
    """
    Outside playback and CW, tvalid is low: no beats before or after a single playback, so the clock-crossing FIFO
    behind the generator empties and every playback starts with the same latency (axis_idle_zero at the DAC input
    makes the gaps zero). Status bit 2 marks playback rows.
    """
    tb = AxilWaveGenTB(dut)
    await tb.reset()
    n = 8
    samples = tb.generate_test_pattern(n, "random")
    await tb.write_waveform_words(tb.samples_to_axi_words(samples))
    assert (await tb.read_status() >> 2) & 1 == 0, "playback valid before a trigger"
    trig = cocotb.start_soon(beats(tb, n + 60))
    await tb.trigger_waveform(n)
    out = await trig
    assert [d for d, _ in out] == samples, f"{len(out)} beats; expected exactly the {n} playback rows"
    assert [last for _, last in out] == [0] * (n - 1) + [1], "tlast only on the last row"
    assert (await tb.read_status() >> 2) & 1 == 0, "playback valid after the playback"
