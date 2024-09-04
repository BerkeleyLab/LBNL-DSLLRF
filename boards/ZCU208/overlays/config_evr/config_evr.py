# A simple overlay to reset GTY and check for alignement. Also verify EVR registers
import pynq
import os
import time
import numpy as np
from pynq import Overlay, MMIO
from smbus2 import SMBus, i2c_msg

MODULE_PATH = os.path.dirname(os.path.realpath(__file__))

class CONFIG_EVR(Overlay):
    def __init__(self, bitfile_name="config_evr.bit", **kwargs):
        board = os.getenv("BOARD")
        super().__init__(resolve_binary_path(bitfile_name), **kwargs)

def ConfigSI570(new_freq=156.1375):
    bus = SMBus(1, force=True)
    bus.write_byte_data(0x74, 0, 0x8)
    # get current settings
    a = bus.read_i2c_block_data(0x5d, 0x7, 6)
    hs_div = (a[0] >> 5) + 4
    n1 = (((a[0] & 0x1f) << 2) | (a[1] >> 6)) + 1
    rfreq = np.uint64((((a[1] & 0x3f) << 32) | (a[2] << 24) | (a[3] << 16) | (a[4] << 8) | a[5])) / (2**28)
    # default start frequency using pynq
    default = 148.5
    fdco = default * n1 * hs_div
    fxtal = fdco / rfreq

    best = [0, 0, 6000.0]
    for i in range(0, 65):
        n1_i = i*2
        if i == 0:
            n1_i = 1
        for hsdiv_i in [4, 5, 6, 7, 9, 11]:
            fdco_i = new_freq * n1_i * hsdiv_i
            if (fdco_i > 4850.0) and (fdco_i < 5670.0):
                # print(n1_i-1, hsdiv_i-4, fdco_i)
                if fdco_i < best[2]:
                    best = [n1_i, hsdiv_i, fdco_i]

    rfreq = int(best[2] * float(2**28) / fxtal)
    rfreq_i = int(best[2] / fxtal)
    n1 = best[0]-1
    hs_div = best[1]-4

    reg = []
    # build registers
    reg7 = (hs_div << 5) | ((n1 & 0x7C) >> 2)  # reg 7: hs_div[2:0], n1[6:2]
    reg8 = ((n1 & 3) << 6) | (rfreq >> 32)  # reg 8: n1[1:0] rfreq[37:32]
    reg9 = (rfreq >> 24) & 0xff  # reg 9: rfreq[31:24]
    reg10 = (rfreq >> 16) & 0xff  # reg 10: rfreq[23:16]
    reg11 = (rfreq >> 8) & 0xff  # reg 11: rfreq[15:8]
    reg12 = rfreq & 0xff  # reg 12: rfreq[7:0]

    # write new registers
    reg = [reg7, reg8, reg9, reg10, reg11, reg12]
    bus.write_i2c_block_data(0x5d, 0x7, reg)

    
