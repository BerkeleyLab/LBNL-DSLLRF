from pynq import DefaultIP
import time
from pathlib import Path
import json


class EVR(DefaultIP):
    bindto = ['xilinx.com:module_ref:axil_evr:1.0']

    def __init__(self, description):
        ip_path = Path(__file__).resolve().parent.parent.parent / \
            'boards' / 'ip'
        json_path = ip_path / 'rtl' / 'axil_evr.json'
        with open(json_path, 'r') as f:
            description['registers'] = json.load(f)
        super().__init__(description=description)

    def check_frequencies(self,
                          ref_freq_expect=156.1375,
                          rx_freq_expect=499.64/4):
        """Diagnostic function to check the GTY frequencies"""
        self._check_freq(self.gt_ref_freq_mhz, ref_freq_expect)
        self._check_freq(self.gt_rx_freq_mhz, rx_freq_expect)
        assert self.rx_aligned, "GTY RX is not aligned"
        self._check_reset_cnt()

    def _convert_freq_to_hz(self, f_cnt, f_ref=100.0e6):
        """Convert the frequency counter value to Hz"""
        return (f_cnt / 2**24) * f_ref

    @property
    def evr_status(self):
        return self.register_map.gt_evr_status

    @property
    def gt_ref_freq_cnt(self):
        return int(self.register_map.gt_ref_freq)

    @property
    def gt_rx_freq_cnt(self):
        return int(self.register_map.gt_rx_freq)

    @property
    def gt_ref_freq_mhz(self):
        return self._convert_freq_to_hz(self.gt_ref_freq_cnt) / 1e6

    @property
    def gt_rx_freq_mhz(self):
        return self._convert_freq_to_hz(self.gt_rx_freq_cnt) / 1e6

    @property
    def event_count(self):
        return int(self.register_map.evr_event_count)

    @property
    def timestamp_valid(self):
        return bool(self.register_map.evr_timestamp_valid)

    @property
    def rx_aligned(self):
        return bool(self.evr_status.rx_aligned)

    @property
    def timestamp(self):
        ts_lo = int(self.register_map.evr_timestamp_lo)
        ts_hi = int(self.register_map.evr_timestamp_hi)
        return (ts_hi << 32) | ts_lo

    def _check_freq(self, freq, freq_expect, tolerance_ppm=50.0):
        ppm = ((freq / freq_expect) - 1.0) * 1e6
        assert abs(ppm) < tolerance_ppm, \
            f"Freq is out of spec by {ppm:3.0f} ppm"

    def _check_reset_cnt(self):
        """ Check if the GTY has been reset during 1 second """
        init_val = self.register_map.gt_reset_count
        time.sleep(1)
        new_val = self.register_map.gt_reset_count
        assert init_val == new_val, "GTY has been reset during 1 second"

    def __repr__(self):
        str = (
            f"GT EVR GTY:      {self.bindto}\n"
            f"Event count:     {self.event_count}\n"
            f"GTY ref freq:    {self.gt_ref_freq_mhz:8.4f} MHz\n"
            f"GTY RX freq:     {self.gt_rx_freq_mhz:8.4f} MHz\n"
            f"Timestamp valid: {self.timestamp_valid}\n"
            f"Timestamp:       {self.timestamp}\n"
            f"GTY status:      {self.evr_status}\n"
            f"RX aligned:      {self.rx_aligned}\n"
        )
        return str
