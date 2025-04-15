import logging
from pathlib import Path
import json
import cocotb
import random
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles
from cocotbext.axi import AxiLiteBus, AxiLiteMaster


class TB:
    def __init__(self, dut):
        dut._log.setLevel(logging.INFO)
        self.dut = dut
        ip_path = Path(__file__).resolve().parent.parent.parent
        json_path = ip_path / 'rtl' / 'axil_rf_control.json'
        with open(json_path, 'r') as f:
            self.registers = json.load(f)

        cocotb.start_soon(Clock(dut.s_axi_aclk, 4, units="ns").start())

        self.dut.rf_permit_in.value = 1
        self.dut.ext_trigger_in.value = 0
        self.dut.evr_trigger_in.value = 0

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

    async def write_register(self, register, value):
        await self.axil_master.write(
            self.registers[register]['address_offset'],
            value.to_bytes(4, 'little'))

    async def read_register(self, register):
        addr = self.registers[register]['address_offset']
        data = await self.axil_master.read(addr, 4)
        return int.from_bytes(data.data, 'little')


@cocotb.test(timeout_time=1, timeout_unit='us')
async def test_write(dut):
    tb = TB(dut)
    await tb.cycle_reset()
    test_regs_dict = {
        'trig_sel': 0,
        'trig_period': 20,
        'trig_divide': 1,
        'pulse_length': 8,
        'dac_enable': 1,
        'amp_loop_setpoint': 200,
        'phs_loop_setpoint': 120,
    }

    for reg, value in test_regs_dict.items():
        await tb.write_register(reg, value)
        assert await tb.read_register(reg) == value, \
            f"readback {reg} mismatch"
        assert getattr(tb.dut, reg).value == value, \
            f"write {reg} mismatch: {getattr(tb.dut, reg).value}"


@cocotb.test(timeout_time=1, timeout_unit='us')
async def test_read(dut):
    tb = TB(dut)
    await tb.cycle_reset()
    test_regs_dict = {
        'amp_measured': random.randint(0, 3000),
        'amp_loop_err': random.randint(0, 1000),
        'phs_measured': random.randint(0, 3000),
        'phs_loop_err': random.randint(0, 1000),
    }
    for reg, value in test_regs_dict.items():
        getattr(tb.dut, reg).value = value
        await RisingEdge(tb.dut.s_axi_aclk)

    reg_val = await tb.read_register('rf_status')
    assert reg_val == 1, f"status mismatch: rf_status = 0x{reg_val}"

    for reg, value in test_regs_dict.items():
        reg_val = await tb.read_register(reg)
        assert reg_val == getattr(tb.dut, reg).value, \
            f"{reg} mismatch: {reg_val} != {getattr(tb.dut, reg).value}"