class ResetGTY():
# ========================= Memory Map =================================
    # Addr     Slice     Usage
    # ------------------------
    # 0        [31:0]    csr
    ADDR_CSR = (0, 0, 31) # (reg_num, bitlow, bithigh)
    # 1        [31:0]   us_since_boot
    ADDR_US_SINCE_BOOT = (1, 0, 31)
    # 2        [0:0]    evr_timestamp_valid
    ADDR_EVR_TVALID = (2, 0, 0) # (reg_num, bitlow, bithigh)
    # 3        [15:0]   evr_evcnt
    ADDR_EVR_EVCNT = (3, 0, 15)
    # 4        [31:0]    evr_live_ts_lo
    ADDR_EVR_TS_LO = (4, 0, 31)
    # 5        [31:0]    evr_live_ts_hi
    ADDR_EVR_TS_HI = (5, 0, 31)
    # 6        [31:0]    si570_freq
    ADDR_SI570_FREQ = (6, 0, 31)
    # 7        [31:0]   gty_rx_freq
    ADDR_GTY_RX_CLK = (7, 0, 31)
     # 8        [0:0]    reset_all
    ADDR_RESET_ALL = (8, 0, 0)
    # 9        [0:0]    rx_slide_req
    ADDR_RX_SLIDER = (9, 0, 0)
    _map = {
        "csr": ADDR_CSR,
        "us_since_boot": ADDR_US_SINCE_BOOT,
        "resetall": ADDR_RESET_ALL,
        "rx_slide": ADDR_RX_SLIDER,
        "evr_tvalid": ADDR_EVR_TVALID,
        "evr_evcnt": ADDR_EVR_EVCNT,
        "evr_ts_lo": ADDR_EVR_TS_LO,
        "evr_ts_hi": ADDR_EVR_TS_HI,
        "si570_freq": ADDR_SI570_FREQ,
        "gty_rx_freq" : ADDR_GTY_RX_CLK
    }

    def __init__(self, ip_dict_entry):
        base = ip_dict_entry["phys_addr"]
        self._mem = {}
        for reg, addr in self._map.items():
            base_addr = base + 4*addr[0] # 32-bit access
            self._mem[reg] = MMIO(base_addr)
        # check if Si570 frequency is correct
        self.freq_counter("si570_freq")
        self.reset_gty()
    
    def write_reg(self, regname, val):
        return self._mem[regname].write(0, val)

    def read_reg(self, regname):
        return self._mem[regname].read()
    
    def freq_counter(self, reg, rw=24, f_ref=100.0e6, fin=0, thres=50):
        self._rw = rw
        self._f_ref = f_ref
        self._fin = fin
        self._thres = thres
        self._freq = self.read_reg(reg)
        data = self._freq
        freq_hz = (data/(2**self._rw))*self._f_ref
        print(f"{reg}: {freq_hz*1.0e-6} MHz")
        if self._fin != 0:
            self.check(self._fin, freq_hz*1.0e-6, self._thres)
        return freq_hz

    def check(self, fin, freq_hz, thres):
        ppm = ((fin)*(1/freq_hz) - 1.0)*1e6
        if (abs(ppm) >= thres):
            raise ValueError(f"Final frequency measurement is not correct, out of spec by {ppm} ppm")

    def reset_gty(self):
        # SI570 needs atleast 10ms before using it
        # this might be an overkill
        time.sleep(10)
        self.write_reg("resetall", 1)
        time.sleep(5)
        self.write_reg("resetall", 0)
        time.sleep(5)
        reg_val = self.read_reg("csr")
        if ((reg_val & 0xf0) != 0x70):
            print(f"GTY didn't reset")
        self.mgtCrankRxAligner()
        self.freq_counter("gty_rx_freq", fin=124.91)
        self.read_evr_regs()

    def microsecondSpin(self, us):
        then = self.read_reg("us_since_boot")
        while (self.read_reg("us_since_boot") - then) <= us:
            continue

    def mgtCrankRxAligner(self):
        lostAlignmentCount = 0
        rxSlideCount = 0
        whenEntered = 0
        resetCount = 0
        state = "S_APPLY_RESET"
        oldState = state

        while True:
            if state == "S_APPLY_RESET":
                reg_val = self.read_reg("csr")
                self.write_reg("resetall", 1)
                state = "S_HOLD_RESET"

            elif state == "S_HOLD_RESET":
                if self.read_reg("us_since_boot") - whenEntered > 10:
                    resetCount += 1
                    if (resetCount % 1000000) == 0:
                        print(f"GTY reset count {resetCount}")
                    self.write_reg("resetall", 0)
                    state = "S_AWAIT_RESET_COMPLETION"

            elif state == "S_AWAIT_RESET_COMPLETION":
                csr_val3 = self.read_reg("csr")
                # check if it's already aligned??
                if ((csr_val3 & 0xf0) == 0x70 or (csr_val3 & 0xf0) == 0xf0):
                    state = "S_POST_RESET_DELAY"
                elif self.read_reg("us_since_boot") - whenEntered > 250000:
                    reg_val = self.read_reg("csr")
                    print(f"csr = 0x{reg_val:x}")
                    print(f"GTY reset incomplete")
                    state = "S_APPLY_RESET"

            elif state == "S_POST_RESET_DELAY":
                if self.read_reg("us_since_boot") - whenEntered > 200:
                    state = "S_CONFIRM_ALIGNMENT"

            elif state == "S_CONFIRM_ALIGNMENT":
                csr_val5 = self.read_reg("csr")
                if ((csr_val5 & 0xf0) != 0xf0):
                    state = "S_APPLY_RESET"
                elif self.read_reg("us_since_boot") - whenEntered > 1000:
                    state = "S_ALIGNMENT_ACHIEVED"

            elif state == "S_ALIGNMENT_ACHIEVED":
                print(f"GTY aligned after {resetCount} resets.")
                resetCount = 0
                # TODO: Figure this out??
                # hwlib.rfDCsync()
                state = "S_ALIGNED"

            elif state == "S_ALIGNED":
                csr_val8 = self.read_reg("csr")
                if ((csr_val8 & 0xf0) != 0xf0):
                    print(f"GTY misaligned after %u us. Bad K:%d Char:%d\n",
                          self.read_reg("us_since_boot") - whenEntered,
                          self.read_reg("csr"),
                          self.read_reg("csr"));
                    lostAlignmentCount += 1
                    state = "S_APPLY_RESET"

            if state != oldState:
                whenEntered = self.read_reg("us_since_boot")
                oldState = state

            if state == "S_ALIGNED":
                break

        return state == "S_ALIGNED"

    def read_evr_regs(self):
        time.sleep(5)
        tvalid = self.read_reg("evr_tvalid")
        csr_val8 = self.read_reg("csr")
        if (((csr_val8 & 0xf0) != 0xf0) and (tvalid != 1)):
            raise ValueError(f"GTY is not aligned and EVR timestamp is not valid")
        else:
            print(f"GTY is aligned and EVR timestamps are valid")
        csr = self.read_reg("csr")
        print(f"CSR 0x: {csr:x}")
        evcnt = self.read_reg("evr_evcnt")
        tslo = self.read_reg("evr_ts_lo")
        tshi = self.read_reg("evr_ts_hi")
        print(f"EVR special events count: {evcnt}")
        print(f"EVR timestamp higher 32-bits: {tshi:d}, lower 32-bits: {tslo:d} ")
        csr = self.read_reg("csr")
        print(f"CSR 0x: {csr:x}")


def resolve_binary_path(bitfile_name):
    """ this helper function is necessary to locate the bit file during overlay loading"""
    if os.path.isfile(bitfile_name):
        return bitfile_name
    elif os.path.isfile(os.path.join(MODULE_PATH, bitfile_name)):
        return os.path.join(MODULE_PATH, bitfile_name)
    else:
        raise FileNotFoundError(f"Cannot find {bitfile_name}.")
