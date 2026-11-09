import json
import logging
import random
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.handle import Immediate
from cocotb.triggers import ClockCycles, RisingEdge
from cocotbext.axi import AxiLiteBus, AxiLiteMaster


class TB:
    def __init__(self, dut):
        dut._log.setLevel(logging.WARNING)
        self.dut = dut
        ip_path = Path(__file__).resolve().parent.parent.parent
        json_path = ip_path / "rtl" / "axil_rf_control.json"
        with open(json_path) as f:
            self.registers = json.load(f)

        cocotb.start_soon(Clock(dut.s_axi_aclk, 4, unit="ns").start())

        self.dut.rf_permit_in.value = 1
        self.dut.ext_trigger_in.value = 0
        self.dut.evr_trigger_in.value = 0

        self.axil_master = AxiLiteMaster(
            AxiLiteBus.from_prefix(dut, "s_axi"), dut.s_axi_aclk, dut.s_axi_aresetn, reset_active_level=False
        )

    async def cycle_reset(self):
        self.dut.s_axi_aresetn.set(Immediate(1))
        await ClockCycles(self.dut.s_axi_aclk, 2)
        for v in [0, 1]:
            self.dut.s_axi_aresetn.value = v
            await RisingEdge(self.dut.s_axi_aclk)

    async def write_register(self, register, value):
        await self.axil_master.write(self.registers[register]["address_offset"], value.to_bytes(4, "little"))

    async def read_register(self, register):
        addr = self.registers[register]["address_offset"]
        data = await self.axil_master.read(addr, 4)
        return int.from_bytes(data.data, "little")


@cocotb.test(timeout_time=1, timeout_unit="us")
async def test_write(dut):
    tb = TB(dut)
    await tb.cycle_reset()
    test_regs_dict = {
        "trig_sel": 0,
        "trig_period": 20,
        "trig_divide": 1,
        "pulse_length": 8,
        "dac_enable": 1,
        "amp_loop_setpoint": 200,
        "phs_loop_setpoint": 120,
    }

    for reg, value in test_regs_dict.items():
        await tb.write_register(reg, value)
        reg_val = getattr(tb.dut, reg).value
        cocotb.log.warning(f"reg: {reg:20s} val: {int(reg_val):>8d}, expect: {value:>8d}")
        assert reg_val == value, f"write {reg} mismatch: {reg_val} != {value}"
        reg_val_readback = await tb.read_register(reg)
        assert reg_val_readback == value, f"readback {reg} mismatch: {reg_val_readback} != {value}"


@cocotb.test(timeout_time=1, timeout_unit="us")
async def test_read(dut):
    tb = TB(dut)
    await tb.cycle_reset()
    test_regs_dict = {
        "amp_measured": random.randint(0, 3000),
        "amp_loop_err": random.randint(0, 1000),
        "phs_measured": random.randint(0, 3000),
        "phs_loop_err": random.randint(0, 1000),
    }
    # set signal values to be read-back and check
    for reg, value in test_regs_dict.items():
        getattr(tb.dut, reg).value = value
        await RisingEdge(tb.dut.s_axi_aclk)

    reg_val = await tb.read_register("rf_status")
    assert reg_val == 1, f"status mismatch: rf_status = 0x{reg_val}"

    for reg, value in test_regs_dict.items():
        reg_val_readback = await tb.read_register(reg)
        reg_val = getattr(tb.dut, reg).value
        cocotb.log.warning(f"reg: {reg:20s} val: {int(reg_val):>8d}, expect: {value:>8d}")
        assert reg_val_readback == reg_val == value, f"{reg} mismatch: {reg_val} != {reg_val}"


@cocotb.test(timeout_time=1, timeout_unit="us")
async def test_trigger_delay(dut):
    tb = TB(dut)
    await tb.cycle_reset()
    trig_delay_cycles = random.randint(0, 30)
    test_regs_dict = {
        "trig_sel": 2,  # select external trigger input
        "trig_divide": 1,  # purposely test divide=0 case
        "trig_delay": trig_delay_cycles,
    }
    for reg, value in test_regs_dict.items():
        await tb.write_register(reg, value)

    for v in [1, 0]:
        tb.dut.ext_trigger_in.value = v
        await RisingEdge(tb.dut.s_axi_aclk)
    await ClockCycles(tb.dut.s_axi_aclk, trig_delay_cycles)
    for ix in range(3):
        await RisingEdge(tb.dut.s_axi_aclk)
        v = tb.dut.trigger_out.value
        cocotb.log.warning(f"dut.trigger_out: {v}")
        assert v == (ix == 1), "unexpected trigger output"


