import logging
from pathlib import Path
import json
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles
from cocotbext.axi import AxiLiteBus, AxiLiteMaster
from cocotb.handle import Immediate


class TB:
    def __init__(self, dut):
        dut._log.setLevel(logging.WARNING)
        self.dut = dut
        self.addr_length = 1 << dut.ADDR_WIDTH.value.to_unsigned()
        self.fcnt_width = dut.FCNT_WIDTH.value.to_unsigned()
        ip_path = Path(__file__).resolve().parent.parent.parent
        json_path = ip_path / 'rtl' / 'axil_evr.json'
        with open(json_path, 'r') as f:
            self.registers = json.load(f)

        self.gt_refclk_freq = 125e6
        gt_refclk = Clock(
            dut.gt_refclk_p, 1e12 // self.gt_refclk_freq, unit="ps")
        cocotb.start_soon(Clock(dut.s_axi_aclk, 10, unit="ns").start())
        cocotb.start_soon(Clock(dut.dsp_clk, 4, unit="ns").start())
        cocotb.start_soon(gt_refclk.start())

        self.axil_master = AxiLiteMaster(
            AxiLiteBus.from_prefix(dut, "s_axi"),
            dut.s_axi_aclk, dut.s_axi_aresetn,
            reset_active_level=False)

    def convert_freq_to_hz(self, f_cnt, f_ref=100.0e6):
        """Convert the frequency counter value to Hz"""
        return (f_cnt / 2**self.fcnt_width) * f_ref

    def check_freq(self, freq, freq_expect, tolerance_ppm=2000.0):
        ppm = ((freq / freq_expect) - 1.0) * 1e6
        assert abs(ppm) < tolerance_ppm, \
            f"Freq is out of spec by {ppm:3.0f} ppm"

    async def cycle_reset(self):
        self.dut.s_axi_aresetn.set(Immediate(1))
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


@cocotb.test(timeout_time=2, timeout_unit='us')
async def test_reset(dut):
    tb = TB(dut)
    await tb.cycle_reset()
    for value in [0, 1]:
        await tb.write_register('reset_all', value)
    await ClockCycles(dut.s_axi_aclk, 32)
    gt_evr_status = await tb.read_register('gt_evr_status')
    reset_rx_done = (gt_evr_status >> 2) & 0x1
    assert reset_rx_done == 1, "reset_rx_done is not set"
    await ClockCycles(dut.s_axi_aclk, 50)
    gt_evr_status = await tb.read_register('gt_evr_status')
    assert gt_evr_status & 0x1 == 1, "rx_aligned is not set"


@cocotb.test(timeout_time=20, timeout_unit='us')
async def test_freq_counter(dut):
    tb = TB(dut)
    await tb.cycle_reset()
    # wait for the frequency counter to stabilize
    # freq_count refresh rate: 100M / 2**8 = 390625 Hz
    await ClockCycles(dut.s_axi_aclk, 800)  # 1/390625 = 2560 ns
    gt_refclk_freq = tb.convert_freq_to_hz(
        await tb.read_register('gt_ref_freq'))
    gt_rx_freq = tb.convert_freq_to_hz(
        await tb.read_register('gt_rx_freq'))
    dut._log.info(f"gt_ref_freq: {gt_refclk_freq} Hz")
    dut._log.info(f"gt_rx_freq:  {gt_rx_freq} Hz")
    tb.check_freq(gt_refclk_freq, tb.gt_refclk_freq)
    tb.check_freq(gt_rx_freq, tb.gt_refclk_freq)
