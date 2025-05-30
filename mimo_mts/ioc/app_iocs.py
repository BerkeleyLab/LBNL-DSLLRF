#!/usr/local/share/pynq-venv/bin/python
from mimo_mts.ioc.base_ioc import MimoMtsIoc
import os
import numpy as np


class AlsLlrfZCU208(MimoMtsIoc):
    def __init__(self, **kwargs):
        assert os.environ['BOARD'] == 'ZCU208', "This IOC is only for ZCU208 board."
        kwargs.setdefault('ol_name', 'ALS_LLRF_ZCU208')
        super().__init__(**kwargs)

    def init_rf_control(self):
        self.llrf_register_map.trig_sel = 0  # internal trigger
        self.llrf_register_map.pulse_length = 4096  # * 4ns
        self.llrf_register_map.trig_period = 250e6
        self.llrf_register_map.trig_delay = 0
        self.llrf_register_map.trig_divide = 1
        self.llrf_register_map.dac_enable = 1
        # Set 50% maximum RF amplitude
        self.llrf_register_map.amp_loop_setpoint = 32767 / self.ol.rf_control.tx_gain / 2
        self.llrf_register_map.dac_enable.pulse_enable = 1
        self.llrf_register_map.pulse_length = 100


class AlsLlrfLBL208(MimoMtsIoc):
    def __init__(self, **kwargs):
        assert os.environ['BOARD'] == 'ZCU208', "This IOC is only for LBL208 board."
        kwargs.setdefault('ol_name', 'ALS_LLRF_LBL208')
        super().__init__(**kwargs)

    def init_rf_control(self):
        self.llrf_register_map.trig_sel = 1  # EVR trigger
        self.llrf_register_map.pulse_length = 4096  # * 4ns
        self.llrf_register_map.trig_period = 250e6
        self.llrf_register_map.trig_delay = 0
        self.llrf_register_map.trig_divide = 1
        self.llrf_register_map.dac_enable = 1
        # Set 50% maximum RF amplitude
        self.llrf_register_map.amp_loop_setpoint = 32767 / self.ol.rf_control.tx_gain / 2
        self.llrf_register_map.dac_enable.pulse_enable = 1
        self.llrf_register_map.pulse_length = 100


class MimoZCU208(MimoMtsIoc):
    def __init__(self, **kwargs):
        assert os.environ['BOARD'] == 'ZCU208', "This IOC is only for ZCU208 board."
        kwargs.setdefault('ol_name', 'MIMO_ZCU208')
        super().__init__(**kwargs)

    def init_rf_control(self):
        super().init_rf_control()
        # Drive DAC with a test arbitrary waveform
        Fc = self.fs_ghz / 16  # 250 MHz
        t = np.arange(self.ol.dac_player.size) / self.fs_ghz  # ns
        amp = 2**14 - 1
        dac_wfm = np.exp(1j * 2 * np.pi * Fc * t) * amp
        # dac_i = np.ones(self.ol.dac_player.size//2, dtype=np.int16) * 32767
        dac_wfm = dac_wfm[::2]  # decimate by 2
        dac_i = (dac_wfm.real).astype(np.int16)
        dac_q = (dac_wfm.imag).astype(np.int16)
        self.ol.write_dac_iq_buf(dac_i, dac_q)


class MimoLBL208(MimoMtsIoc):
    def __init__(self, **kwargs):
        assert os.environ['BOARD'] == 'ZCU208', "This IOC is only for LBL208 board."
        kwargs.setdefault('ol_name', 'MIMO_LBL208')
        super().__init__(**kwargs)


class MimoZCU216(MimoMtsIoc):
    def __init__(self, **kwargs):
        assert os.environ['BOARD'] == 'ZCU216', "This IOC is only for ZCU216 board."
        kwargs.setdefault('ol_name', 'MIMO_ZCU216')
        super().__init__(**kwargs)

    def init_rf_control(self):
        super().init_rf_control()
        # Drive DAC with a constant signal
        Fc = self.fs_ghz / 16  # 250 MHz
        t = np.arange(self.ol.dac_player.size) / self.fs_ghz  # ns
        amp = 2**14 - 1
        dac_wfm = np.exp(1j * 2 * np.pi * Fc * t) * amp
        # dac_i = np.ones(self.ol.dac_player.size//2, dtype=np.int16) * 32767
        dac_wfm = dac_wfm[::2]  # decimate by 2
        dac_i = (dac_wfm.real).astype(np.int16)
        dac_q = (dac_wfm.imag).astype(np.int16)
        self.ol.write_dac_iq_buf(dac_i, dac_q)


def llrf_zcu208_ioc():
    ioc = AlsLlrfZCU208()
    ioc.run_ioc()


def llrf_lbl208_ioc():
    ioc = AlsLlrfLBL208()
    ioc.run_ioc()


def mimo_zcu208_ioc():
    ioc = MimoZCU208()
    ioc.run_ioc()


def mimo_lbl208_ioc():
    ioc = MimoLBL208()
    ioc.run_ioc()


def mimo_zcu216_ioc():
    ioc = MimoZCU216()
    ioc.run_ioc()