async def trigger_cycles(tb, n_triggers, timeout_cycles):
    """Clock cycles at which trigger_out is high, collecting up to n_triggers within timeout_cycles."""
    hits = []
    for cycle in range(timeout_cycles):
        await RisingEdge(tb.dut.s_axi_aclk)
        if tb.dut.trigger_out.value == 1:
            hits.append(cycle)
            if len(hits) == n_triggers:
                break
    return hits


@cocotb.test(timeout_time=20, timeout_unit="us")
async def test_internal_trigger_period_change(dut):
    """
    The internal trigger must follow a trig_period write within one period, also when the
    counter has already passed the new period (after reset trig_period is 0, and software sets it
    later). With an exact-match comparison the counter would first wrap at 2**32 (~17 s at 250 MHz).
    """
    tb = TB(dut)
    await tb.cycle_reset()
    await tb.write_register("trig_sel", 0)  # internal trigger
    await ClockCycles(dut.s_axi_aclk, 200)  # counter runs past the period written next

    for period in (20, 50, 8):
        await tb.write_register("trig_period", period)
        hits = await trigger_cycles(tb, n_triggers=4, timeout_cycles=5 * period)
        cocotb.log.warning(f"trig_period={period}: triggers at cycles {hits}")
        assert len(hits) == 4, f"trig_period={period}: {len(hits)} triggers in {5 * period} cycles"
        assert hits[0] <= period, f"trig_period={period}: first trigger after {hits[0]} cycles"
        spacing = {hits[i + 1] - hits[i] for i in range(len(hits) - 1)}
        assert spacing == {period}, f"trig_period={period}: trigger spacing {spacing}"


@cocotb.test(timeout_time=5, timeout_unit="us")
async def test_internal_trigger_disabled(dut):
    """trig_period = 0 (the reset value) disables the internal trigger."""
    tb = TB(dut)
    await tb.cycle_reset()
    await tb.write_register("trig_sel", 0)
    await tb.write_register("trig_period", 0)
    hits = await trigger_cycles(tb, n_triggers=1, timeout_cycles=500)
    assert hits == [], f"trigger with trig_period=0 at cycles {hits}"


@cocotb.test(timeout_time=5, timeout_unit="us")
async def test_cw_apply_pulse(dut):
    """dac_enable bit 2: a one-cycle cw_apply pulse on each 0 -> 1 write, none while it stays 1."""
    tb = TB(dut)
    await tb.cycle_reset()
    pulses = 0

    async def count():
        nonlocal pulses
        while True:
            await RisingEdge(dut.s_axi_aclk)
            pulses += int(dut.cw_apply.value)

    cocotb.start_soon(count())
    for value, expected in ((0b001, 0), (0b101, 1), (0b101, 1), (0b001, 1), (0b111, 2)):
        await tb.write_register("dac_enable", value)
        await ClockCycles(dut.s_axi_aclk, 5)
        assert pulses == expected, f"after writing 0b{value:03b}: {pulses} pulses, expected {expected}"
    assert dut.dac_enable.value == 1 and dut.pulse_enable.value == 1


@cocotb.test()
async def test_capture_arm_pulse(dut):
    """dac_enable bit 3: a one-cycle capture_arm pulse on each 0 -> 1 write, independent of the other bits."""
    tb = TB(dut)
    await tb.cycle_reset()
    pulses = {"capture_arm": 0, "cw_apply": 0}

    async def count():
        while True:
            await RisingEdge(dut.s_axi_aclk)
            for name in pulses:
                pulses[name] += int(getattr(dut, name).value)

    cocotb.start_soon(count())
    for value, arms, applies in ((0b0001, 0, 0), (0b1001, 1, 0), (0b1001, 1, 0), (0b0001, 1, 0), (0b1101, 2, 1)):
        await tb.write_register("dac_enable", value)
        await ClockCycles(dut.s_axi_aclk, 5)
        got = (pulses["capture_arm"], pulses["cw_apply"])
        assert got == (arms, applies), f"after 0b{value:04b}: capture_arm/cw_apply {got}, expected {(arms, applies)}"
