# A simple overlay to measure the
# clk104 input frequency and experiment with xrfclk
from pynq import Overlay, MMIO
import os

MODULE_PATH = os.path.dirname(os.path.realpath(__file__))


class CLK104IF(Overlay):
    def __init__(self, bitfile_name="clk104if.bit", **kwargs):
        board = os.getenv("BOARD")
        print(board)
        super().__init__(resolve_binary_path(bitfile_name), **kwargs)


class FreqCounter:
    def __init__(self, ip_dict_entry, rw=24, f_ref=250.0e6):
        self._rw = rw
        self._f_ref = f_ref
        base = ip_dict_entry["phys_addr"]
        self._freq = MMIO(base)

    def read(self):
        data = self._freq.read()
        freq_hz = (data / (2**self._rw)) * self._f_ref
        return freq_hz


def resolve_binary_path(bitfile_name):
    """this helper function is necessary to
    locate the bit file during overlay loading"""
    if os.path.isfile(bitfile_name):
        return bitfile_name
    elif os.path.isfile(os.path.join(MODULE_PATH, bitfile_name)):
        return os.path.join(MODULE_PATH, bitfile_name)
    else:
        raise FileNotFoundError(f"Cannot find {bitfile_name}.")
