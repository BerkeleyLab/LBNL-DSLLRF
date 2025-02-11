import logging
import cocotb
import random
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles
from cocotbext.axi import AxiLiteBus, AxiLiteMaster


class TB:
    def __init__(self, dut):
        dut._log.setLevel(logging.INFO)
        self.dut = dut
        cocotb.start_soon(Clock(dut.s_axi_aclk, 4, units="ns").start())

        self.axil_master = AxiLiteMaster(
            AxiLiteBus.from_prefix(dut, "s_axi"),
            dut.s_axi_aclk, dut.s_axi_aresetn,
            reset_active_level=False)

    async def cycle_reset(self):
        self.dut.s_axi_aresetn.setimmediatevalue(1)
        await ClockCycles(self.dut.s_axi_aclk, 2)
        self.dut.s_axi_aresetn.value = 0
        await RisingEdge(self.dut.s_axi_aclk)
        self.dut.s_axi_aresetn.value = 1
        await RisingEdge(self.dut.s_axi_aclk)

    async def drive_gpio(self, value=0):
        self.dut.gpio_in.value = value
        await RisingEdge(self.dut.s_axi_aclk)


@cocotb.test(timeout_time=1, timeout_unit='us')
async def test_write(dut):
    tb = TB(dut)
    await tb.cycle_reset()
    addr = tb.dut.ADDR_GPIO_OUT.value
    test_data = b'\x00\x11\x22\x33'
    await tb.axil_master.write(addr, test_data)
    assert dut.gpio_out.value == int.from_bytes(test_data, 'little'), \
        "write gpio_out mismatch"
    data = await tb.axil_master.read(addr, 4)
    assert data.data == test_data, "read back gpio_out mismatch"


@cocotb.test(timeout_time=1, timeout_unit='us')
async def test_read(dut):
    tb = TB(dut)
    await tb.cycle_reset()
    addr = tb.dut.ADDR_GPIO_IN.value
    gpio_in = random.randint(0, 0xFFFFFFFF)
    await tb.drive_gpio(gpio_in)
    data = await tb.axil_master.read(addr, 4)
    assert gpio_in == int.from_bytes(data, 'little'), \
        "read gpio_in mismatch"
