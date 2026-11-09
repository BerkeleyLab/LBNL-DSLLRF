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
from mimo_mts.drivers.wave_gen import MODE_SINGLE
from mimo_mts.overlay import MimoMtsOverlay
from mimo_mts.utils.rfdc_freq import nco_to_rf, rf_to_nco

logging.basicConfig(level=logging.INFO, format="%(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

DESC_LEN = 40  # EPICS DESC field: 40 characters


def desc(text: str) -> str:
    """Record description, cut to the 40 characters of the EPICS DESC field."""
    return text[:DESC_LEN]


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
        self.init_wave_gens()
        self.update_adc_bufs()
        self.init_capture_mode()
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
        self.llrf_register_map.dac_enable = 0  # DACs off at boot; enable with rf_control:dac_enable
        self.llrf_register_map.amp_loop_setpoint = 0

    def init_wave_gens(self):
        """
        Waveform generators (axil_wave_gen) play on the rf_control trigger, like the captures; their reset default is
        the software trigger only, so without this they never play. Single mode over the whole memory.
        """
        for wg in getattr(self.ol, "wave_gens", []):
            wg.trigger_mode = 1
            wg.wave_length = 0
            if getattr(wg, "version", 0):
                wg.mode = MODE_SINGLE
        if getattr(self.ol, "wave_gens", None) and all(getattr(g, "version", 0) for g in self.ol.wave_gens):
            self.ol.apply_dac_settings()

    def init_capture_mode(self):
        """
        One-shot captures where the overlay has the capture control registers (doc/development_plan.md, item 11):
        each capture is armed, taken on the next trigger and then held until the IOC has read it and re-armed, so a
        trigger during the read cannot overwrite a buffer half read. Older captures run free (every trigger).
        """
        self.capture_oneshot = bool(getattr(self.ol, "has_capture_csrs", False))
        self._last_read = time.monotonic()
        if self.capture_oneshot:
            self.ol.capture_oneshot = True
            self.ol.arm_captures()
        logger.info("ADC captures: %s", "one-shot (armed per read)" if self.capture_oneshot else "free-running")

    def captures_done(self) -> bool:
        """All armed captures have completed (one-shot mode)."""
        return all(done for _, _, done, _ in self.ol.capture_status())

    def read_captures(self):
        """Read the captures into the waveform PVs; in one-shot mode re-arm them afterwards."""
        self.update_adc_bufs_with_pvs()
        self._last_read = time.monotonic()
        if self.capture_oneshot:
            self.ol.arm_captures()

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
                # phase of the mean phasor, and spread around it: no wrap error near +-180 deg
                mean_phasor = pulse_data.mean()
                phs_dev = np.angle(pulse_data * np.conj(mean_phasor), deg=True)
                self.pvs_in[f"DSP:ADC{ix}:pulse_stat:phs:mean"].set(np.angle(mean_phasor, deg=True))
                self.pvs_in[f"DSP:ADC{ix}:pulse_stat:phs:std"].set(phs_dev.std())

    def encode_2s_comp(self, val):
        """encode signed integer to 2's complement representation"""
        return int(np.binary_repr(val, width=32), 2)

    def create_ioc(self):
        builder.SetDeviceName(self.prefix)
        self.pvs_in = {}
        self.pvs_out = {}

        name = "ADC:TWF"  # in ns
        self.pvs_in[name] = builder.WaveformIn(
            name,
            np.arange(0, self.n_samples / self.adc_fs_ghz, 1 / self.adc_fs_ghz),
            DESC=desc("Time axis of the ADC waveforms"),
            EGU="ns",
        )
        name = "DSP:TWF"  # in ns, after decimation
        self.pvs_in[name] = builder.WaveformIn(
            name,
            np.arange(0, self.n_dsp_samples / self.dsp_fs_ghz, 1 / self.dsp_fs_ghz),
            DESC=desc("Time axis of the DSP waveforms"),
            EGU="ns",
        )

        for ix in range(self.n_adc):
            name = f"ADC{ix}:IWF"
            self.pvs_in[name] = builder.WaveformIn(
                name, self.adc_bufs_i[ix], DESC=desc(f"ADC{ix} captured I samples"), EGU="cnt"
            )
            name = f"ADC{ix}:QWF"
            self.pvs_in[name] = builder.WaveformIn(
                name, self.adc_bufs_q[ix], DESC=desc(f"ADC{ix} captured Q samples"), EGU="cnt"
            )
            name = f"DSP:ADC{ix}:AWF"
            self.pvs_in[name] = builder.WaveformIn(
                name, np.abs(self.adc_bufs_mean[ix]), DESC=desc(f"ADC{ix} amplitude, decimated"), EGU="cnt"
            )
            name = f"DSP:ADC{ix}:PWF"
            self.pvs_in[name] = builder.WaveformIn(
                name, np.angle(self.adc_bufs_mean[ix], deg=True), DESC=desc(f"ADC{ix} phase, decimated"), EGU="deg"
            )

        self.add_mixer_pvs()
        self.add_dac_wfm_pvs()
        self.add_dac_channel_pvs()
        self.add_rf_control_pvs()
        self.add_pulse_pvs()
        self.add_trigger_pvs()
        if hasattr(self.ol, "adc_cal"):
            self.add_adc_cal_pvs()

    def add_dac_wfm_pvs(self):
        """
        DAC arbitrary waveform (I/Q baseband, int16), shared by all DACs (one waveform memory):
            DAC:IWF, DAC:QWF   write a waveform; both are written to the memory on every update
            DAC:TWF            time axis in ns at the complex input rate (DAC rate / interpolation)
        A write shorter than the memory is padded with zeros. Per-channel waveforms follow with one generator
        per DAC (doc/development_plan.md, item 2).
        """
        player = getattr(self.ol, "dac_player", None)
        if player is None:
            return
        n = player.size // 2
        if getattr(self, "dac_i", None) is None or self.dac_i.size != n:
            self.dac_i = np.zeros(n, dtype=np.int16)
            self.dac_q = np.zeros(n, dtype=np.int16)
        fs_iq_ghz = self.dac_fs_ghz / self.ol.ol_info["rfdc"]["dac_interpolation_factor"]
        self.pvs_in["DAC:TWF"] = builder.WaveformIn(
            "DAC:TWF", np.arange(n) / fs_iq_ghz, DESC=desc("Time axis of the DAC waveform"), EGU="ns"
        )
        for part in ("I", "Q"):
            name = f"DAC:{part}WF"
            self.pvs_out[name] = builder.WaveformOut(
                name,
                self.dac_i if part == "I" else self.dac_q,
                on_update=lambda value, part=part: self._on_dac_wfm(part, value),
                always_update=True,
                DESC=desc(f"DAC waveform {part}, all DACs"),
                EGU="cnt",
            )
        # Quick fill of every DAC waveform: 1 = full-scale I (drive_ones_awg), 0 = zeros (drive_zeros_awg)
        self.pvs_out["DAC:fill_ones"] = builder.boolOut(
            "DAC:fill_ones",
            initial_value=int(self.dac_i.size > 0 and bool(np.all(self.dac_i == 32767))),
            ZNAM="zeros",
            ONAM="ones",
            always_update=True,
            on_update=lambda v: self.drive_ones_awg() if v else self.drive_zeros_awg(),
            DESC=desc("Fill all DAC waveforms: 0 zeros, 1 ones"),
        )

    def add_dac_channel_pvs(self):
        """
        Per-DAC waveform, mode and CW PVs, on overlays with one waveform generator per DAC (doc/wave_gen.md):
            DAC{n}:IWF, DAC{n}:QWF        waveform of one DAC (int16 I/Q)
            DAC{n}:mode, DAC{n}:mode:RBV  staged and active mode: single (playback per trigger), loop, CW
            DAC{n}:cw:amp, DAC{n}:cw:phase  staged CW amplitude (fraction of full scale) and phase (deg)
            DAC:apply                     write 1: staged modes and CW values become active on all DACs at once
            DAC{n}:wave_length (+ :RBV), DAC:wave_length
                                          waveform length in ns (single: pulse length; loop: period), rounded to
                                          one generator row (4 ns at 5 GSPS); 0 = the whole memory. A write to
                                          rf_control:pulse_length (cycles of the 4 ns DSP clock) sets all of them.
        The CW carrier comes from the DAC fine mixer (rfdc_mixer:*:rf_freq_mhz).
        """
        gens = getattr(self.ol, "wave_gens", [])
        if len(gens) < 2 or not all(getattr(g, "version", 0) for g in gens):
            return
        self.dac_ch_iq = {}
        self.dac_cw = {}
        fs_iq = self.ol.dac_sampling_rate / self.ol.ol_info["rfdc"]["dac_interpolation_factor"]
        self.dac_row_ns = (gens[0].out_data_width // 32) / fs_iq * 1e9  # one generator row (I/Q pairs per row)
        full_ns = gens[0].bank_depth * self.dac_row_ns
        modes = {"ZRST": "single", "ONST": "loop", "TWST": "CW"}
        for ch, wg in enumerate(gens):
            n = wg.wave_mem.size // 2
            # start from the shared waveform loaded at init (write_dac), which every generator holds
            shared = getattr(self, "dac_i", None)
            if shared is not None and shared.size == n:
                self.dac_ch_iq[ch] = {"I": self.dac_i.copy(), "Q": self.dac_q.copy()}
            else:
                self.dac_ch_iq[ch] = {"I": np.zeros(n, dtype=np.int16), "Q": np.zeros(n, dtype=np.int16)}
            self.dac_cw[ch] = {"amp": 0.0, "phase": 0.0}
            for part in ("I", "Q"):
                self.pvs_out[f"DAC{ch}:{part}WF"] = builder.WaveformOut(
                    f"DAC{ch}:{part}WF",
                    self.dac_ch_iq[ch][part],
                    on_update=lambda value, ch=ch, part=part: self._on_dac_ch_wfm(ch, part, value),
                    always_update=True,  # DAC:IWF/QWF also write this memory: a repeated value must still be written
                    DESC=desc(f"DAC{ch} waveform {part}"),
                    EGU="cnt",
                )
            amp, phs = self._dac_amp_phase(ch)
            self.pvs_in[f"DAC{ch}:AWF"] = builder.WaveformIn(
                f"DAC{ch}:AWF", amp, DESC=desc(f"DAC{ch} waveform amplitude"), EGU="cnt"
            )
            self.pvs_in[f"DAC{ch}:PWF"] = builder.WaveformIn(
                f"DAC{ch}:PWF", phs, DESC=desc(f"DAC{ch} waveform phase"), EGU="deg"
            )
            self.pvs_out[f"DAC{ch}:mode"] = builder.mbbOut(
                f"DAC{ch}:mode",
                initial_value=0,
                on_update=lambda v, wg=wg: setattr(wg, "mode", int(v)),
                always_update=True,
                DESC=desc(f"DAC{ch} mode (active on DAC:apply)"),
                **modes,
            )
            self.pvs_in[f"DAC{ch}:mode:RBV"] = builder.mbbIn(
                f"DAC{ch}:mode:RBV", initial_value=wg.active_mode, DESC=desc(f"DAC{ch} active mode"), **modes
            )
            self.pvs_out[f"DAC{ch}:cw:amp"] = builder.aOut(
                f"DAC{ch}:cw:amp",
                initial_value=0.0,
                on_update=lambda v, ch=ch: self._on_dac_cw(ch, amp=v),
                always_update=True,
                DESC=desc(f"DAC{ch} CW amplitude (fraction of FS)"),
                DRVL=0,
                DRVH=1,
                PREC=4,
            )
            self.pvs_out[f"DAC{ch}:cw:phase"] = builder.aOut(
                f"DAC{ch}:cw:phase",
                initial_value=0.0,
                on_update=lambda v, ch=ch: self._on_dac_cw(ch, phase=v),
                always_update=True,
                DESC=desc(f"DAC{ch} CW phase"),
                EGU="deg",
                PREC=2,
            )
            self.pvs_out[f"DAC{ch}:wave_length"] = builder.aOut(
                f"DAC{ch}:wave_length",
                initial_value=self._dac_length_ns(wg),
                on_update=lambda v, ch=ch: self._set_dac_length([ch], v),
                always_update=True,
                DESC=desc(f"DAC{ch} waveform length, 0 = whole"),
                EGU="ns",
                DRVL=0,
                DRVH=full_ns,
                PREC=0,
            )
            self.pvs_in[f"DAC{ch}:wave_length:RBV"] = builder.aIn(
                f"DAC{ch}:wave_length:RBV",
                initial_value=self._dac_length_ns(wg),
                DESC=desc(f"DAC{ch} waveform length applied"),
                EGU="ns",
                PREC=0,
            )
        self.pvs_out["DAC:wave_length"] = builder.aOut(
            "DAC:wave_length",
            initial_value=self._dac_length_ns(gens[0]),
            on_update=lambda v: self._set_dac_length(range(len(gens)), v),
            always_update=True,
            DESC=desc("All DACs waveform length, 0 = whole"),
            EGU="ns",
            DRVL=0,
            DRVH=full_ns,
            PREC=0,
        )
        self.pvs_out["DAC:apply"] = builder.boolOut(
            "DAC:apply",
            ZNAM="idle",
            ONAM="apply",
            always_update=True,
            on_update=lambda v: v and self.ol.apply_dac_settings(),
            DESC=desc("Apply staged DAC modes / CW, all DACs"),
        )

    def _dac_length_ns(self, wg):
        """Playback length of a generator in ns (wave_length 0 plays the whole memory)."""
        return (int(wg.wave_length) or wg.bank_depth) * self.dac_row_ns

    def _set_dac_length(self, chans, ns):
        """Set the waveform length of DACs from ns: whole rows; 0 or the full memory -> wave_length 0 (whole memory)."""
        for ch in chans:
            wg = self.ol.wave_gens[ch]
            rows = int(round(ns / self.dac_row_ns))
            wg.wave_length = rows if 0 < rows < wg.bank_depth else 0
            applied = self._dac_length_ns(wg)
            self.pvs_out[f"DAC{ch}:wave_length"].set(ns, process=False)
            self.pvs_in[f"DAC{ch}:wave_length:RBV"].set(applied)
            logger.info("DAC%d waveform length %s ns -> %d rows (%.0f ns)", ch, ns, wg.wave_length, applied)

    def _dac_amp_phase(self, ch):
        """Amplitude (counts) and phase (deg) of DAC ch's waveform, float32 for the DAC{n}:AWF / PWF plots."""
        c = self.dac_ch_iq[ch]["I"].astype(np.float32) + 1j * self.dac_ch_iq[ch]["Q"].astype(np.float32)
        return np.abs(c).astype(np.float32), np.angle(c, deg=True).astype(np.float32)

    def _publish_dac_ch(self, ch, iq_pvs=False):
        """Update DAC{ch}:AWF / PWF (and with iq_pvs DAC{ch}:IWF / QWF, without writing the memory again)."""
        if iq_pvs:
            for part in ("I", "Q"):
                self.pvs_out[f"DAC{ch}:{part}WF"].set(self.dac_ch_iq[ch][part], process=False)
        amp, phs = self._dac_amp_phase(ch)
        self.pvs_in[f"DAC{ch}:AWF"].set(amp)
        self.pvs_in[f"DAC{ch}:PWF"].set(phs)

    def _on_dac_ch_wfm(self, ch, part, value):
        """
        DAC{ch}:IWF or QWF written: use the written value and the IOC's copy of the other part. Reading the PVs back
        here would race with other callbacks (a shared DAC:IWF write updates these PVs when its callback runs, which
        can be after a later DAC{ch}:IWF write has already been stored).
        """
        n = self.dac_ch_iq[ch]["I"].size
        v = np.asarray(value, dtype=np.int16)[:n]
        self.dac_ch_iq[ch][part] = np.pad(v, (0, n - v.size))
        self.ol.write_dac_iq_buf_ch(ch, self.dac_ch_iq[ch]["I"], self.dac_ch_iq[ch]["Q"])
        self._publish_dac_ch(ch, iq_pvs=True)  # the PVs end up showing what the generator holds
        logger.info("DAC%d waveform written (%d I/Q samples)", ch, n)

    def _on_dac_cw(self, ch, **kw):
        self.dac_cw[ch].update(kw)
        try:
            self.ol.wave_gens[ch].set_cw_amp_phase(self.dac_cw[ch]["amp"], self.dac_cw[ch]["phase"])
        except ValueError as e:
            logger.error("DAC%d CW: %s", ch, e)

    def _on_dac_wfm(self, part, value):
        """DAC:IWF or QWF written: the written value and the IOC's copy of the other part (no PV read-back)."""
        n = self.dac_i.size
        v = np.asarray(value, dtype=np.int16)[:n]
        v = np.pad(v, (0, n - v.size))
        self.write_dac(v if part == "I" else self.dac_i, v if part == "Q" else self.dac_q)
        logger.info("DAC waveform written (%d I/Q samples)", n)

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
            DESC=desc("Freeze GCB/TSCB calibration, all ADCs"),
            ZNAM="tracking",
            ONAM="frozen",
            always_update=True,
            on_update=lambda v: self._adc_cal_action("freeze" if v else "unfreeze"),
        )
        for ch in cal.channels:
            name = f"{prefix}ADC{ch}:freeze"
            self.pvs_out[name] = builder.boolOut(
                name,
                DESC=desc(f"Freeze GCB/TSCB calibration, ADC{ch}"),
                ZNAM="tracking",
                ONAM="frozen",
                always_update=True,
                on_update=lambda v, ch=ch: self._adc_cal_action("freeze" if v else "unfreeze", ch),
            )
            name = f"{prefix}ADC{ch}:frozen:RBV"
            self.pvs_in[name] = builder.boolIn(
                name, DESC=desc(f"ADC{ch} calibration freeze status"), ZNAM="tracking", ONAM="frozen"
            )

        action_desc = {
            "save": "Save calibration coefficients to file",
            "restore": "Restore GCB/TSCB from file and freeze",
            "release_override": "Return calibration to the engine",
        }
        for action in ("save", "restore", "release_override"):
            self.pvs_out[prefix + action] = builder.boolOut(
                prefix + action,
                DESC=desc(action_desc[action]),
                ZNAM="idle",
                ONAM="run",
                always_update=True,
                on_update=lambda v, action=action: v and self._adc_cal_action(action),
            )
        self.pvs_in[prefix + "file"] = builder.longStringIn(
            prefix + "file", initial_value=str(self.adc_cal_file), DESC=desc("Calibration file on the board")
        )
        self.pvs_in[prefix + "status"] = builder.longStringIn(
            prefix + "status", initial_value=self.adc_cal_status, DESC=desc("Result of the last calibration action")
        )

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
        units = {"freq_mhz": ("NCO frequency", "MHz"), "nyquist": ("Nyquist zone", ""), "phase": ("NCO phase", "deg")}

        def add(name, value, what):
            key = name.rsplit("_", 1)[-1] if not name.endswith("freq_mhz") else "freq_mhz"
            text, egu = units[key]
            self.pvs_in[prefix + name + ":RBV"] = builder.aIn(
                prefix + name + ":RBV", initial_value=value, DESC=desc(f"{what} {text}"), EGU=egu
            )
            self.pvs_out[prefix + name] = builder.aOut(
                prefix + name,
                initial_value=value,
                on_update_name=self.on_update_name,
                always_update=True,  # global and per-channel PVs set the same NCOs: re-apply a repeated value
                DESC=desc(f"{what} {text}"),
                EGU=egu,
            )

        # Global PVs (apply to all channels at once)
        for name, value in self.ol.mixer_cfg.items():
            add(name, value, "All ADCs" if name.startswith("adc") else "All DACs")

        # Per-channel ADC mixer PVs
        for ch, cfg in self.adc_mixer_cfg.items():
            for key in cfg.keys():
                add(f"ADC{ch}:nco_{key}", self.adc_mixer_cfg[ch][key], f"ADC{ch}")

        # Per-channel DAC mixer PVs
        for ch, cfg in self.dac_mixer_cfg.items():
            for key in cfg.keys():
                add(f"DAC{ch}:nco_{key}", self.dac_mixer_cfg[ch][key], f"DAC{ch}")

        # Operator view: RF frequency only; NCO frequency and Nyquist zone follow (mimo_mts/utils/rfdc_freq.py)
        def add_rf(name, rf_mhz, what, fs_hz):
            self.pvs_in[prefix + name + ":RBV"] = builder.aIn(
                prefix + name + ":RBV", initial_value=rf_mhz, DESC=desc(f"{what} RF frequency"), EGU="MHz", PREC=3
            )
            self.pvs_out[prefix + name] = builder.aOut(
                prefix + name,
                initial_value=rf_mhz,
                on_update_name=self.on_update_name,
                always_update=True,
                DESC=desc(f"{what} RF frequency (sets NCO, zone)"),
                EGU="MHz",
                PREC=3,
                DRVL=0,
                DRVH=fs_hz / 1e6,
            )

        add_rf(
            "adc_rf_freq_mhz",
            self._rf_mhz("adc", self.ol.mixer_cfg, "adc_mixer_nco_"),
            "All ADCs",
            self.ol.adc_sampling_rate,
        )
        add_rf(
            "dac_rf_freq_mhz",
            self._rf_mhz("dac", self.ol.mixer_cfg, "dac_mixer_nco_"),
            "All DACs",
            self.ol.dac_sampling_rate,
        )
        for ch, cfg in self.adc_mixer_cfg.items():
            add_rf(f"ADC{ch}:rf_freq_mhz", self._rf_mhz("adc", cfg), f"ADC{ch}", self.ol.adc_sampling_rate)
        for ch, cfg in self.dac_mixer_cfg.items():
            add_rf(f"DAC{ch}:rf_freq_mhz", self._rf_mhz("dac", cfg), f"DAC{ch}", self.ol.dac_sampling_rate)

    @staticmethod
    def _rf_mhz(converter, cfg, key_prefix=""):
        """RF frequency of a mixer configuration (dict with freq_mhz/nyquist, optionally prefixed)."""
        return nco_to_rf(cfg[key_prefix + "freq_mhz"], int(cfg[key_prefix + "nyquist"]), converter)

    def add_rf_control_pvs(self, prefix="rf_control:"):
        """
        Add RF control related PVs to the IOC.
        """
        for name, reg in self.ol.rf_control._registers.items():
            value = int(getattr(self.llrf_register_map, name))
            text = reg.get("description", name)
            self.pvs_in[prefix + name + ":RBV"] = builder.longIn(
                prefix + name + ":RBV", initial_value=value, DESC=desc(text)
            )
            if reg.get("access") == "read-only":
                continue
            self.pvs_out[prefix + name] = builder.longOut(
                prefix + name, initial_value=value, on_update_name=self.on_update_name, DESC=desc(text)
            )

    def add_trigger_pvs(self):
        """
        trigger:rate_hz (+ :RBV): internal trigger rate in Hz, i.e. rf_control:trig_period in cycles of the DSP clock
        (ol_info["dsp_clk_hz"], 250 MHz by default); 0 = internal trigger off.
        """
        self.dsp_clk_hz = float(self.ol.ol_info.get("dsp_clk_hz", 250e6))
        rate = self._trig_rate_hz()
        self.pvs_out["trigger:rate_hz"] = builder.aOut(
            "trigger:rate_hz",
            initial_value=rate,
            on_update=self._set_trig_rate,
            always_update=True,
            DESC=desc("Internal trigger rate, 0 = off"),
            EGU="Hz",
            DRVL=0,
            DRVH=1e6,
            PREC=3,
        )
        self.pvs_in["trigger:rate_hz:RBV"] = builder.aIn(
            "trigger:rate_hz:RBV", initial_value=rate, DESC=desc("Internal trigger rate"), EGU="Hz", PREC=3
        )

    def _trig_rate_hz(self):
        period = int(self.llrf_register_map.trig_period)
        return self.dsp_clk_hz / period if period > 0 else 0.0

    def _set_trig_rate(self, rate_hz):
        period = int(round(self.dsp_clk_hz / rate_hz)) if rate_hz > 0 else 0
        period = min(period, 2**32 - 1)
        self.llrf_register_map.trig_period = period
        self.pvs_out["rf_control:trig_period"].set(period, process=False)
        self.pvs_in["trigger:rate_hz:RBV"].set(self._trig_rate_hz())
        logger.info("Internal trigger rate %s Hz -> trig_period %d cycles", rate_hz, period)

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
                    name,
                    DRVL=0,
                    DRVH=16380,
                    EGU="ns",
                    initial_value=1000,
                    on_update_name=self.on_update_name,
                    DESC=desc(f"ADC{ix} pulse window {s.split('_')[0]}"),
                )
            for p in ["mean", "std"]:
                name = f"DSP:ADC{ix}:{prefix}amp:{p}"
                self.pvs_in[name] = builder.aIn(
                    name, LOPR=0, HOPR=32768, EGU="cnt", initial_value=0, DESC=desc(f"ADC{ix} pulse amplitude {p}")
                )
                name = f"DSP:ADC{ix}:{prefix}phs:{p}"
                self.pvs_in[name] = builder.aIn(
                    name, LOPR=-180, HOPR=180, EGU="deg", initial_value=0, DESC=desc(f"ADC{ix} pulse phase {p}")
                )

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
            if self.capture_oneshot and not self.captures_done():
                # the IRQ comes from one capture; the others finish on the same trigger, give them a moment
                await asyncio.sleep(1e-3)
                if not self.captures_done():
                    logger.warning("%s IRQ but not all captures done; reading anyway", self.ioc_name)
            self.read_captures()
            logger.debug("%s IRQ!, time since last: %.6f s", self.ioc_name, t1 - t0)
            t0 = t1

    async def update_registers(self):
        """Periodically update register RBV PVs."""
        while True:
            await asyncio.sleep(0.5)

            # If no interrupt is used, we still need to update ADC buffers
            if not hasattr(self.ol, "write_done_irq") and (not self.capture_oneshot or self.captures_done()):
                self.read_captures()
            elif self.capture_oneshot and time.monotonic() - self._last_read > 1.0 and self.captures_done():
                # watchdog: a capture finished but its interrupt was missed; read it and re-arm, or updates stop
                logger.debug("%s captures done without an interrupt; reading", self.ioc_name)
                self.read_captures()

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

            # RF frequency RBVs, derived from the NCO settings
            mix = self.ol.mixer_cfg
            self.pvs_in["rfdc_mixer:adc_rf_freq_mhz:RBV"].set(self._rf_mhz("adc", mix, "adc_mixer_nco_"))
            self.pvs_in["rfdc_mixer:dac_rf_freq_mhz:RBV"].set(self._rf_mhz("dac", mix, "dac_mixer_nco_"))
            for conv, configs in (("adc", self.adc_mixer_cfg), ("dac", self.dac_mixer_cfg)):
                for ch, cfg in configs.items():
                    self.pvs_in[f"rfdc_mixer:{conv.upper()}{ch}:rf_freq_mhz:RBV"].set(self._rf_mhz(conv, cfg))

            if hasattr(self.ol, "adc_cal"):
                self.update_adc_cal_pvs()

            self.pvs_in["trigger:rate_hz:RBV"].set(self._trig_rate_hz())

            for ch, wg in enumerate(getattr(self.ol, "wave_gens", [])):
                rbv = self.pvs_in.get(f"DAC{ch}:mode:RBV")
                if rbv is not None:
                    rbv.set(wg.active_mode)
                    self.pvs_in[f"DAC{ch}:wave_length:RBV"].set(self._dac_length_ns(wg))

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
            if name == "pulse_length" and "DAC:wave_length" in self.pvs_out:
                # per-DAC generators: the DAC pulse length is their wave_length (cycles of the 4 ns DSP clock)
                ns = value * 4.0
                self.pvs_out["DAC:wave_length"].set(ns, process=False)
                self._set_dac_length(range(len(self.ol.wave_gens)), ns)

        elif pv_name.startswith(f"{self.prefix}:rfdc_mixer:"):
            field = pv_name.removeprefix(f"{self.prefix}:rfdc_mixer:")
            if field.endswith("rf_freq_mhz"):
                self._set_rf_freq(field, value)
                return

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
                    self.pvs_out[f"rfdc_mixer:ADC{ch}:nco_freq_mhz"].set(cfg["freq_mhz"], process=False)
                    self.pvs_out[f"rfdc_mixer:ADC{ch}:nco_nyquist"].set(cfg["nyquist"], process=False)
                    self.pvs_out[f"rfdc_mixer:ADC{ch}:nco_phase"].set(cfg["phase"], process=False)

            # Global DAC: use set_dac_mixer() — all channels, synchronized
            elif field.startswith("dac_mixer_nco_"):
                logger.info("Setting ALL DAC mixers: field=%s, value=%s", field, value)
                setattr(self.ol, field, value)  # call self.ol.set_dac_mixer()
                # Update per-channel configs and PVs
                for ch, cfg in self.dac_mixer_cfg.items():
                    cfg["freq_mhz"] = self.ol.dac_mixer_nco_freq_mhz
                    cfg["nyquist"] = self.ol.dac_mixer_nco_nyquist
                    cfg["phase"] = self.ol.dac_mixer_nco_phase
                    self.pvs_out[f"rfdc_mixer:DAC{ch}:nco_freq_mhz"].set(cfg["freq_mhz"], process=False)
                    self.pvs_out[f"rfdc_mixer:DAC{ch}:nco_nyquist"].set(cfg["nyquist"], process=False)
                    self.pvs_out[f"rfdc_mixer:DAC{ch}:nco_phase"].set(cfg["phase"], process=False)

        elif "pulse_stat" in pv_name:
            # Per-channel ADC: DSP:ADC?:pulse_stat:start|end
            field = pv_name.removeprefix(f"{self.prefix}:")
            match = re.match(r"^(?P<type>DSP:ADC)(?P<ch>\d+):pulse_stat:(?P<param>start_ns|end_ns)$", field)
            if match:
                ch_type = match.group("type")
                ch = int(match.group("ch"))
                param = match.group("param")
                self.pvs_out[f"{ch_type}{ch}:pulse_stat:{param}"].set(value, process=False)
                if param == "start_ns":
                    self.adc_pulse_start_ns[ch] = value
                elif param == "end_ns":
                    self.adc_pulse_end_ns[ch] = value
                logger.info("Updated %s ch%d pulse_stat %s to %s", ch_type, ch, param, value)

    def _set_rf_freq(self, field, rf_mhz):
        """Apply an RF frequency PV: derive NCO frequency and Nyquist zone, keep the phase, update the NCO PVs."""
        m = re.match(r"^(?:(?P<all>adc|dac)_rf_freq_mhz|(?P<type>ADC|DAC)(?P<ch>\d+):rf_freq_mhz)$", field)
        if not m:
            logger.warning("Unknown RF frequency PV %s", field)
            return
        conv = (m.group("all") or m.group("type")).lower()
        fs_mhz = (self.ol.adc_sampling_rate if conv == "adc" else self.ol.dac_sampling_rate) / 1e6
        try:
            nco, zone = rf_to_nco(rf_mhz, fs_mhz, conv)
        except ValueError as e:
            logger.error("%s: %s", field, e)
            return
        logger.info("%s = %s MHz -> NCO %s MHz, Nyquist zone %d", field, rf_mhz, nco, zone)
        if m.group("all"):
            phase = getattr(self.ol, f"{conv}_mixer_nco_phase")
            getattr(self.ol, f"set_{conv}_mixer")(nco, zone, phase)
            configs = self.adc_mixer_cfg if conv == "adc" else self.dac_mixer_cfg
            for ch, cfg in configs.items():
                cfg.update(freq_mhz=nco, nyquist=zone, phase=phase)
                self.pvs_out[f"rfdc_mixer:{conv.upper()}{ch}:nco_freq_mhz"].set(nco, process=False)
                self.pvs_out[f"rfdc_mixer:{conv.upper()}{ch}:nco_nyquist"].set(zone, process=False)
                self.pvs_out[f"rfdc_mixer:{conv.upper()}{ch}:rf_freq_mhz"].set(rf_mhz, process=False)
            self.pvs_out[f"rfdc_mixer:{conv}_mixer_nco_freq_mhz"].set(nco, process=False)
            self.pvs_out[f"rfdc_mixer:{conv}_mixer_nco_nyquist"].set(zone, process=False)
        else:
            ch = int(m.group("ch"))
            cfg = (self.adc_mixer_cfg if conv == "adc" else self.dac_mixer_cfg)[ch]
            cfg.update(freq_mhz=nco, nyquist=zone)
            getattr(self.ol, f"set_{conv}_mixer_ch")(ch, nco, zone, cfg["phase"])
            self.pvs_out[f"rfdc_mixer:{conv.upper()}{ch}:nco_freq_mhz"].set(nco, process=False)
            self.pvs_out[f"rfdc_mixer:{conv.upper()}{ch}:nco_nyquist"].set(zone, process=False)

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
        self.write_dac(dac_i, dac_q)

    def drive_zeros_awg(self):
        """Zero DAC waveform: no output even where rf_control:dac_enable does not gate the DACs (mimo_mts_5g)."""
        assert self.ol.dac_player is not None, "DAC player buffer not initialized."
        dac_i = np.zeros(self.ol.dac_player.size // 2, dtype=np.int16)
        self.write_dac(dac_i, np.zeros_like(dac_i))

    def drive_ones_awg(self):
        """Drive DAC with all ones, for testing purposes."""
        assert self.ol.dac_player is not None, "DAC player buffer not initialized."
        dac_i = np.ones(self.ol.dac_player.size // 2, dtype=np.int16) * 32767
        dac_q = np.zeros_like(dac_i)
        self.write_dac(dac_i, dac_q)

    def write_dac(self, dac_i, dac_q):
        """Write the DAC waveform (shared by all DACs) and remember it for the DAC:IWF/QWF PVs."""
        self.dac_i = np.asarray(dac_i, dtype=np.int16)
        self.dac_q = np.asarray(dac_q, dtype=np.int16)
        self.ol.write_dac_iq_buf(self.dac_i, self.dac_q)
        # with one generator per DAC this wrote every generator: keep the per-DAC PVs and plots in step
        for ch in getattr(self, "dac_ch_iq", {}):
            if f"DAC{ch}:AWF" in getattr(self, "pvs_in", {}):
                self.dac_ch_iq[ch] = {"I": self.dac_i.copy(), "Q": self.dac_q.copy()}
                self._publish_dac_ch(ch, iq_pvs=True)


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
