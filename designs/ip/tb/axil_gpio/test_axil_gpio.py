import logging
import cocotb
import random
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles
from cocotbext.axi import AxiLiteBus, AxiLiteMaster


class TB:
    def __init__(self, dut):
        dut._log.setLevel(logging.WARNING)
        self.dut = dut
        self.registers = {
            'gpio_out0': {
                'address_offset': 0x0,
                'access': 'read-write',
                'size': 32
            },
            'gpio_out1': {
                'address_offset': 0x4,
                'access': 'read-write',
                'size': 32
            },
            'gpio_inp': {
                'address_offset': 0x8,
                'access': 'read-only',
                'size': 32
            }
        }

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
    regs = [tb.registers['gpio_out0'], tb.registers['gpio_out1']]
    ports = [tb.dut.gpio_out0, tb.dut.gpio_out1]
    for i, reg in enumerate(regs):
        addr = reg['address_offset']
        data = random.randint(0, 0xFFFFFFFF)
        await tb.axil_master.write(addr, data.to_bytes(4, 'little'))
        assert ports[i].value == data, "write gpio_out mismatch"
        read_data = await tb.axil_master.read(addr, 4)
        assert read_data.data == data.to_bytes(4, 'little'), \
            "read back gpio_out mismatch"


@cocotb.test(timeout_time=1, timeout_unit='us')
async def test_read(dut):
    tb = TB(dut)
    await tb.cycle_reset()
    regs = [tb.registers['gpio_inp']]
    ports = [tb.dut.gpio_inp]
    for i, reg in enumerate(regs):
        addr = reg['address_offset']
        data = random.randint(0, 0xFFFFFFFF)
        ports[i].value = data
        read_data = await tb.axil_master.read(addr, 4)
        assert read_data.data == data.to_bytes(4, 'little'), \
            "read gpio_in mismatch"
