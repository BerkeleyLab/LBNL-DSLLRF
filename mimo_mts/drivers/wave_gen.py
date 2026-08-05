from pynq import DefaultIP
from pathlib import Path
import json


class WaveGen(DefaultIP):
    bindto = ['xilinx.com:module_ref:axil_wave_gen:1.0']

    def __init__(self, description):
        ip_path = Path(__file__).resolve().parent.parent.parent / \
            'designs' / 'ip'
        json_path = ip_path / 'rtl' / 'axil_wave_gen.json'
        with open(json_path, 'r') as f:
            description['registers'] = json.load(f)
        super().__init__(description)
        self.wave_mem = self._mem_to_view()

    @property
    def busy(self):
        """Generator is busy (reading or writing)"""
        return int(self.register_map.status.busy)

    @property
    def wave_length(self):
        """Number of samples to output on trigger"""
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

    def flush(self):
        """Flush write accumulator"""
        self.register_map.ctrl.flush = 1

    def flush_and_wait(self):
        """Flush write accumulator and wait for completion"""
        self.flush()
        while self.busy:
            pass

    def _mem_to_view(self, dtype="int16"):
        # Base address for waveform memory writes
        start = self.register_map.waveform_data.address
        # See maximum length defined in axil_wave_gen.v
        # XXX hard-coded parameters
        self._max_wave_bytes = 4096 * 320 // 8
        return self.mmio.array[start:start+self._max_wave_bytes].view(dtype)
