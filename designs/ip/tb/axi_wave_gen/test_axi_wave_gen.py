import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles
import logging
from cocotbext.axi import AxiBus, AxiMaster
from cocotbext.axi import AxiStreamBus, AxiStreamSink

import random
import math


class AxiWaveGenTB:
    """Testbench for axi_wave_gen"""

    def __init__(self, dut):
        self.dut = dut
        self.log = dut._log
        self.log.setLevel(logging.INFO)

        # Get parameters (defaults for simulation)
        self.axi_data_width = self._get_param('AXI_DATA_WIDTH', 256)
        self.out_data_width = self._get_param('OUT_DATA_WIDTH', 320)
        self.granule = self._get_param('GRANULE', 64)
        self.bank_depth = self._get_param('BANK_DEPTH', 4096)
        self.ram_style = self._get_param('RAM_STYLE', "ultra")

        self.axi_bytes = self.axi_data_width // 8
        self.out_bytes = self.out_data_width // 8
        self.out_granules = self.out_data_width // self.granule
        self.axi_granules = self.axi_data_width // self.granule

        self.log.warning("Configuration:")
        self.log.warning(f"  AXI Data Width: {self.axi_data_width} bits ({self.axi_granules} granules)")
        self.log.warning(f"  Output Width:   {self.out_data_width} bits ({self.out_granules} granules)")
        self.log.warning(f"  Granule:        {self.granule} bits")
        self.log.warning(f"  Bank Depth:     {self.bank_depth}")
        self.log.warning(f"  Ram Style:      {self.ram_style}")

        # Create clock
        self.clock = Clock(dut.clk, 4, unit="ns")
        cocotb.start_soon(self.clock.start())

        # Create AXI Master
        self.axi_master = AxiMaster(
            AxiBus.from_prefix(dut, "s_axi"),
            dut.clk,
            dut.rst_n,
            reset_active_level=False
        )

        # Create AXI-Stream Sink
        self.axis_sink = AxiStreamSink(
            AxiStreamBus.from_prefix(dut, "m_axis"),
            dut.clk,
            dut.rst_n,
            reset_active_level=False,
            byte_size=self.out_data_width
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

        self.dut.rst_n.value = 0
        self.dut.ctrl_trigger.value = 0
        self.dut.ctrl_wave_length.value = 0
        self.dut.ctrl_flush.value = 0

        # Clear any pending data in sink
        while not self.axis_sink.empty():
            self.axis_sink.recv_nowait()

        await ClockCycles(self.dut.clk, 20)
        self.dut.rst_n.value = 1
        await ClockCycles(self.dut.clk, 20)

        # Wait for not busy after reset
        await self._wait_not_busy(100)
        self.log.info("Reset complete")

    async def _wait_not_busy(self, timeout_cycles=1000):
        """Internal wait for not busy with timeout"""
        for _ in range(timeout_cycles):
            await RisingEdge(self.dut.clk)
            if self.dut.ctrl_busy.value == 0:
                return True
        return False

    async def write_waveform_data(self, data: bytes, address: int = 0):
        """Write waveform data via AXI"""
        self.log.info(f"Writing {len(data)} bytes to address 0x{address:04x}")

        # Perform AXI write
        await self.axi_master.write(address, data)

        # Small delay for write to propagate
        await ClockCycles(self.dut.clk, 5)

    async def write_waveform_words(self, words: list, address: int = 0):
        """Write list of integer words as waveform data"""
        data = b''
        for word in words:
            data += word.to_bytes(self.axi_bytes, byteorder='little')

        await self.write_waveform_data(data, address)

    async def flush_and_wait(self, timeout_cycles=5000):
        """Flush write accumulator and wait for completion"""
        self.log.info("Flushing write accumulator...")

        # Pulse flush signal
        self.dut.ctrl_flush.value = 1
        await ClockCycles(self.dut.clk, 5)
        self.dut.ctrl_flush.value = 0

        # Wait for busy to clear
        success = await self._wait_not_busy(timeout_cycles)
        if not success:
            # Debug: print state
            self.log.error("Timeout waiting for flush completion")
            self.log.error(f"  ctrl_busy = {self.dut.ctrl_busy.value}")
        assert success, "Timeout waiting for flush completion"

        self.log.info("Flush complete, DUT idle")

    async def trigger_waveform(self, length: int):
        """Trigger waveform output"""
        self.log.info(f"Triggering waveform with length {length}")

        # Set length
        self.dut.ctrl_wave_length.value = length
        await ClockCycles(self.dut.clk, 2)

        # Pulse trigger
        self.dut.ctrl_trigger.value = 1
        await ClockCycles(self.dut.clk, 2)
        self.dut.ctrl_trigger.value = 0
        await ClockCycles(self.dut.clk, 2)

    async def collect_output(self, num_samples: int):
        """Collect output samples from AXI-Stream with timeout"""
        samples = []

        self.log.warning(f"Collecting {num_samples} output samples...")
        samples = await self.axis_sink.read()
        self.log.warning(f"Successfully collected {len(samples)} samples")
        return samples

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
            self.log.info(f"  Got {i}:   0x{rx_int:0{self.out_bytes*2}x}")

        for i, (rx, exp) in enumerate(zip(received, expected)):
            # Convert bytes to int for comparison
            if isinstance(rx, bytes):
                rx_int = int.from_bytes(rx, byteorder='little')
            else:
                rx_int = int(rx)
            # Mask to output width
            rx_int &= (1 << self.out_data_width) - 1
            exp &= (1 << self.out_data_width) - 1

            if rx_int != exp:
                self.log.error(f"Sample {i} mismatch:")
                self.log.error(f"  Got:      0x{rx_int:0{self.out_bytes*2}x}")
                self.log.error(f"  Expected: 0x{exp:0{self.out_bytes*2}x}")
                self.log.error(f"  XOR:      0x{(rx_int ^ exp):0{self.out_bytes*2}x}")
                return False

        self.log.info(f"All {len(expected)} samples verified successfully")
        return True


# =============================================================================
# Test Cases
# =============================================================================

@cocotb.test(timeout_time=5, timeout_unit='us')
async def test_basic_write_read(dut):
    """Test basic write and read functionality"""
    tb = AxiWaveGenTB(dut)
    await tb.reset()

    # Small number of samples for basic test
    num_samples = 8
    expected_samples = tb.generate_test_pattern(num_samples, "counter")

    # Convert to AXI words
    axi_words = tb.samples_to_axi_words(expected_samples)
    tb.log.warning(f"Test: {len(axi_words)} AXI words -> {num_samples} samples")

    await tb.write_waveform_words(axi_words, address=0)
    await tb.flush_and_wait()
    await tb.trigger_waveform(num_samples)
    received = await tb.collect_output(num_samples)
    assert tb.verify_samples(received, expected_samples), "Sample verification failed"


@cocotb.test(timeout_time=5, timeout_unit='us')
async def test_random_data(dut):
    """Test with random data pattern"""
    tb = AxiWaveGenTB(dut)
    await tb.reset()

    random.seed(42)  # Reproducible
    num_samples = 32
    expected_samples = tb.generate_test_pattern(num_samples, "random")
    axi_words = tb.samples_to_axi_words(expected_samples)

    await tb.write_waveform_words(axi_words, address=0)
    await tb.flush_and_wait()

    await tb.trigger_waveform(num_samples)
    received = await tb.collect_output(num_samples)

    assert tb.verify_samples(received, expected_samples), "Random data test failed"


@cocotb.test(timeout_time=5, timeout_unit='us')
async def test_multiple_triggers(dut):
    """Test multiple trigger sequences"""
    tb = AxiWaveGenTB(dut)
    await tb.reset()

    num_samples = 16
    expected_samples = tb.generate_test_pattern(num_samples, "counter")
    axi_words = tb.samples_to_axi_words(expected_samples)

    # Write once
    await tb.write_waveform_words(axi_words, address=0)
    await tb.flush_and_wait()

    # Trigger multiple times
    for iteration in range(3):
        tb.log.info(f"=== Trigger iteration {iteration + 1} ===")

        await tb.trigger_waveform(num_samples)
        received = await tb.collect_output(num_samples)

        assert tb.verify_samples(received, expected_samples), f"Iteration {iteration + 1} failed"

        # Wait for idle before next trigger
        await ClockCycles(dut.clk, 20)


@cocotb.test(timeout_time=5, timeout_unit='us')
async def test_partial_length(dut):
    """Test reading partial waveform length"""
    tb = AxiWaveGenTB(dut)
    await tb.reset()

    # Write more samples than we'll read
    num_write_samples = 32
    expected_samples = tb.generate_test_pattern(num_write_samples, "counter")
    axi_words = tb.samples_to_axi_words(expected_samples)

    await tb.write_waveform_words(axi_words, address=0)
    await tb.flush_and_wait()

    # Read only first 10 samples
    num_read_samples = 10
    await tb.trigger_waveform(num_read_samples)
    received = await tb.collect_output(num_read_samples)

    assert tb.verify_samples(received, expected_samples[:num_read_samples]), "Partial length test failed"


@cocotb.test(timeout_time=5, timeout_unit='us')
async def test_conversion_boundary(dut):
    """Test at gearbox conversion boundary (LCM of widths)"""
    tb = AxiWaveGenTB(dut)
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
    await tb.flush_and_wait()

    await tb.trigger_waveform(num_samples)
    received = await tb.collect_output(num_samples)

    assert tb.verify_samples(received, expected_samples), "Conversion boundary test failed"


@cocotb.test(timeout_time=5, timeout_unit='us')
async def test_single_sample(dut):
    """Test single sample write/read"""
    tb = AxiWaveGenTB(dut)
    await tb.reset()

    num_samples = 1
    expected_samples = [0xDEADBEEF & ((1 << tb.out_data_width) - 1)]
    axi_words = tb.samples_to_axi_words(expected_samples)

    await tb.write_waveform_words(axi_words, address=0)
    await tb.flush_and_wait()

    await tb.trigger_waveform(num_samples)
    received = await tb.collect_output(num_samples)

    assert tb.verify_samples(received, expected_samples), "Single sample test failed"


@cocotb.test(timeout_time=5, timeout_unit='us')
async def test_tlast_assertion(dut):
    """Verify TLAST is asserted correctly"""
    tb = AxiWaveGenTB(dut)
    await tb.reset()

    num_samples = 8
    expected_samples = tb.generate_test_pattern(num_samples, "counter")
    axi_words = tb.samples_to_axi_words(expected_samples)

    await tb.write_waveform_words(axi_words, address=0)
    await tb.flush_and_wait()

    await tb.trigger_waveform(num_samples)

    # Manually check TLAST
    sample_count = 0
    timeout = 10000

    while sample_count < num_samples and timeout > 0:
        await RisingEdge(dut.clk)
        timeout -= 1

        if dut.m_axis_tvalid.value == 1 and dut.m_axis_tready.value == 1:
            sample_count += 1
            is_last = int(dut.m_axis_tlast.value)

            if sample_count == num_samples:
                assert is_last == 1, f"TLAST not asserted on final sample {sample_count}"
                tb.log.info(f"TLAST correctly asserted on sample {sample_count}")
            else:
                assert is_last == 0, f"TLAST incorrectly asserted on sample {sample_count}"

    assert sample_count == num_samples, f"Only received {sample_count}/{num_samples} samples"
    tb.log.info("TLAST assertion verified")


@cocotb.test(timeout_time=5, timeout_unit='us')
async def test_large_waveform(dut):
    """Test larger waveform"""
    tb = AxiWaveGenTB(dut)
    await tb.reset()

    num_samples = 128
    expected_samples = tb.generate_test_pattern(num_samples, "counter")
    axi_words = tb.samples_to_axi_words(expected_samples)

    await tb.write_waveform_words(axi_words, address=0)
    await tb.flush_and_wait()

    await tb.trigger_waveform(num_samples)
    received = await tb.collect_output(num_samples)

    assert tb.verify_samples(received, expected_samples), "Large waveform test failed"
