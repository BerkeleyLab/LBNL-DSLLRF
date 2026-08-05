import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from cocotbext.axi import AxiStreamBus, AxiStreamSource, AxiStreamSink
import logging
import random


class AXISAdderTB:
    def __init__(self, dut):
        dut._log.setLevel(logging.WARNING)
        self.dut = dut
        self.samp_dw = samp_dw = dut.SAMP_DW.value.to_unsigned()
        self.samp_num = samp_num = dut.SAMP_NUM.value.to_unsigned()
        self.data_width = samp_dw * samp_num
        self.s0_source = AxiStreamSource(
            AxiStreamBus.from_prefix(dut, "s0_axis"),
            dut.axis_aclk, dut.axis_aresetn,
            reset_active_level=False,
            byte_size=samp_dw)
        self.s1_source = AxiStreamSource(
            AxiStreamBus.from_prefix(dut, "s1_axis"),
            dut.axis_aclk, dut.axis_aresetn,
            reset_active_level=False,
            byte_size=samp_dw)

        self.m_sink = AxiStreamSink(
            AxiStreamBus.from_prefix(dut, "m_axis"),
            dut.axis_aclk, dut.axis_aresetn,
            reset_active_level=False,
            byte_size=samp_dw)

        cocotb.start_soon(Clock(dut.axis_aclk, 4, unit="ns").start())

    async def reset(self):
        for v in [1, 0, 1]:
            self.dut.axis_aresetn.value = v
            await RisingEdge(self.dut.axis_aclk)

    async def send_parallel_transactions(self, s0_samples, s1_samples):
        """Send transactions on both input streams in parallel"""
        # Send both frames (they will be sent in parallel)
        await self.s0_source.write(s0_samples)
        await self.s1_source.write(s1_samples)

    async def receive_result(self):
        """Receive and return the output frame"""
        return await self.m_sink.read()

    def validate_samples(self, s0_samples, s1_samples, output_samples):
        for s0, s1, out in zip(s0_samples, s1_samples, output_samples):
            expected = (s0 + s1) & (2**self.samp_dw - 1)
            assert out == expected, f"Unexpected result: expected {expected}, got {out}"


@cocotb.test()
async def test_basic_addition(dut):
    """Test basic addition functionality"""
    tb = AXISAdderTB(dut)
    await tb.reset()

    s0_samples = [i for i in range(tb.samp_num)]
    s1_samples = [i * 2 for i in range(tb.samp_num)]

    await tb.send_parallel_transactions(s0_samples, s1_samples)
    output_samples = await tb.receive_result()
    tb.validate_samples(s0_samples, s1_samples, output_samples)

    cocotb.log.info("✓ Basic addition test passed")


@cocotb.test()
async def test_random_data(dut):
    """Test with random data"""
    tb = AXISAdderTB(dut)
    await tb.reset()

    # Run multiple random tests
    for test_num in range(10):
        s0_samples = [random.randint(-0x7FFF, 0x7FFF) for _ in range(tb.samp_num)]
        s1_samples = [random.randint(-0x7FFF, 0x7FFF) for _ in range(tb.samp_num)]

        await tb.send_parallel_transactions(s0_samples, s1_samples)
        output_samples = await tb.receive_result()
        tb.validate_samples(s0_samples, s1_samples, output_samples)

    cocotb.log.info("✓ Random data test passed (10 iterations)")


@cocotb.test()
async def test_continuous_stream(dut):
    """Test continuous streaming of data"""
    tb = AXISAdderTB(dut)
    await tb.reset()

    # Send multiple consecutive transactions
    test_data = []
    for transaction in range(5):
        s0_samples = [transaction * 16 + i for i in range(tb.samp_num)]
        s1_samples = [(transaction + 1) * 16 + i for i in range(tb.samp_num)]
        test_data.append((s0_samples, s1_samples))

        await tb.send_parallel_transactions(s0_samples, s1_samples)

    # Verify all outputs
    for transaction, (s0_samples, s1_samples) in enumerate(test_data):
        output_samples = await tb.receive_result()
        tb.validate_samples(s0_samples, s1_samples, output_samples)

    cocotb.log.info("✓ Continuous stream test passed (5 transactions)")
