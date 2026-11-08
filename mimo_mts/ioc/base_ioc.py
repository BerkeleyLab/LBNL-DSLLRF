#!/usr/local/share/pynq-venv/bin/python
import argparse
import asyncio
import logging
import os
import re
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import numpy as np
from softioc import asyncio_dispatcher, builder, softioc

from mimo_mts.drivers.adc_calibration import DEFAULT_CAL_FILE
from mimo_mts.overlay import MimoMtsOverlay

logging.basicConfig(level=logging.INFO, format="%(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class MimoMtsIoc:
    def __init__(self, **kwargs) -> None:
        self.log_level = kwargs.get("log_level", logging.INFO)
        logger.setLevel(self.log_level)
        self.ol_name = ol_name = kwargs.get("ol_name", "MIMO_ZCU208")
        self.prefix = kwargs.get("prefix", ol_name)
        self.ioc_name = ol_name + ":ioc"
        self.ol: MimoMtsOverlay = self._load_overlay(kwargs.get("ol"))
        self.adc_cal_file = Path(kwargs.get("adc_cal_file", DEFAULT_CAL_FILE))
        self.adc_cal_status = "not initialized"
        self.init()

    def _load_overlay(self, ol: MimoMtsOverlay | None) -> MimoMtsOverlay:
        """Use the overlay passed in, or load ``self.ol_name``."""
        if ol is None:
            logger.info("Initializing IOC with overlay: %s", self.ol_name)
            return MimoMtsOverlay(config=self.ol_name, log_level=self.log_level)
        logger.info("Using provided overlay for IOC: %s", self.ol_name)
        return ol

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
        self.llrf_register_map = self.ol.rf_control.register_map
        self.decimation = self.ol.ol_info["ioc"]["decimation"]
        self.adc_bufs_i, self.adc_bufs_q = self.ol.capture_adc_iq_buf()
        self.n_adc, self.n_samples = self.adc_bufs_i.shape
        self.adc_fs_ghz = self.ol.adc_sampling_rate / 1e9
        self.dac_fs_ghz = self.ol.dac_sampling_rate / 1e9
        self.dsp_decimation_factor = self.ol.ol_info["rfdc"]["adc_decimation_factor"] * self.decimation
        self.n_dsp_samples = self.n_samples / self.decimation
        self.dsp_fs_ghz = self.adc_fs_ghz / self.dsp_decimation_factor
        self.dsp_clk_ns = 1 / self.dsp_fs_ghz
        self.adc_pulse_start_ns = np.ones(self.n_adc, dtype=np.int32) * 1000
        self.adc_pulse_end_ns = np.ones(self.n_adc, dtype=np.int32) * 1000
        self.init_rf_control()
        self.update_adc_bufs()
        self._init_per_channel_mixer_cfg()
        if hasattr(self.ol, "adc_cal"):
            self.init_adc_cal()

    def _init_per_channel_mixer_cfg(self):
        """Initialize per-channel mixer config from the global defaults."""
        self.adc_mixer_cfg = {}
        for ch in range(self.ol.board.n_adcs):
            self.adc_mixer_cfg[ch] = {
                "freq_mhz": self.ol.adc_mixer_nco_freq_mhz,
                "nyquist": self.ol.adc_mixer_nco_nyquist,
                "phase": self.ol.adc_mixer_nco_phase,
            }
        self.dac_mixer_cfg = {}
        for ch in range(self.ol.board.n_dacs):
            self.dac_mixer_cfg[ch] = {
                "freq_mhz": self.ol.dac_mixer_nco_freq_mhz,
                "nyquist": self.ol.dac_mixer_nco_nyquist,
                "phase": self.ol.dac_mixer_nco_phase,
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
        self.llrf_register_map.pulse_length = 0xFFF  # * 4ns
        self.llrf_register_map.trig_period = 125e6
        self.llrf_register_map.trig_delay = 0
        self.llrf_register_map.trig_divide = 1
        self.llrf_register_map.dac_enable = 1
        self.llrf_register_map.amp_loop_setpoint = 0

    def init_adc_cal(self):
        """
        RF-ADC calibration policy at IOC start. Default: leave the ADCs as RF-ADC startup
        left them (background calibration tracking). Applications override this.
        """
        frozen = self.ol.adc_cal.is_frozen()
        self.adc_cal_status = f"startup state, frozen: {[ch for ch, f in frozen.items() if f]}"
        logger.info("ADC calibration %s", self.adc_cal_status)

    def restore_adc_cal(self):
        """Restore GCB/TSCB from ``self.adc_cal_file`` and freeze; never raises, reports via status."""
        try:
            mismatches = self.ol.adc_cal.restore(self.adc_cal_file)
        except (OSError, KeyError, ValueError, RuntimeError) as e:
            self.adc_cal_status = f"restore failed: {e}"
            logger.error("ADC calibration %s", self.adc_cal_status)
            return False
        bad = [ch for ch, m in mismatches.items() if m]
        self.adc_cal_status = f"restore verify failed on ADC {bad}" if bad else f"restored from {self.adc_cal_file}"
        return not bad

    def update_adc_bufs(self):
        self.ol.capture_adc_iq_buf(self.adc_bufs_i, self.adc_bufs_q)
        self.adc_bufs_c = self.adc_bufs_i + 1j * self.adc_bufs_q
        self.adc_bufs_mean = self.adc_bufs_c.reshape(self.n_adc, -1, self.decimation).mean(axis=2)

    def update_adc_bufs_with_pvs(self):
        self.update_adc_bufs()
        for ix in range(self.n_adc):
            self.pvs_in[f"ADC{ix}:IWF"].set(self.adc_bufs_i[ix])
            self.pvs_in[f"ADC{ix}:QWF"].set(self.adc_bufs_q[ix])
            self.pvs_in[f"DSP:ADC{ix}:AWF"].set(np.abs(self.adc_bufs_mean[ix]))
            self.pvs_in[f"DSP:ADC{ix}:PWF"].set(np.angle(self.adc_bufs_mean[ix], deg=True))
            start = int(self.adc_pulse_start_ns[ix] // self.dsp_clk_ns)
            end = int(self.adc_pulse_end_ns[ix] // self.dsp_clk_ns)
            if end > start:
                pulse_data = self.adc_bufs_mean[ix][start:end]
                self.pvs_in[f"DSP:ADC{ix}:pulse_stat:amp:mean"].set(np.abs(pulse_data).mean())
                self.pvs_in[f"DSP:ADC{ix}:pulse_stat:amp:std"].set(np.abs(pulse_data).std())
                self.pvs_in[f"DSP:ADC{ix}:pulse_stat:phs:mean"].set(np.angle(pulse_data, deg=True).mean())
                self.pvs_in[f"DSP:ADC{ix}:pulse_stat:phs:std"].set(np.angle(pulse_data, deg=True).std())

    def encode_2s_comp(self, val):
        """encode signed integer to 2's complement representation"""
        return int(np.binary_repr(val, width=32), 2)

    def create_ioc(self):
        builder.SetDeviceName(self.prefix)
        self.pvs_in = {}
        self.pvs_out = {}

        name = "ADC:TWF"  # in ns
        self.pvs_in[name] = builder.WaveformIn(
            name, np.arange(0, self.n_samples / self.adc_fs_ghz, 1 / self.adc_fs_ghz)
        )
        name = "DSP:TWF"  # in ns, after decimation
        self.pvs_in[name] = builder.WaveformIn(
            name, np.arange(0, self.n_dsp_samples / self.dsp_fs_ghz, 1 / self.dsp_fs_ghz)
        )

        for ix in range(self.n_adc):
            name = f"ADC{ix}:IWF"
            self.pvs_in[name] = builder.WaveformIn(name, self.adc_bufs_i[ix])
            name = f"ADC{ix}:QWF"
            self.pvs_in[name] = builder.WaveformIn(name, self.adc_bufs_q[ix])
            name = f"DSP:ADC{ix}:AWF"
            self.pvs_in[name] = builder.WaveformIn(name, np.abs(self.adc_bufs_mean[ix]))
            name = f"DSP:ADC{ix}:PWF"
            self.pvs_in[name] = builder.WaveformIn(name, np.angle(self.adc_bufs_mean[ix], deg=True))

        self.add_mixer_pvs()
        self.add_rf_control_pvs()
        self.add_pulse_pvs()
        if hasattr(self.ol, "adc_cal"):
            self.add_adc_cal_pvs()

    def add_adc_cal_pvs(self, prefix="adc_cal:"):
        """
        RF-ADC calibration PVs (see mimo_mts/drivers/adc_calibration.py):
            adc_cal:freeze               write 1/0 to freeze/unfreeze GCB+TSCB on all ADCs
            adc_cal:ADC{ch}:freeze       same, one ADC
            adc_cal:ADC{ch}:frozen:RBV   freeze status reported by the RFDC
            adc_cal:save                 write 1 to save all coefficients to adc_cal:file
            adc_cal:restore              write 1 to restore GCB+TSCB from adc_cal:file and freeze
            adc_cal:release_override     write 1 to return all blocks to engine-computed values
            adc_cal:file                 calibration file path on the board
            adc_cal:status               result of the last action
        """
        cal = self.ol.adc_cal
        self.pvs_out[prefix + "freeze"] = builder.boolOut(
            prefix + "freeze",
            ZNAM="tracking",
            ONAM="frozen",
            always_update=True,
            on_update=lambda v: self._adc_cal_action("freeze" if v else "unfreeze"),
        )
        for ch in cal.channels:
            name = f"{prefix}ADC{ch}:freeze"
            self.pvs_out[name] = builder.boolOut(
                name,
                ZNAM="tracking",
                ONAM="frozen",
                always_update=True,
                on_update=lambda v, ch=ch: self._adc_cal_action("freeze" if v else "unfreeze", ch),
            )
            name = f"{prefix}ADC{ch}:frozen:RBV"
            self.pvs_in[name] = builder.boolIn(name, ZNAM="tracking", ONAM="frozen")

        for action in ("save", "restore", "release_override"):
            self.pvs_out[prefix + action] = builder.boolOut(
                prefix + action,
                ZNAM="idle",
                ONAM="run",
                always_update=True,
                on_update=lambda v, action=action: v and self._adc_cal_action(action),
            )
        self.pvs_in[prefix + "file"] = builder.longStringIn(prefix + "file", initial_value=str(self.adc_cal_file))
        self.pvs_in[prefix + "status"] = builder.longStringIn(prefix + "status", initial_value=self.adc_cal_status)

    def _adc_cal_action(self, action, ch=None):
        cal = self.ol.adc_cal
        try:
            if action == "freeze":
                cal.freeze(ch)
                self.adc_cal_status = f"frozen ADC {'all' if ch is None else ch}"
            elif action == "unfreeze":
                cal.unfreeze(ch)
                self.adc_cal_status = f"tracking ADC {'all' if ch is None else ch}"
            elif action == "save":
                cal.save(self.adc_cal_file)
                self.adc_cal_status = f"saved to {self.adc_cal_file}"
            elif action == "restore":
                self.restore_adc_cal()
            elif action == "release_override":
                cal.release_override()
                self.adc_cal_status = "override released"
        except (OSError, KeyError, ValueError, RuntimeError) as e:
            self.adc_cal_status = f"{action} failed: {e}"
            logger.error("ADC calibration %s", self.adc_cal_status)
        self.pvs_in["adc_cal:status"].set(self.adc_cal_status)
        self.update_adc_cal_pvs()

    def update_adc_cal_pvs(self):
        for ch, frozen in self.ol.adc_cal.is_frozen().items():
            self.pvs_in[f"adc_cal:ADC{ch}:frozen:RBV"].set(frozen)

    def add_mixer_pvs(self, prefix="rfdc_mixer:"):
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
            self.pvs_in[prefix + name + ":RBV"] = builder.aIn(prefix + name + ":RBV", initial_value=value)
            self.pvs_out[prefix + name] = builder.aOut(
                prefix + name, initial_value=value, on_update_name=self.on_update_name
            )

        # Per-channel ADC mixer PVs
        for ch, cfg in self.adc_mixer_cfg.items():
            for key in cfg.keys():
                name = f"ADC{ch}:nco_{key}"
                value = self.adc_mixer_cfg[ch][key]
                self.pvs_in[prefix + name + ":RBV"] = builder.aIn(prefix + name + ":RBV", initial_value=value)
                self.pvs_out[prefix + name] = builder.aOut(
                    prefix + name, initial_value=value, on_update_name=self.on_update_name
                )

        # Per-channel DAC mixer PVs
        for ch, cfg in self.dac_mixer_cfg.items():
            for key in cfg.keys():
                name = f"DAC{ch}:nco_{key}"
                value = self.dac_mixer_cfg[ch][key]
                self.pvs_in[prefix + name + ":RBV"] = builder.aIn(prefix + name + ":RBV", initial_value=value)
                self.pvs_out[prefix + name] = builder.aOut(
                    prefix + name, initial_value=value, on_update_name=self.on_update_name
                )

    def add_rf_control_pvs(self, prefix="rf_control:"):
        """
        Add RF control related PVs to the IOC.
        """
        for name in self.ol.rf_control._registers.keys():
            value = getattr(self.llrf_register_map, name)
            self.pvs_in[prefix + name + ":RBV"] = builder.longIn(prefix + name + ":RBV", initial_value=value)
            self.pvs_out[prefix + name] = builder.longOut(
                prefix + name, initial_value=value, on_update_name=self.on_update_name
            )

    def add_pulse_pvs(self, prefix="pulse_stat:"):
        """
        Add pulse amplitude and phase statistics, after start_ns and before end_ns
        DSP:ADC?:pulse_stat:start_ns
        DSP:ADC?:pulse_stat:end_ns
        DSP:ADC?:pulse_stat:amp:mean
        DSP:ADC?:pulse_stat:amp:std
        DSP:ADC?:pulse_stat:phs:mean
        DSP:ADC?:pulse_stat:phs:std
        """
        for ix in range(self.n_adc):
            for s in ["start_ns", "end_ns"]:
                name = f"DSP:ADC{ix}:{prefix}{s}"
                self.pvs_out[name] = builder.longOut(
                    name, DRVL=0, DRVH=16380, EGU="ns", initial_value=1000, on_update_name=self.on_update_name
                )
            for p in ["mean", "std"]:
                name = f"DSP:ADC{ix}:{prefix}amp:{p}"
                self.pvs_in[name] = builder.aIn(name, LOPR=0, HOPR=32768, EGU="cnt", initial_value=0)
                name = f"DSP:ADC{ix}:{prefix}phs:{p}"
                self.pvs_in[name] = builder.aIn(name, LOPR=-180, HOPR=180, EGU="deg", initial_value=0)

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
        if hasattr(self.ol, "write_done_irq"):
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
            logger.debug("%s IRQ!, time since last: %.6f s", self.ioc_name, t1 - t0)
            t0 = t1

    async def update_registers(self):
        """Periodically update register RBV PVs."""
        while True:
            await asyncio.sleep(0.5)

            # If no interrupt is used, we still need to update ADC buffers
            if not hasattr(self.ol, "write_done_irq"):
                self.update_adc_bufs_with_pvs()

            logger.debug("%s Updating register RBVs", self.ioc_name)
            for name in self.ol.rf_control._registers.keys():
                value = getattr(self.llrf_register_map, name)
                self.pvs_in[f"rf_control:{name}:RBV"].set(value)

            # Update global mixer RBVs
            for name, value in self.ol.mixer_cfg.items():
                self.pvs_in[f"rfdc_mixer:{name}:RBV"].set(value)

            # Update per-channel mixer RBVs
            for ch, cfg in self.adc_mixer_cfg.items():
                for key in cfg.keys():
                    self.pvs_in[f"rfdc_mixer:ADC{ch}:nco_{key}:RBV"].set(cfg[key])

            for ch, cfg in self.dac_mixer_cfg.items():
                for key in cfg.keys():
                    self.pvs_in[f"rfdc_mixer:DAC{ch}:nco_{key}:RBV"].set(cfg[key])

            if hasattr(self.ol, "adc_cal"):
                self.update_adc_cal_pvs()

    def on_update_name(self, value, pv_name):
        """
        Callback for when a PV is updated.
        This method updates the overlay's register map or mixer settings based on the PV name.
        """
        if pv_name.startswith(f"{self.prefix}:rf_control:"):
            name = pv_name.split(":")[-1]
            signed_value = self.encode_2s_comp(value)  # XXX add "signed" field for each register
            if hasattr(self.llrf_register_map, name):
                setattr(self.llrf_register_map, name, signed_value)
            else:
                logger.warning("%s not found in llrf_register_map.", name)

        elif pv_name.startswith(f"{self.prefix}:rfdc_mixer:"):
            field = pv_name.removeprefix(f"{self.prefix}:rfdc_mixer:")

            # Per-channel ADC/DAC: e.g., "ADC0:nco_freq_mhz"
            match = re.match(r"^(?P<type>ADC|DAC)(?P<ch>\d+):nco_(?P<param>freq_mhz|nyquist|phase)$", field)
            if match:
                ch_type = match.group("type")
                ch = int(match.group("ch"))
                param = match.group("param")

                configs, setter = {
                    "ADC": (self.adc_mixer_cfg, self.ol.set_adc_mixer_ch),
                    "DAC": (self.dac_mixer_cfg, self.ol.set_dac_mixer_ch),
                }[ch_type]

                try:
                    cfg = configs[ch]
                    cfg[param] = value

                    logger.info(
                        "Setting %s ch%d mixer: freq=%s MHz, nyquist=%s, phase=%s",
                        ch_type,
                        ch,
                        cfg["freq_mhz"],
                        cfg["nyquist"],
                        cfg["phase"],
                    )
                    setter(ch, cfg["freq_mhz"], int(cfg["nyquist"]), cfg["phase"])
                except (KeyError, IndexError, ValueError) as e:
                    logger.error("Error updating %s with value %s: %s", field, value, e)

            # Global ADC: use set_adc_mixer() — all channels, synchronized
            elif field.startswith("adc_mixer_nco_"):
                logger.info("Setting ALL ADC mixers: field=%s, value=%s", field, value)
                setattr(self.ol, field, value)  # call self.ol.set_adc_mixer()
                # Update per-channel configs and PVs
                for ch, cfg in self.adc_mixer_cfg.items():
                    cfg["freq_mhz"] = self.ol.adc_mixer_nco_freq_mhz
                    cfg["nyquist"] = self.ol.adc_mixer_nco_nyquist
                    cfg["phase"] = self.ol.adc_mixer_nco_phase
                    self.pvs_out[f"rfdc_mixer:ADC{ch}:nco_freq_mhz"].set(cfg["freq_mhz"])
                    self.pvs_out[f"rfdc_mixer:ADC{ch}:nco_nyquist"].set(cfg["nyquist"])
                    self.pvs_out[f"rfdc_mixer:ADC{ch}:nco_phase"].set(cfg["phase"])

            # Global DAC: use set_dac_mixer() — all channels, synchronized
            elif field.startswith("dac_mixer_nco_"):
                logger.info("Setting ALL DAC mixers: field=%s, value=%s", field, value)
                setattr(self.ol, field, value)  # call self.ol.set_dac_mixer()
                # Update per-channel configs and PVs
                for ch, cfg in self.dac_mixer_cfg.items():
                    cfg["freq_mhz"] = self.ol.dac_mixer_nco_freq_mhz
                    cfg["nyquist"] = self.ol.dac_mixer_nco_nyquist
                    cfg["phase"] = self.ol.dac_mixer_nco_phase
                    self.pvs_out[f"rfdc_mixer:DAC{ch}:nco_freq_mhz"].set(cfg["freq_mhz"])
                    self.pvs_out[f"rfdc_mixer:DAC{ch}:nco_nyquist"].set(cfg["nyquist"])
                    self.pvs_out[f"rfdc_mixer:DAC{ch}:nco_phase"].set(cfg["phase"])

        elif "pulse_stat" in pv_name:
            # Per-channel ADC: DSP:ADC?:pulse_stat:start|end
            field = pv_name.removeprefix(f"{self.prefix}:")
            match = re.match(r"^(?P<type>DSP:ADC)(?P<ch>\d+):pulse_stat:(?P<param>start_ns|end_ns)$", field)
            if match:
                ch_type = match.group("type")
                ch = int(match.group("ch"))
                param = match.group("param")
                self.pvs_out[f"{ch_type}{ch}:pulse_stat:{param}"].set(value)
                if param == "start_ns":
                    self.adc_pulse_start_ns[ch] = value
                elif param == "end_ns":
                    self.adc_pulse_end_ns[ch] = value
                logger.info("Updated %s ch%d pulse_stat %s to %s", ch_type, ch, param, value)

    def drive_test_awg(self):
        """Drive DAC with a test arbitrary waveform"""
        assert self.ol.dac_player is not None, "DAC player buffer not initialized."
        f_c = self.dac_fs_ghz / 16  # 250 MHz
        t = np.arange(self.ol.dac_player.size) / self.dac_fs_ghz  # ns
        amp = 2**14 - 1
        # interp_factor = ol.ol_info['rfdc']['dac_interpolation_factor']
        dac_wfm = np.exp(1j * 2 * np.pi * f_c * t) * amp
        # dac_i = np.ones(self.ol.dac_player.size//2, dtype=np.int16) * 32767
        dac_wfm = dac_wfm[::2]  # decimate by 2
        dac_i = (dac_wfm.real).astype(np.int16)
        dac_q = (dac_wfm.imag).astype(np.int16)
        self.ol.write_dac_iq_buf(dac_i, dac_q)

    def drive_ones_awg(self):
        """Drive DAC with all ones, for testing purposes."""
        assert self.ol.dac_player is not None, "DAC player buffer not initialized."
        dac_i = np.ones(self.ol.dac_player.size // 2, dtype=np.int16) * 32767
        dac_q = np.zeros_like(dac_i)
        self.ol.write_dac_iq_buf(dac_i, dac_q)


def mimo_auto_ioc():
    ol_name = "MIMO" + "_" + os.environ["BOARD"]
    ioc = MimoMtsIoc(ol_name=ol_name)
    ioc.run_ioc()


def main():
    parser = argparse.ArgumentParser(description="soft IOC")
    parser.add_argument("--prefix", default="MIMO", help="$(P)")
    parser.add_argument(
        "--ol_name",
        default="MIMO",
        help="overlay config",
        choices=["MIMO_ZCU208", "MIMO_ZCU216", "ALS_LLRF_ZCU208", "ALS_LLRF_LBL208"],
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the logging level",
    )
    args = parser.parse_args()
    args.log_level = getattr(logging, args.log_level.upper(), logging.INFO)
    ioc = MimoMtsIoc(**vars(args))
    ioc.run_ioc()


if __name__ == "__main__":
    main()
