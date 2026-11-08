import json
import time
from pathlib import Path
from typing import Any

import numpy as np
from pynq import DefaultIP


class WaveGen(DefaultIP):
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

    @property
    def samples_per_word(self):
        """int16 samples per output word (one wave_length unit)"""
        return self.out_data_width // 16

    def _mem_to_view(self, dtype="int16"):
        """
        The waveform memory as a numpy array: a flat byte array in output order (doc/wave_gen.md), writable with any
        access size and in any order. ``mmio.array`` is uint32, so slice a byte view of it.
        """
        start = self.register_map.waveform_data.address  # byte offset
        self._max_wave_bytes = self.bank_depth * self.out_data_width // 8
        return self.mmio.array.view(np.uint8)[start : start + self._max_wave_bytes].view(dtype)
