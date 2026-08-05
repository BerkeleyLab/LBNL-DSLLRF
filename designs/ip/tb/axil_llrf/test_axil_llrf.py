from llrf_dsp import LLRFModel
from pathlib import Path
import json
import cocotb
import random
from cocotb.clock import Clock
from cocotb.queue import Queue
from cocotb.handle import Immediate
from cocotb.triggers import RisingEdge, ClockCycles, Timer
from cocotbext.axi import (AxiStreamBus, AxiLiteBus, AxiLiteMaster,
                           AxiStreamSource, AxiStreamSink)
import logging
import numpy as np
import itertools


class Plant:
    """Model of a plant for feedback testing. """
    def __init__(self,
                 delay_ns: float = 0.1,
                 gain: float = 1) -> None:
        self.i_queue = Queue()
        self.o_queue = Queue()
        self.gain = gain
        self.delay_ns = delay_ns
        cocotb.start_soon(self.run())

    def step(self, complex_val):
        return complex_val * self.gain

    async def run(self) -> None:
        while True:
            complex_val = await self.i_queue.get()
            await Timer(self.delay_ns, 'ns')
            out_val = self.step(complex_val)
            await self.o_queue.put(out_val)


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

        self.plant = Plant(delay_ns=0.5, gain=1)

        cocotb.start_soon(Clock(dut.clk, 4, unit="ns").start())

        self.dut.rf_permit_in.value = 1
        self.dut.ext_trigger_in.value = 0
        self.dut.evr_trigger_in.value = 0

    def log_banner(self, str):
        cocotb.log.warning('*'*20 + f"{str:^20s}" + '*'*20)

    def wrap_phase(self, phs: float, deg=True):
        """Wrap phase value to be within [-180, 180] or [-pi, pi]. """
        scale = 180 if deg else np.pi
        return (phs + scale) % (2 * scale) - scale

    def decode_phase(self, signal, deg=True):
        """ Convert phase value from register """
        scale = 360 if deg else (2 * np.pi)
        reg = signal.value.to_signed()
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
        self.dut.s_axi_aresetn.set(Immediate(1))
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
            'amp_loop_kp': 200,
            'amp_loop_ki': 30,
            'phs_loop_enable': 0,
            'phs_loop_reset': 0,
            'phs_loop_kp': 300,
            'phs_loop_ki': 100,
            'phs_loop_setpoint': phs_loop_setpoint,
        }
        for reg, val in regs_dict.items():
            await self.write_register(reg, val)
        self.sink.clear()
        self.source0.clear()
        self.source1.clear()

    async def read_m_axis(self):
        rx_frame = await self.sink.read()
        rx_array = np.frombuffer(bytes(rx_frame), dtype=np.int16)
        self.dut._log.info(f"read_m_axis : {rx_array}")
        return rx_array

    async def write_s_axis(self, i_array, q_array):
        self.dut._log.info(f"write_s_axis, s0: {i_array}")
        self.dut._log.info(f"write_s_axis, s1: {q_array}")
        await self.source0.write(bytes(i_array))
        await self.source1.write(bytes(q_array))

    async def init_test(self, amp_exp=None, phs_exp=None) -> None:
        await self.cycle_reset()
        if amp_exp is None:
            amp_exp = self.llrf.max_adc_amp
        else:
            assert amp_exp < self.llrf.max_adc_amp, \
                f"amp_exp {amp_exp:.3f} too high. " \
                f"max value : {self.llrf.max_adc_amp:.3f}"
        if phs_exp is None:
            phs_exp = random.randint(-180, 180)
        return amp_exp, phs_exp

    def add_noise(self, array, noise_amp=10):
        array += random.randint(-noise_amp, noise_amp)
        return np.clip(array, -32768, 32767).astype(np.int16)

    def demux_interp_iq(self, array):
        """ Demux I/Q data from 16 to 8 samples, interploate back to 16 """
        x = np.arange(16)
        xp = np.arange(8) * 2
        i_array = np.interp(x, xp, array[0::2])
        q_array = np.interp(x, xp, array[1::2])
        return i_array, q_array

    async def check_sig(self, amp_exp, phs_exp) -> None:
        cocotb.log.warning(
            f"expected mag: {amp_exp:8.2f} cnt,  phs: {phs_exp:8.2f} deg")
        for _ in range(5):
            await RisingEdge(self.dut.clk)
            i_meas = self.dut.llrf_dsp.field_i.value.to_signed()
            q_meas = self.dut.llrf_dsp.field_q.value.to_signed()
            iq_meas = i_meas + 1j * q_meas
            amp_meas = self.dut.amp_measured.value.to_signed()
            amp_meas /= np.abs(self.llrf.rx_gain)
            phs_meas = self.decode_phase(self.dut.phs_measured)
            self.dut._log.debug(
                f"raw IQ   mag: {np.abs(iq_meas):8.2f} cnt,  "
                f"phs: {np.angle(iq_meas, deg=True):8.2f} deg")
            cocotb.log.warning(
                f"measured mag: {amp_meas:8.2f} cnt,  "
                f"phs: {phs_meas:8.2f} deg")
            assert abs(amp_meas - amp_exp) / amp_exp < 0.001, \
                "RX amplitude out-of-bound of 0.1%"
            assert abs(self.wrap_phase(phs_meas - phs_exp)) < 0.1, \
                "RX phase out-of-bound of 0.1 deg"

    async def task_monitor(self, show_feedback=False) -> None:
        for t in itertools.count():
            self.dut._log.info(
                f"s0_axis_tdata:    "
                f"{hex(self.dut.llrf_dsp.s0_axis_tdata.value)}")
            self.dut._log.info(
                f"s1_axis_tdata:    "
                f"{hex(self.dut.llrf_dsp.s1_axis_tdata.value)}")
            self.dut._log.info(
                f"s_axis_tdata_avg: ["
                f"{self.dut.llrf_dsp.s0_axis_tdata_avg.value.to_signed()} "
                f"{self.dut.llrf_dsp.s1_axis_tdata_avg.value.to_signed()}]")
            if t % 20 == 0 and show_feedback:
                amp_meas = self.dut.amp_measured.value.to_signed()
                amp_meas /= np.abs(self.llrf.rx_gain)
                phs_meas = self.decode_phase(self.dut.phs_measured)
                cocotb.log.warning(
                    f"measured amp / phs: [{amp_meas:8.2f} cnt, {phs_meas:8.2f} deg]")
            await RisingEdge(self.dut.clk)

    async def task_loopback(self, delay=2, noise_amp=1) -> None:
        """ Direct loop back from m_axis to s_axis """
        while True:
            # read the controller output (DAC)
            m_axis_dat = await self.read_m_axis()
            await Timer(delay, 'ns')  # cable delay
            i_array, q_array = self.demux_interp_iq(m_axis_dat)
            i_array = self.add_noise(i_array, noise_amp)
            q_array = self.add_noise(q_array, noise_amp)
            # write the system response to the controller input (ADC)
            await self.write_s_axis(i_array, q_array)
            await RisingEdge(self.dut.clk)

    async def task_feedback(self, noise_amp=1) -> None:
        """ Feedback loop from m_axis to s_axis """
        while True:
            # read the controller output (DAC)
            m_axis_dat = await self.read_m_axis()
            i_array, q_array = self.demux_interp_iq(m_axis_dat)
            c_array = i_array + 1j * q_array
            await self.plant.i_queue.put(c_array.mean())  # scalar
            c_out = await self.plant.o_queue.get()
            i_out = c_out.real * np.ones_like(i_array)
            q_out = c_out.imag * np.ones_like(q_array)
            i_out = self.add_noise(i_out, noise_amp)
            q_out = self.add_noise(q_out, noise_amp)
            # write the system response to the controller input (ADC)
            await self.write_s_axis(i_out, q_out)
            await RisingEdge(self.dut.clk)

    async def task_drive_rx(self, i_val, q_val, noise_amp=1) -> None:
        while True:
            ones = np.ones((self.dut.S_AXIS_SAMP_NUM.value,), dtype=np.int16)
            i_array = i_val * ones
            q_array = q_val * ones
            i_array = self.add_noise(i_array, noise_amp)
            q_array = self.add_noise(q_array, noise_amp)
            await self.write_s_axis(i_array, q_array)
            await RisingEdge(self.dut.clk)

    async def test_rx(self, amp_exp=None, phs_exp=None):
        self.log_banner('RX Test')
        amp_exp, phs_exp = await self.init_test(amp_exp, phs_exp)
        i_val, q_val = self.polar_to_rect(amp_exp, phs_exp)
        cocotb.start_soon(self.task_drive_rx(i_val, q_val))
        cocotb.start_soon(self.task_monitor())

        await ClockCycles(self.dut.clk, self.llrf.rx_coupler.pipeline_delay)
        await ClockCycles(self.dut.clk, self.llrf.rx_cordic.pipeline_delay)
        await self.check_sig(amp_exp, phs_exp)

    async def test_open_loop(self, amp_exp=None, phs_exp=None, wait_ns=3):
        self.log_banner('Open Loop Test')
        amp_exp, phs_exp = await self.init_test(amp_exp, phs_exp)
        amp_setp, phs_setp = self.llrf.calc_open_loop_setp(amp_exp, phs_exp)
        await self.init_llrf(amp_setp, phs_setp)
        cocotb.start_soon(self.task_loopback(delay=wait_ns))
        cocotb.start_soon(self.task_monitor())

        await ClockCycles(self.dut.clk, self.llrf.tx_cordic.pipeline_delay)
        await ClockCycles(self.dut.clk, self.llrf.tx_coupler.pipeline_delay)

        await RisingEdge(self.dut.clk)

        await ClockCycles(self.dut.clk, wait_ns // 4)
        await ClockCycles(self.dut.clk, self.llrf.rx_coupler.pipeline_delay)
        await ClockCycles(self.dut.clk, self.llrf.rx_cordic.pipeline_delay)
        await self.check_sig(amp_exp, phs_exp)

    async def close_loops(self) -> None:
        reg_pairs = [
            ('amp_loop_reset', 1),
            ('phs_loop_reset', 1),
            ('amp_loop_enable', 1),
            ('phs_loop_enable', 1),
            ('amp_loop_reset', 0),
            ('phs_loop_reset', 0),
        ]
        for reg, val in reg_pairs:
            await self.write_register(reg, val)

    async def test_close_loop(self, amp_exp=None, phs_exp=None, wait=3000):
        self.log_banner('Close Loop Test')
        amp_exp, phs_exp = await self.init_test(amp_exp, phs_exp)
        assert amp_exp < self.llrf.max_adc_amp * 0.9, \
            f"amp_exp {amp_exp:.3f} too high. " \
            f"max value : {self.llrf.max_adc_amp * 0.9:.3f}"
        amp_setp, phs_setp = self.llrf.calc_close_loop_setp(amp_exp, phs_exp)
        await self.init_llrf(amp_setp, phs_setp)
        cocotb.start_soon(self.task_feedback())
        cocotb.start_soon(self.task_monitor(show_feedback=True))
        await self.close_loops()

        await ClockCycles(self.dut.clk, self.llrf.tx_cordic.pipeline_delay)
        await ClockCycles(self.dut.clk, self.llrf.tx_coupler.pipeline_delay)

        await RisingEdge(self.dut.clk)

        await ClockCycles(self.dut.clk, wait)  # settling time
        await ClockCycles(self.dut.clk, self.llrf.rx_coupler.pipeline_delay)
        await ClockCycles(self.dut.clk, self.llrf.rx_cordic.pipeline_delay)
        await self.check_sig(amp_exp, phs_exp)


@cocotb.test(timeout_time=1, timeout_unit='us')
@cocotb.parametrize(
    amp_exp=[8000, 15000],
    phs_exp=[-100, 45, 270]
)
async def test_rx(dut, amp_exp, phs_exp):
    tb = TB(dut)
    await tb.test_rx(amp_exp, phs_exp)


@cocotb.test(timeout_time=5, timeout_unit='us')
@cocotb.parametrize(
    amp_exp=[8000, 15000],
    phs_exp=[-100, 45, 270]
)
async def test_open_loop(dut, amp_exp, phs_exp):
    tb = TB(dut)
    await tb.test_open_loop(amp_exp, phs_exp)


@cocotb.test(timeout_time=30, timeout_unit='us')
@cocotb.parametrize(
    amp_exp=[8000, 15000],
    phs_exp=[-100, 45, 270]
)
async def test_close_loop(dut, amp_exp, phs_exp):
    tb = TB(dut)
    await tb.test_close_loop(amp_exp, phs_exp)
