# A simple overlay to reset GTY and check for alignement.
# Also verify EVR registers
import os
import numpy as np
import time
from pynq import Overlay, MMIO
from smbus2 import SMBus

MODULE_PATH = os.path.dirname(os.path.realpath(__file__))


class CONFIG_EVR(Overlay):
    def __init__(self, bitfile_name="config_evr.bit", **kwargs):
        board = os.getenv("BOARD")
        print(board)
        super().__init__(resolve_binary_path(bitfile_name), **kwargs)


def ConfigSI570(new_freq=156.1375):
    bus = SMBus(1, force=True)
    bus.write_byte_data(0x74, 0, 0x8)
    # get current settings
    a = bus.read_i2c_block_data(0x5D, 0x7, 6)
    hs_div = (a[0] >> 5) + 4
    n1 = (((a[0] & 0x1F) << 2) | (a[1] >> 6)) + 1
    rfreq = np.uint64(
        (((a[1] & 0x3F) << 32) | (a[2] << 24) |
         (a[3] << 16) | (a[4] << 8) | a[5])
    ) / (2**28)
    # default start frequency using pynq
    default = 148.5
    fdco = default * n1 * hs_div
    fxtal = fdco / rfreq

    best = [0, 0, 6000.0]
    for i in range(0, 65):
        n1_i = i * 2
        if i == 0:
            n1_i = 1
        for hsdiv_i in [4, 5, 6, 7, 9, 11]:
            fdco_i = new_freq * n1_i * hsdiv_i
            if (fdco_i > 4850.0) and (fdco_i < 5670.0):
                # print(n1_i-1, hsdiv_i-4, fdco_i)
                if fdco_i < best[2]:
                    best = [n1_i, hsdiv_i, fdco_i]

    rfreq = int(best[2] * float(2**28) / fxtal)
    # rfreq_i = int(best[2] / fxtal)
    n1 = best[0] - 1
    hs_div = best[1] - 4

    reg = []
    # build registers
    reg7 = (hs_div << 5) | ((n1 & 0x7C) >> 2)  # reg 7: hs_div[2:0], n1[6:2]
    reg8 = ((n1 & 3) << 6) | (rfreq >> 32)  # reg 8: n1[1:0] rfreq[37:32]
    reg9 = (rfreq >> 24) & 0xFF  # reg 9: rfreq[31:24]
    reg10 = (rfreq >> 16) & 0xFF  # reg 10: rfreq[23:16]
    reg11 = (rfreq >> 8) & 0xFF  # reg 11: rfreq[15:8]
    reg12 = rfreq & 0xFF  # reg 12: rfreq[7:0]

    # write new registers
    reg = [reg7, reg8, reg9, reg10, reg11, reg12]
    bus.write_i2c_block_data(0x5D, 0x7, reg)


