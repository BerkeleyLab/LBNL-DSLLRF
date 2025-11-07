#!/usr/local/share/pynq-venv/bin/python
from mimo_mts.overlay import MimoMtsOverlay
import numpy as np
import argparse
from softioc import softioc, builder, asyncio_dispatcher
import asyncio
import os
from contextlib import contextmanager


class MimoMtsIoc:
    def __init__(self, **kwargs) -> None:
        self.ol_name = ol_name = kwargs.get('ol_name', 'MIMO_ZCU208')
        self.prefix = kwargs.get('prefix', ol_name)
        self.ioc_name = ol_name + ':ioc'

    @contextmanager
    def run(self):
        self.init()
        self.create_ioc()
        self.start_ioc()
        try:
            yield
        finally:
            self.ol.free()

    def run_ioc(self):
        with self.run():
            print(self)
            softioc.interactive_ioc(globals())

    def init(self):
        print(f"Initializing IOC with overlay: {self.ol_name}")
        self.ol = MimoMtsOverlay(config=self.ol_name)
        self.llrf_register_map = self.ol.rf_control.register_map
        self.decimation = self.ol.ol_info['ioc']['decimation']
        self.adc_bufs_i, self.adc_bufs_q = self.ol.capture_adc_iq_buf()
        self.n_adc, self.n_samples = self.adc_bufs_i.shape
        self.fs_ghz = self.ol.board.adc_sampling_rate / 1e9
        self.dsp_decimation_factor = self.ol.ol_info['rfdc']['adc_decimation_factor'] * self.decimation
        self.n_dsp_samples = self.n_samples / self.decimation
        self.dsp_fs_ghz = self.fs_ghz / self.dsp_decimation_factor
        self.update_adc_bufs()
        self.init_rf_control()

    def __repr__(self):
        str = f"< {self.__class__.__name__} >:\n"
        str += f"  prefix:      {self.prefix}\n"
        str += f"  ioc_name:    {self.ioc_name}\n"
        str += f"  n_adc:       {self.n_adc}\n"
        str += f"  n_samples:   {self.n_samples}\n"
        str += f"  fs_ghz:      {self.fs_ghz}\n"
        str += f"  n_dsp_samples: {self.n_dsp_samples}\n"
        str += f"  dsp_fs_ghz:  {self.dsp_fs_ghz}\n"
        str += f"  decimation:  {self.decimation}\n"
        str += self.ol.__repr__()
        return str

    def init_rf_control(self):
        """
        Default initialization settings for each OL flavors
        """
        self.llrf_register_map.trig_sel = 0  # internal trigger
        self.llrf_register_map.pulse_length = 4096  # * 4ns
        self.llrf_register_map.trig_period = 250e6
        self.llrf_register_map.trig_delay = 0
        self.llrf_register_map.trig_divide = 1
        self.llrf_register_map.dac_enable = 1
        self.llrf_register_map.amp_loop_setpoint = 0

    def update_adc_bufs(self):
        self.ol.capture_adc_iq_buf(self.adc_bufs_i, self.adc_bufs_q)
        self.adc_bufs_c = self.adc_bufs_i + 1j * self.adc_bufs_q
        self.adc_bufs_mean = self.adc_bufs_c.reshape(self.n_adc, -1, self.decimation).mean(axis=2)

    def encode_2s_comp(self, val):
        """ encode signed integer to 2's complement representation """
        return int(np.binary_repr(val, width=32), 2)

    def create_ioc(self):
        builder.SetDeviceName(self.prefix)
        self.pvs_in = {}
        self.pvs_out = {}
        name = 'ADC:TWF'  # in ns
        self.pvs_in[name] = builder.WaveformIn(
            name, np.arange(0, self.n_samples/self.fs_ghz, 1/self.fs_ghz))
        name = 'DSP:TWF'  # in ns, after decimation
        self.pvs_in[name] = builder.WaveformIn(
            name, np.arange(0, self.n_dsp_samples/self.dsp_fs_ghz, 1/self.dsp_fs_ghz))
        for ix in range(self.n_adc):
            name = f'ADC{ix}:IWF'
            self.pvs_in[name] = builder.WaveformIn(name, self.adc_bufs_i[ix])
            name = f'ADC{ix}:QWF'
            self.pvs_in[name] = builder.WaveformIn(name, self.adc_bufs_q[ix])
            name = f'DSP:ADC{ix}:AWF'
            self.pvs_in[name] = builder.WaveformIn(name, np.abs(self.adc_bufs_mean[ix]))
            name = f'DSP:ADC{ix}:PWF'
            self.pvs_in[name] = builder.WaveformIn(name, np.angle(self.adc_bufs_mean[ix], deg=True))

        self.add_mixer_pvs()
        self.add_rf_control_pvs()

    def add_mixer_pvs(self, prefix='rfdc_mixer:'):
        """
        Add RFDC related PVs to the IOC.
        """
        for name, value in self.ol.mixer_cfg.items():
            self.pvs_in[prefix + name + ':RBV'] = builder.aIn(
                prefix + name + ':RBV', initial_value=value)
            self.pvs_out[prefix + name] = builder.aOut(
                prefix + name, initial_value=value, on_update_name=self.on_update_name)

    def add_rf_control_pvs(self, prefix='rf_control:'):
        """
        Add RF control related PVs to the IOC.
        """
        for name in self.ol.rf_control._registers.keys():
            value = getattr(self.llrf_register_map, name)
            self.pvs_in[prefix + name + ':RBV'] = builder.longIn(
                prefix + name + ':RBV', initial_value=value)
            self.pvs_out[prefix + name] = builder.longOut(
                prefix + name, initial_value=value, on_update_name=self.on_update_name)

    def start_ioc(self):
        dispatcher = asyncio_dispatcher.AsyncioDispatcher()
        builder.LoadDatabase()
        softioc.devIocStats(self.ioc_name)
        # builder.dbLoadDatabase('ioc.db', substitutions=f'P={self.prefix}:')
        softioc.iocInit(dispatcher)
        asyncio.run_coroutine_threadsafe(self.update(), dispatcher.loop)

    async def update(self):
        while True:
            self.update_adc_bufs()
            for ix in range(self.n_adc):
                name = f'ADC{ix}:IWF'
                self.pvs_in[name].set(self.adc_bufs_i[ix])
                name = f'ADC{ix}:QWF'
                self.pvs_in[name].set(self.adc_bufs_q[ix])
                name = f'DSP:ADC{ix}:AWF'
                self.pvs_in[name].set(np.abs(self.adc_bufs_mean[ix]))
                name = f'DSP:ADC{ix}:PWF'
                self.pvs_in[name].set(np.angle(self.adc_bufs_mean[ix], deg=True))
            for name in self.ol.rf_control._registers.keys():
                value = getattr(self.llrf_register_map, name)
                self.pvs_in[f'rf_control:{name}:RBV'].set(value)
            for name, value in self.ol.mixer_cfg.items():
                self.pvs_in[f'rfdc_mixer:{name}:RBV'].set(value)
            await asyncio.sleep(0.5)

    def on_update_name(self, value, pv_name):
        """
        Callback for when a PV is updated.
        This method updates the overlay's register map or mixer settings based on the PV name.
        """
        if pv_name.startswith(f'{self.prefix}:rf_control:'):
            name = pv_name.split(':')[-1]
            signed_value = self.encode_2s_comp(value)  # XXX add "signed" field for each register
            if hasattr(self.llrf_register_map, name):
                setattr(self.llrf_register_map, name, signed_value)
            else:
                print(f"Warning: {name} not found in llrf_register_map.")
        elif pv_name.startswith(f'{self.prefix}:rfdc_mixer:'):
            name = pv_name.split(':')[-1]
            if name == 'dac_mixer_nco_freq_mhz':
                nyquist = self.ol.mixer_cfg['dac_mixer_nco_nyquist']
                phase = self.ol.mixer_cfg['dac_mixer_nco_phase']
                print(f"Setting DAC mixer NCO frequency: {value} MHz, Nyquist: {nyquist}, Phase: {phase}")
                self.ol.set_dac_mixer(value, nyquist, phase)
            elif name == 'adc_mixer_nco_freq_mhz':
                nyquist = self.ol.mixer_cfg['adc_mixer_nco_nyquist']
                phase = self.ol.mixer_cfg['adc_mixer_nco_phase']
                print(f"Setting ADC mixer NCO frequency: {value} MHz, Nyquist: {nyquist}, Phase: {phase}")
                self.ol.set_adc_mixer(value, nyquist, phase)

    def drive_test_awg(self):
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


def mimo_auto_ioc():
    ol_name = 'MIMO' + '_' + os.environ['BOARD']
    ioc = MimoMtsIoc(ol_name=ol_name)
    ioc.run_ioc()


def main():
    parser = argparse.ArgumentParser(description="soft IOC")
    parser.add_argument('--prefix', default="MIMO", help="$(P)")
    parser.add_argument('--ol_name', default="MIMO", help="overlay config",
                        choices=['MIMO_ZCU208', 'MIMO_ZCU216', 'ALS_LLRF_ZCU208', 'ALS_LLRF_LBL208'])
    args = parser.parse_args()
    ioc = MimoMtsIoc(**vars(args))
    ioc.run_ioc()


if __name__ == "__main__":
    main()
