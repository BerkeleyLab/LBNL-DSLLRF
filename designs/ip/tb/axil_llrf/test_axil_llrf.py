from llrf_dsp import LLRFModel
from pathlib import Path
import json
import cocotb
import itertools
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles
from cocotbext.axi import (AxiStreamBus, AxiStreamFrame,
                           AxiLiteBus, AxiLiteMaster,
                           AxiStreamSource, AxiStreamSink)
import logging
import numpy as np


class TB:
    llrf = LLRFModel()

    def __init__(self, dut):
        dut._log.setLevel(logging.WARNING)
        self.dut = dut
        ip_path = Path(__file__).resolve().parent.parent.parent
        json_path = ip_path / 'rtl' / 'axil_rf_control.json'
        with open(json_path, 'r') as f:
            self.registers = json.load(f)

        self.source0 = AxiStreamSource(
            AxiStreamBus.from_prefix(dut, "s0_axis"),
            dut.clk, dut.s_axi_aresetn, reset_active_level=False)
        self.source1 = AxiStreamSource(
            AxiStreamBus.from_prefix(dut, "s1_axis"),
            dut.clk, dut.s_axi_aresetn, reset_active_level=False)

        self.sink = AxiStreamSink(
            AxiStreamBus.from_prefix(dut, "m_axis"),
            dut.clk, dut.s_axi_aresetn, reset_active_level=False)

        self.axil_master = AxiLiteMaster(
            AxiLiteBus.from_prefix(dut, "s_axi"),
            dut.clk, dut.s_axi_aresetn, reset_active_level=False)

        cocotb.start_soon(Clock(dut.clk, 4, units="ns").start())

        self.dut.rf_permit_in.value = 1
        self.dut.ext_trigger_in.value = 0
        self.dut.evr_trigger_in.value = 0

    def log_banner(self, str):
        self.dut._log.warning('*'*20 + f"{str:^20s}" + '*'*20)

    def wrap_phase(self, phs: float, deg=True):
        """Wrap phase value to be within [-180, 180] or [-pi, pi]. """
        scale = 180 if deg else np.pi
        return (phs + scale) % (2 * scale) - scale

    def decode_phase(self, signal, deg=True):
        """ Convert phase value from register """
        scale = 360 if deg else (2 * np.pi)
        reg = signal.value.signed_integer
        width = len(signal)
        return self.wrap_phase(reg / 2**width * scale)

    def encode_2s_comp(self, val):
        """ encode signed integer to 2's complement representation """
        return int(np.binary_repr(val, width=32), 2)

    def polar_to_rect(self, amp, phs):
        """ Convert polar to rectangular coordinates """
        phs = np.deg2rad(phs)
        i_val = int(amp * np.cos(phs))
        q_val = int(amp * np.sin(phs))
        return i_val, q_val

    async def cycle_reset(self):
        self.dut.s_axi_aresetn.setimmediatevalue(1)
        await ClockCycles(self.dut.clk, 2)
        for val in [0, 1]:
            self.dut.s_axi_aresetn.value = val
            await RisingEdge(self.dut.clk)

    async def write_register(self, register, value):
        val = self.encode_2s_comp(value)
        await self.axil_master.write(
            self.registers[register]['address_offset'],
            val.to_bytes(4, 'little'))

    async def read_register(self, register):
        addr = self.registers[register]['address_offset']
        data = await self.axil_master.read(addr, 4)
        return int.from_bytes(data.data, 'little')

    async def init_llrf(self, amp_loop_setpoint=10000, phs_loop_setpoint=0):
        regs_dict = {
            'trig_sel': 0,
            'trig_period': 20,
            'trig_divide': 1,
            'pulse_length': 8,
            'dac_enable': 1,
            'amp_loop_enable': 0,
            'amp_loop_reset': 0,
            'amp_loop_setpoint': amp_loop_setpoint,
            'amp_loop_kp': 2,
            'amp_loop_ki': 0,
            'phs_loop_enable': 0,
            'phs_loop_reset': 0,
            'phs_loop_kp': 2,
            'phs_loop_ki': 0,
            'phs_loop_setpoint': phs_loop_setpoint,
        }
        for reg, val in regs_dict.items():
            await self.write_register(reg, val)

    async def read_m_axis(self):
        rx_frame = await self.sink.recv()
        return np.frombuffer(rx_frame.tdata, dtype=np.int16)

    async def drive_s_axis(self, i_val, q_val, noise_amp=10):
        for t in itertools.count():
            i_array = i_val * np.ones(
                (self.dut.S_AXIS_SAMP_NUM.value,), dtype=np.int16)
            q_array = q_val * np.ones_like(i_array)
            # add random noise
            for array in [i_array, q_array]:
                noise = np.random.randint(
                    low=-noise_amp, high=noise_amp,
                    size=(self.dut.S_AXIS_SAMP_NUM.value,), dtype=np.int16)
                array += noise
            i_frame = AxiStreamFrame(bytearray(i_array.tobytes()))
            q_frame = AxiStreamFrame(bytearray(q_array.tobytes()))
            await self.source0.send(i_frame)
            await self.source1.send(q_frame)
            await RisingEdge(self.dut.clk)

    async def init_test(self) -> None:
        await self.cycle_reset()
        amp_exp = self.llrf.max_adc_amp
        phs_exp = np.random.randint(-180, 180)
        return amp_exp, phs_exp

    async def test_rx(self):
        self.log_banner('RX Test')
        amp_exp, phs_exp = await self.init_test()
        i_val, q_val = self.polar_to_rect(amp_exp, phs_exp)
        cocotb.start_soon(self.drive_s_axis(i_val, q_val))

        await ClockCycles(self.dut.clk, self.llrf.rx_coupler.pipeline_delay)
        await ClockCycles(self.dut.clk, self.llrf.rx_cordic.pipeline_delay)
        await self.check_sig(amp_exp, phs_exp)

    async def test_open_loop(self):
        self.log_banner('TX Test')
        amp_exp, phs_exp = await self.init_test()
        amp_setp, phs_setp = self.llrf.calc_open_loop_setp(amp_exp, phs_exp)
        await self.init_llrf(amp_setp, phs_setp)

        await ClockCycles(self.dut.clk, self.llrf.tx_cordic.pipeline_delay)
        await ClockCycles(self.dut.clk, self.llrf.tx_coupler.pipeline_delay)

        # flush sink
        while not self.sink.empty():
            await self.sink.recv()

        i_val, q_val = self.polar_to_rect(amp_exp, phs_exp)

        rx_expect = np.empty((self.dut.M_AXIS_SAMP_NUM.value,), dtype=np.int16)
        rx_expect[0::2] = i_val
        rx_expect[1::2] = q_val
        rx_arr = await self.read_m_axis()
        self.dut._log.warning(f"expected: {rx_expect}")
        self.dut._log.warning(f"received: {rx_arr}")
        assert np.allclose(rx_arr, rx_expect, atol=1), \
            f"Data mismatch: {rx_arr} != {rx_expect}"
        assert self.sink.empty()

    async def check_sig(self, amp_exp, phs_exp, noise_amp=10) -> None:
        self.dut._log.warning(
            f"expected mag: {amp_exp:8.2f} cnt,  phs: {phs_exp:6.3f} deg")
        for _ in range(5):
            await RisingEdge(self.dut.clk)
            i_meas = self.dut.llrf_dsp.field_i.value.signed_integer
            q_meas = self.dut.llrf_dsp.field_q.value.signed_integer
            iq_meas = i_meas + 1j * q_meas
            amp_meas = self.dut.amp_measured.value.signed_integer
            amp_meas /= np.abs(self.llrf.rx_gain)
            phs_meas = self.decode_phase(self.dut.phs_measured)
            self.dut._log.debug(
                f"raw IQ   mag: {np.abs(iq_meas):8.2f} cnt,  "
                f"phs: {np.angle(iq_meas, deg=True):6.3f} deg")
            self.dut._log.warning(
                f"measured mag: {amp_meas:8.2f} cnt,  "
                f"phs: {phs_meas:6.3f} deg")
            # XXX: validation condition is fuzzy...
            assert abs(amp_meas - amp_exp) < noise_amp, \
                f"RX amplitude out-of-bound of {noise_amp}%"
            assert abs(self.wrap_phase(phs_meas - phs_exp)) < 0.1, \
                "RX phase out-of-bound of 0.1 deg"


@cocotb.test(timeout_time=1, timeout_unit='us')
async def test_llrf_open_loop(dut, length=1):
    tb = TB(dut)
    await tb.test_open_loop()


@cocotb.test(timeout_time=1, timeout_unit='us')
async def test_llrf_rx(dut, length=1):
    tb = TB(dut)
    await tb.test_rx()
