import json
import time
from pathlib import Path
from typing import Any

import numpy as np
from pynq import DefaultIP

MODE_SINGLE, MODE_LOOP, MODE_CW = 0, 1, 2
LEGACY_WAVEFORM_BASE = 0x18  # register map version 1 (before the loop / CW modes)


class WaveGen(DefaultIP):
    """
    Driver for axil_wave_gen (doc/wave_gen.md): a waveform memory played on trigger, in a loop, or replaced by a
    constant I/Q value (CW). Mode and CW value are staged and become active on apply: on this channel with
    ``apply()``, or on all generators at once with the common apply of axil_rf_control
    (``MimoMtsOverlay.apply_dac_settings()``). Bitstreams with register map version 1 (``version == 0``) have no
    modes; the waveform memory is then at 0x18.
    """

    MODE_SINGLE, MODE_LOOP, MODE_CW = MODE_SINGLE, MODE_LOOP, MODE_CW

    bindto = ["xilinx.com:module_ref:axil_wave_gen:1.0"]
    register_map: Any  # built at runtime by PYNQ from axil_wave_gen.json

    def __init__(self, description):
        ip_path = Path(__file__).resolve().parent.parent.parent / "designs" / "ip"
        json_path = ip_path / "rtl" / "axil_wave_gen.json"
        with open(json_path) as f:
            description["registers"] = json.load(f)
        super().__init__(description)
        params = description.get("parameters", {})
        self.out_data_width = int(params.get("OUT_DATA_WIDTH", 320))
        self.bank_depth = int(params.get("BANK_DEPTH", 4096))
        self.version = self.read(self.register_map.version.address) & 0xFFFFFFFF
        self.wave_mem = self._mem_to_view()

    @property
    def busy(self):
        """Playback is running"""
        return int(self.register_map.status.busy)

    @property
    def wave_length(self):
        """Number of output words (20 int16 samples each with the default 320-bit output) to play; 0 plays all"""
        return int(self.register_map.wave_length)

    @wave_length.setter
    def wave_length(self, value):
        self.register_map.wave_length = value

    @property
    def trigger_mode(self):
        """Trigger mode (0=internal, 1=external)"""
        return int(self.register_map.ctrl.trigger_mode)

    @trigger_mode.setter
    def trigger_mode(self, value):
        self.register_map.ctrl.trigger_mode = value

    def trigger(self):
        """Trigger waveform output"""
        self.register_map.ctrl.trigger = 1

    def wait_idle(self, timeout_s=1.0):
        """Wait until playback has finished; returns False on timeout (e.g. DAC stream stopped)."""
        t_end = time.monotonic() + timeout_s
        while self.busy:
            if time.monotonic() > t_end:
                return False
        return True

    # --- modes (register map version 2) ---

    def _require_modes(self):
        if self.version == 0:
            raise RuntimeError("this bitstream's axil_wave_gen has no loop/CW modes (register map version 1)")

    @property
    def mode(self):
        """Staged mode (0 single, 1 loop, 2 CW); becomes active on apply"""
        self._require_modes()
        return int(self.register_map.mode) & 3

    @mode.setter
    def mode(self, value):
        self._require_modes()
        self.register_map.mode = int(value)

    @property
    def active_mode(self):
        """Mode in effect (0 single, 1 loop, 2 CW)"""
        return int(self.register_map.status.mode) if self.version else MODE_SINGLE

    def set_cw(self, i, q):
        """Stage the CW value: int16 I and Q (active on apply)"""
        self._require_modes()
        i, q = int(i), int(q)
        if not (-32768 <= i <= 32767 and -32768 <= q <= 32767):
            raise ValueError(f"CW I/Q ({i}, {q}) outside int16")
        self.register_map.cw_iq = ((q & 0xFFFF) << 16) | (i & 0xFFFF)

    def set_cw_amp_phase(self, amp, phase_deg):
        """Stage the CW value from amplitude (fraction of full scale, 0..1) and phase in degrees"""
        if not 0 <= amp <= 1:
            raise ValueError(f"CW amplitude {amp} outside 0..1")
        z = amp * 32767 * np.exp(1j * np.deg2rad(phase_deg))
        self.set_cw(round(z.real), round(z.imag))

    def apply(self):
        """Make the staged mode and CW value active on this channel only"""
        self._require_modes()
        self.register_map.ctrl.apply = 1

    @property
    def samples_per_word(self):
        """int16 samples per output word (one wave_length unit)"""
        return self.out_data_width // 16

    def _mem_to_view(self, dtype="int16"):
        """
        The waveform memory as a numpy array: a flat byte array in output order (doc/wave_gen.md), writable with any
        access size and in any order. ``mmio.array`` is uint32, so slice a byte view of it.
        """
        start = self.register_map.waveform_data.address if self.version else LEGACY_WAVEFORM_BASE  # byte offset
        self._max_wave_bytes = self.bank_depth * self.out_data_width // 8
        return self.mmio.array.view(np.uint8)[start : start + self._max_wave_bytes].view(dtype)