class EVR:
    # ========================= Memory Map =================================
    # Addr     Slice     Usage
    # ------------------------
    # 0        [31:0]    gty_evr_status_axi
    ADDR_GTY_STATUS = (0, 0, 31)  # (rx_aligned_sys, reset_tx_done,
    #                                reset_rx_done, cplllocked,
    #                                reset_all, gty_reset_all)
    # 1        [31:0]    gty_rx_reset_cnt
    ADDR_GTY_RX_RESET_CNT = (1, 0, 31)
    # 2        [0:0]     evr_timestamp_valid
    ADDR_EVR_TVALID = (2, 0, 0)  # (reg_num, bitlow, bithigh)
    # 3        [15:0]    evr_evcnt
    ADDR_EVR_EVCNT = (3, 0, 15)
    # 4        [31:0]    evr_live_ts_lo
    ADDR_EVR_TS_LO = (4, 0, 31)
    # 5        [31:0]    evr_live_ts_hi
    ADDR_EVR_TS_HI = (5, 0, 31)
    # 6        [31:0]    si570_freq
    ADDR_SI570_FREQ = (6, 0, 31)
    # 7        [31:0]    gty_rx_freq
    ADDR_GTY_RX_CLK = (7, 0, 31)
    # 8        [0:0]     reset_all
    ADDR_RESET_ALL = (8, 0, 0)
    # 9        [0:0]     rx_slide_req
    ADDR_RX_SLIDER = (9, 0, 0)
    _map = {
        "gty_status": ADDR_GTY_STATUS,
        "gty_resets": ADDR_GTY_RX_RESET_CNT,
        "resetall": ADDR_RESET_ALL,
        "rx_slide": ADDR_RX_SLIDER,
        "evr_tvalid": ADDR_EVR_TVALID,
        "evr_evcnt": ADDR_EVR_EVCNT,
        "evr_ts_lo": ADDR_EVR_TS_LO,
        "evr_ts_hi": ADDR_EVR_TS_HI,
        "si570_freq": ADDR_SI570_FREQ,
        "gty_rx_freq": ADDR_GTY_RX_CLK,
    }

    def __init__(self, ip_dict_entry,
                 si570_freq_expect=156.1375e6,
                 rx_freq_expect=124.91e6):
        base = ip_dict_entry["phys_addr"]
        self._mem = {}
        for reg, addr in self._map.items():
            base_addr = base + 4 * addr[0]  # 32-bit access
            self._mem[reg] = MMIO(base_addr)
        si570_freq = self.measure_freq("si570_freq")
        rx_freq = self.measure_freq("gty_rx_freq")
        # self.read_evr_regs()
        print(f"si570_freq : {si570_freq * 1e-6:8.5f} MHz")
        print(f"gty_rx_freq: {rx_freq * 1e-6:8.5f} MHz")
        gty_status = self.read_reg("gty_status")
        assert gty_status == 0x3C, "GTY is not aligned."
        print(f"GTY status: 0x{gty_status:x}, GTY is aligned.")
        self.check_freq(si570_freq, si570_freq_expect)
        self.check_freq(rx_freq, rx_freq_expect)
        self.check_reset_cnt("gty_resets")

    def write_reg(self, regname, val):
        return self._mem[regname].write(0, val)

    def read_reg(self, regname):
        return self._mem[regname].read()

    def measure_freq(self, reg, rw=24, f_ref=100.0e6):
        freq_hz = (self.read_reg(reg) / (2**rw)) * f_ref
        return freq_hz

    def check_freq(self, freq, freq_expect, tolerance_ppm=200.0):
        ppm = ((freq / freq_expect) - 1.0) * 1e6
        assert abs(ppm) < tolerance_ppm, \
            f"Freq is out of spec by {ppm:3.0f} ppm"

    def check_reset_cnt(self, reg_name, delay=1):
        init_val = self.read_reg(reg_name)
        time.sleep(delay)
        new_val = self.read_reg(reg_name)
        if new_val > init_val:
            print(f"BAD:'{reg_name}' has incremented")

    def read_evr_regs(self):
        gty_status = self.read_reg("gty_status")
        assert gty_status == 0x3C, "GTY is not aligned."
        print(f"GTY status 0x: {gty_status:x}")
        evcnt = self.read_reg("evr_evcnt")
        tslo = self.read_reg("evr_ts_lo")
        tshi = self.read_reg("evr_ts_hi")
        print(f"EVR special events count: {evcnt}")
        print(f"EVR timestamp higher: {tshi:d}, lower: {tslo:d} ")


def resolve_binary_path(bitfile_name):
    """this helper function is necessary to
    locate the bit file during overlay loading"""
    if os.path.isfile(bitfile_name):
        return bitfile_name
    elif os.path.isfile(os.path.join(MODULE_PATH, bitfile_name)):
        return os.path.join(MODULE_PATH, bitfile_name)
    else:
        raise FileNotFoundError(f"Cannot find {bitfile_name}.")
