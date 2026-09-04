#!/usr/local/share/pynq-venv/bin/python
import re
import time
import logging
import threading
from mimo_mts.overlay import MimoMtsOverlay
import numpy as np
import argparse
from softioc import softioc, builder, asyncio_dispatcher
import asyncio
import os
from contextlib import contextmanager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class MimoMtsIoc:
    def __init__(self, **kwargs) -> None:
        self.log_level = kwargs.get('log_level', logging.INFO)
        logger.setLevel(self.log_level)
        self.ol = kwargs.get('ol', None)
        self.ol_name = ol_name = kwargs.get('ol_name', 'MIMO_ZCU208')
        self.prefix = kwargs.get('prefix', ol_name)
        self.ioc_name = ol_name + ':ioc'
        self.init()

    @contextmanager
    def run(self):
        self.create_ioc()
        self.start_ioc()
        try:
            yield
        finally:
            self.ol.free()

    def run_ioc(self):
        with self.run():
            logger.info(self)
            softioc.interactive_ioc(globals())

    def init(self):
        if self.ol is None:
            logger.info("Initializing IOC with overlay: %s", self.ol_name)
            self.ol = MimoMtsOverlay(config=self.ol_name)
        else:
            logger.info("Using provided overlay for IOC: %s", self.ol_name)

        self.llrf_register_map = self.ol.rf_control.register_map
        self.decimation = self.ol.ol_info['ioc']['decimation']
        self.adc_bufs_i, self.adc_bufs_q = self.ol.capture_adc_iq_buf()
        self.n_adc, self.n_samples = self.adc_bufs_i.shape
        self.adc_fs_ghz = self.ol.adc_sampling_rate / 1e9
        self.dac_fs_ghz = self.ol.dac_sampling_rate / 1e9
        self.dsp_decimation_factor = self.ol.ol_info['rfdc']['adc_decimation_factor'] * self.decimation
        self.n_dsp_samples = self.n_samples / self.decimation
        self.dsp_fs_ghz = self.adc_fs_ghz / self.dsp_decimation_factor
        self.init_rf_control()
        self.update_adc_bufs()
        self._init_per_channel_mixer_cfg()

    def _init_per_channel_mixer_cfg(self):
        """Initialize per-channel mixer config from the global defaults."""
        self.adc_mixer_cfg = {}
        for ch in range(self.ol.board.n_adcs):
            self.adc_mixer_cfg[ch] = {
                'freq_mhz': self.ol.adc_mixer_nco_freq_mhz,
                'nyquist': self.ol.adc_mixer_nco_nyquist,
                'phase': self.ol.adc_mixer_nco_phase,
            }
        self.dac_mixer_cfg = {}
        for ch in range(self.ol.board.n_dacs):
            self.dac_mixer_cfg[ch] = {
                'freq_mhz': self.ol.dac_mixer_nco_freq_mhz,
                'nyquist': self.ol.dac_mixer_nco_nyquist,
                'phase': self.ol.dac_mixer_nco_phase,
            }

    def __repr__(self):
        str = f"< {self.__class__.__name__} >:\n"
        str += f"  prefix:      {self.prefix}\n"
        str += f"  ioc_name:    {self.ioc_name}\n"
        str += f"  n_adc:       {self.n_adc}\n"
        str += f"  n_samples:   {self.n_samples}\n"
        str += f"  adc_fs_ghz:  {self.adc_fs_ghz}\n"
        str += f"  dac_fs_ghz:  {self.dac_fs_ghz}\n"
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
        self.llrf_register_map.pulse_length = 0xfff  # * 4ns
        self.llrf_register_map.trig_period = 125e6
        self.llrf_register_map.trig_delay = 0
        self.llrf_register_map.trig_divide = 1
        self.llrf_register_map.dac_enable = 1
        self.llrf_register_map.amp_loop_setpoint = 0

    def update_adc_bufs(self):
        self.ol.capture_adc_iq_buf(self.adc_bufs_i, self.adc_bufs_q)
        self.adc_bufs_c = self.adc_bufs_i + 1j * self.adc_bufs_q
        self.adc_bufs_mean = self.adc_bufs_c.reshape(self.n_adc, -1, self.decimation).mean(axis=2)

    def update_adc_bufs_with_pvs(self):
        self.update_adc_bufs()
        for ix in range(self.n_adc):
            self.pvs_in[f'ADC{ix}:IWF'].set(self.adc_bufs_i[ix])
            self.pvs_in[f'ADC{ix}:QWF'].set(self.adc_bufs_q[ix])
            self.pvs_in[f'DSP:ADC{ix}:AWF'].set(np.abs(self.adc_bufs_mean[ix]))
            self.pvs_in[f'DSP:ADC{ix}:PWF'].set(np.angle(self.adc_bufs_mean[ix], deg=True))

    def encode_2s_comp(self, val):
        """ encode signed integer to 2's complement representation """
        return int(np.binary_repr(val, width=32), 2)

    def create_ioc(self):
        builder.SetDeviceName(self.prefix)
        self.pvs_in = {}
        self.pvs_out = {}

        name = 'ADC:TWF'  # in ns
        self.pvs_in[name] = builder.WaveformIn(
            name, np.arange(0, self.n_samples/self.adc_fs_ghz, 1/self.adc_fs_ghz))
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
        Add per-channel and global RFDC mixer PVs to the IOC.
        Per-channel PVs:
            rfdc_mixer:ADC{ch}:nco_freq_mhz
            rfdc_mixer:ADC{ch}:nco_nyquist
            rfdc_mixer:ADC{ch}:nco_phase
            rfdc_mixer:DAC{ch}:nco_freq_mhz
            rfdc_mixer:DAC{ch}:nco_nyquist
            rfdc_mixer:DAC{ch}:nco_phase
        Global PVs (set all channels at once):
            rfdc_mixer:adc_mixer_nco_freq_mhz
            rfdc_mixer:adc_mixer_nco_nyquist
            rfdc_mixer:adc_mixer_nco_phase
            rfdc_mixer:dac_mixer_nco_freq_mhz
            rfdc_mixer:dac_mixer_nco_nyquist
            rfdc_mixer:dac_mixer_nco_phase
        """
        # Global PVs (apply to all channels at once)
        for name, value in self.ol.mixer_cfg.items():
            self.pvs_in[prefix + name + ':RBV'] = builder.aIn(
                prefix + name + ':RBV', initial_value=value)
            self.pvs_out[prefix + name] = builder.aOut(
                prefix + name, initial_value=value, on_update_name=self.on_update_name)

        # Per-channel ADC mixer PVs
        for ch, cfg in self.adc_mixer_cfg.items():
            for key in cfg.keys():
                name = f'ADC{ch}:nco_{key}'
                value = self.adc_mixer_cfg[ch][key]
                self.pvs_in[prefix + name + ':RBV'] = builder.aIn(
                    prefix + name + ':RBV', initial_value=value)
                self.pvs_out[prefix + name] = builder.aOut(
                    prefix + name, initial_value=value, on_update_name=self.on_update_name)

        # Per-channel DAC mixer PVs
        for ch, cfg in self.dac_mixer_cfg.items():
            for key in cfg.keys():
                name = f'DAC{ch}:nco_{key}'
                value = self.dac_mixer_cfg[ch][key]
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
        loop = asyncio.get_event_loop()  # required for IRQ!
        if not loop.is_running():
            threading.Thread(target=loop.run_forever, daemon=True).start()

        self.dispatcher = dispatcher = asyncio_dispatcher.AsyncioDispatcher(loop=loop)
        builder.LoadDatabase()
        softioc.devIocStats(self.ioc_name)
        # builder.dbLoadDatabase('ioc.db', substitutions=f'P={self.prefix}:')
        softioc.iocInit(dispatcher)

        # dispatcher.loop is initialized in a background thread by AsyncioDispatcher
        loop = dispatcher.loop
        if hasattr(self.ol, 'write_done_irq'):
            asyncio.run_coroutine_threadsafe(self.isr_update_adc_bufs(), loop)
        asyncio.run_coroutine_threadsafe(self.update_registers(), loop)

    async def isr_update_adc_bufs(self):
        """Interrupt service routine to update ADC buffers and waveform PVs."""
        irq = self.ol.write_done_irq
        t0 = time.perf_counter()
        while True:
            await irq.wait()
            t1 = time.perf_counter()
            self.update_adc_bufs_with_pvs()
            logger.debug("%s IRQ!, time since last: %.6f s", self.ioc_name, t1-t0)
            t0 = t1

    async def update_registers(self):
        """Periodically update register RBV PVs."""
        while True:
            await asyncio.sleep(0.5)

            # If no interrupt is used, we still need to update ADC buffers
            if not hasattr(self.ol, 'write_done_irq'):
                self.update_adc_bufs_with_pvs()

            logger.debug("%s Updating register RBVs", self.ioc_name)
            for name in self.ol.rf_control._registers.keys():
                value = getattr(self.llrf_register_map, name)
                self.pvs_in[f'rf_control:{name}:RBV'].set(value)

            # Update global mixer RBVs
            for name, value in self.ol.mixer_cfg.items():
                self.pvs_in[f'rfdc_mixer:{name}:RBV'].set(value)

            # Update per-channel mixer RBVs
            for ch, cfg in self.adc_mixer_cfg.items():
                for key in cfg.keys():
                    self.pvs_in[f'rfdc_mixer:ADC{ch}:nco_{key}:RBV'].set(cfg[key])

            for ch, cfg in self.dac_mixer_cfg.items():
                for key in cfg.keys():
                    self.pvs_in[f'rfdc_mixer:DAC{ch}:nco_{key}:RBV'].set(cfg[key])

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
                logger.warning("%s not found in llrf_register_map.", name)

        elif pv_name.startswith(f'{self.prefix}:rfdc_mixer:'):
            field = pv_name.removeprefix(f'{self.prefix}:rfdc_mixer:')

            # Per-channel ADC/DAC: e.g., "ADC0:nco_freq_mhz"
            match = re.match(r'^(?P<type>ADC|DAC)(?P<ch>\d+):nco_(?P<param>freq_mhz|nyquist|phase)$', field)
            if match:
                ch_type = match.group('type')
                ch = int(match.group('ch'))
                param = match.group('param')

                configs, setter = {
                    'ADC': (self.adc_mixer_cfg, self.ol.set_adc_mixer_ch),
                    'DAC': (self.dac_mixer_cfg, self.ol.set_dac_mixer_ch)
                }[ch_type]

                try:
                    cfg = configs[ch]
                    cfg[param] = value

                    logger.info("Setting %s ch%d mixer: freq=%s MHz, nyquist=%s, phase=%s",
                                ch_type, ch, cfg['freq_mhz'], cfg['nyquist'], cfg['phase'])
                    setter(ch, cfg['freq_mhz'], int(cfg['nyquist']), cfg['phase'])
                except (KeyError, IndexError, ValueError) as e:
                    logger.error("Error updating %s with value %s: %s", field, value, e)

            # Global ADC: use set_adc_mixer() — all channels, synchronized
            elif field.startswith('adc_mixer_nco_'):
                logger.info("Setting ALL ADC mixers: field=%s, value=%s", field, value)
                setattr(self.ol, field, value)  # call self.ol.set_adc_mixer()
                # Update per-channel configs and PVs
                for ch, cfg in self.adc_mixer_cfg.items():
                    cfg['freq_mhz'] = self.ol.adc_mixer_nco_freq_mhz
                    cfg['nyquist'] = self.ol.adc_mixer_nco_nyquist
                    cfg['phase'] = self.ol.adc_mixer_nco_phase
                    self.pvs_out[f'rfdc_mixer:ADC{ch}:nco_freq_mhz'].set(cfg['freq_mhz'])
                    self.pvs_out[f'rfdc_mixer:ADC{ch}:nco_nyquist'].set(cfg['nyquist'])
                    self.pvs_out[f'rfdc_mixer:ADC{ch}:nco_phase'].set(cfg['phase'])

            # Global DAC: use set_dac_mixer() — all channels, synchronized
            elif field.startswith('dac_mixer_nco_'):
                logger.info("Setting ALL DAC mixers: field=%s, value=%s", field, value)
                setattr(self.ol, field, value)  # call self.ol.set_dac_mixer()
                # Update per-channel configs and PVs
                for ch, cfg in self.dac_mixer_cfg.items():
                    cfg['freq_mhz'] = self.ol.dac_mixer_nco_freq_mhz
                    cfg['nyquist'] = self.ol.dac_mixer_nco_nyquist
                    cfg['phase'] = self.ol.dac_mixer_nco_phase
                    self.pvs_out[f'rfdc_mixer:DAC{ch}:nco_freq_mhz'].set(cfg['freq_mhz'])
                    self.pvs_out[f'rfdc_mixer:DAC{ch}:nco_nyquist'].set(cfg['nyquist'])
                    self.pvs_out[f'rfdc_mixer:DAC{ch}:nco_phase'].set(cfg['phase'])

    def drive_test_awg(self):
        """ Drive DAC with a test arbitrary waveform """
        f_c = self.fs_ghz / 16  # 250 MHz
        t = np.arange(self.ol.dac_player.size) / self.fs_ghz  # ns
        amp = 2**14 - 1
        # interp_factor = ol.ol_info['rfdc']['dac_interpolation_factor']
        dac_wfm = np.exp(1j * 2 * np.pi * f_c * t) * amp
        # dac_i = np.ones(self.ol.dac_player.size//2, dtype=np.int16) * 32767
        dac_wfm = dac_wfm[::2]  # decimate by 2
        dac_i = (dac_wfm.real).astype(np.int16)
        dac_q = (dac_wfm.imag).astype(np.int16)
        self.ol.write_dac_iq_buf(dac_i, dac_q)

    def drive_ones_awg(self):
        """ Drive DAC with all ones, for testing purposes. """
        dac_i = np.ones(self.ol.dac_player.size//2, dtype=np.int16) * 32767
        dac_q = np.zeros_like(dac_i)
        self.ol.write_dac_iq_buf(dac_i, dac_q)


def mimo_auto_ioc():
    ol_name = 'MIMO' + '_' + os.environ['BOARD']
    ioc = MimoMtsIoc(ol_name=ol_name)
    ioc.run_ioc()


def main():
    parser = argparse.ArgumentParser(description="soft IOC")
    parser.add_argument('--prefix', default="MIMO", help="$(P)")
    parser.add_argument('--ol_name', default="MIMO", help="overlay config",
                        choices=['MIMO_ZCU208', 'MIMO_ZCU216', 'ALS_LLRF_ZCU208',
                                 'ALS_LLRF_LBL208'])
    args = parser.parse_args()
    ioc = MimoMtsIoc(**vars(args))
    ioc.run_ioc()


if __name__ == "__main__":
    main()
