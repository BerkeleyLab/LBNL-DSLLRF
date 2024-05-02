# -------------------------------------------------------------------------------------------------
# Heavily-modified version of the Multi-Tile Synch (mts) example from Xilinx
# Copyright (C) 2023 Advanced Micro Devices, Inc
# SPDX-License-Identifier: MIT
# ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- --
import pynq
from pynq import Overlay, MMIO
import xrfclk
import xrfdc
import numpy as np
import time
import os
import subprocess

MODULE_PATH = os.path.dirname(os.path.realpath(__file__))
CLOCKWIZARD_LOCK_ADDRESS = 0x0004
CLOCKWIZARD_RESET_ADDRESS = 0x0000
CLOCKWIZARD_RESET_TOKEN = 0x000A

class CapturePulserOverlay(Overlay):
    def __init__(self, bitfile_name='pulser_mts.bit', **kwargs):
        board = os.getenv('BOARD') 
        # Run lsmod command to get the loaded modules list
        output = subprocess.check_output(['lsmod'])
        # Check if "zocl" is present in the output
        if b'zocl' in output:
            # If present, remove the module using rmmod command
            rmmod_output = subprocess.run(['rmmod', 'zocl'])
            # Check return code
            assert rmmod_output.returncode == 0, "Could not restart zocl. Please Shutdown All Kernels and then restart"
            # If successful, load the module using modprobe command
            modprobe_output = subprocess.run(['modprobe', 'zocl'])
            assert modprobe_output.returncode == 0, "Could not restart zocl. It did not restart as expected"
        else:
            modprobe_output = subprocess.run(['modprobe', 'zocl'])
            # Check return code
            assert modprobe_output.returncode == 0, "Could not restart ZOCL!"

        # must configure clock synthesizers 
        # the LMK04828 PL_CLK and PL_SYSREF clocks
        if board == 'ZCU208':
            xrfclk.set_ref_clks(lmk_freq = ZCU208_LMK_FREQ, lmx_freq = ZCU208_LMX_FREQ)
        else:
            assert false, "Board Not Supported"
        time.sleep(0.5)
        super().__init__(resolve_binary_path(bitfile_name), **kwargs)

        # map PL GPIO registers
        self.trig_cap = self.gpio_control.axi_gpio_bram_adc.channel1[0]

        # DAC Player Memory - DACs will play this waveform
        self.pulser = PulseGen(self.ip_dict["pulser_axis_0"])

        # DAC Capture Memory - to verify DAC AWG for diagnostics
        self.dac_capture = self.memdict_to_view("hier_dac_cap/axi_bram_ctrl_0")

        # Reset GPIOs and bring to known state
        self.trig_cap.off()

    def memdict_to_view(self, ip, dtype='int16'):
        """ Configures access to internal memory via MMIO"""
        baseAddress = self.mem_dict[ip]["phys_addr"]
        mem_range = self.mem_dict[ip]["addr_range"]
        ipmmio = MMIO(baseAddress, mem_range)
        return ipmmio.array[0:ipmmio.length].view(dtype)

    def verify_clock_tree(self):
        """ Verify the PL and PL_SYSREF clocks are active by verifying an MMCM is in the LOCKED state"""
        Xstatus = self.clocktreeMTS.MTSclkwiz.read(CLOCKWIZARD_LOCK_ADDRESS) # reads the LOCK register
        # the ClockWizard AXILite registers are NOT fully mapped: refer to PG065
        if (Xstatus != 1):
            raise Exception("The MTS ClockTree has failed to LOCK. Please verify board clocking configuration")

    def trigger_capture(self):
        """ Internal loopback of DAC waveform to internal capture mirror"""
        self.trig_cap.off()
        self.trig_cap.on() # triggers ADCs to capture and pulser to begin
        #self.pulser.trigger()
        time.sleep(0.5)
        self.trig_cap.off()

    def internal_capture(self, doublebuffer):
        """ Captures ADC samples from two channels and stores to internal memories """
        if not np.issubdtype(doublebuffer.dtype, np.int16):
            raise Exception("buffer not defined or np.int16!")
        if not doublebuffer.shape[0] == 2:
            raise Exception("buffer must be of shape(2, N)!")
        self.trigger_capture()
        doublebuffer[0] = np.copy(self.adc_capture_ch1[0:len(doublebuffer[0])])
        doublebuffer[1] = np.copy(self.adc_capture_ch2[0:len(doublebuffer[1])])

def resolve_binary_path(bitfile_name):
    """ this helper function is necessary to locate the bit file during overlay loading"""
    if os.path.isfile(bitfile_name):
        return bitfile_name
    elif os.path.isfile(os.path.join(MODULE_PATH, bitfile_name)):
        return os.path.join(MODULE_PATH, bitfile_name)
    else:
        raise FileNotFoundError(f'Cannot find {bitfile_name}.')
# -------------------------------------------------------------------------------------------------

class PulseGen():
    # ========================= Memory Map =================================
    # Addr     Slice     Usage
    # ------------------------
    # 0        [11:0]    phase_step_l
    ADDR_PHASE_STEP_L = (0, 0, 11) # (reg_num, bitlow, bithigh)
    # 0        [31:12]   phase_step_h
    ADDR_PHASE_STEP_H = (0, 12, 31)
    # 1        [11:0]    modulo
    ADDR_MODULO = (1, 0, 11)
    # 2        [CW-1:0]  count_max
    ADDR_COUNT_MAX = (2, 0, 7) # Default max can be clobbered at initialization
    # 3        [13:0]    amplitude
    ADDR_AMPLITUDE = (3, 0, 13)
    # 4        [0:0]     sw_trig
    ADDR_SW_TRIG = (4, 0, 0)
    # 5        [0:0]     enable
    ADDR_ENABLE = (5, 0, 0)
    # 6        [31:0]    trigger_counts (read-only)
    ADDR_TRIG_COUNTS = (6, 0, 31)
    _map = {
        "phase_step_l": ADDR_PHASE_STEP_L,
        "phase_step_h": ADDR_PHASE_STEP_H,
        "modulo": ADDR_MODULO,
        "count_max": ADDR_COUNT_MAX,
        "amplitude": ADDR_AMPLITUDE,
        "sw_trig": ADDR_SW_TRIG,
        "enable": ADDR_ENABLE,
        "trig_counts": ADDR_TRIG_COUNTS,
    }
    def __init__(self, ip_dict_item, count_width=8):
        base = ip_dict_item["phys_addr"]
        # Clobber count_max memory map to map to the correct count_width
        addr_count_max = self._map["count_max"]
        self._map["count_max"] = (addr_count_max[0], addr_count_max[1], addr_count_max[1] + count_width-1)
        self._mem = {}
        # Only create a single MMIO instance if two values are mapped to the same register
        addr_l = self._map["phase_step_l"]
        addr_h = self._map["phase_step_h"]
        merged_ph = addr_l[0] == addr_h[0]
        if merged_ph:
            phase_mmio = MMIO(base + 4*addr_l[0]) # 32-bit access

        for reg, addr in self._map.items():
            base_addr = base + 4*addr[0] # 32-bit access
            if merged_ph and reg in ("phase_step_l", "phase_step_h"):
                # Two references to the same MMIO instance
                self._mem[reg] = phase_mmio
            else:
                # New MMIO for every register
                self._mem[reg] = MMIO(base_addr)

    def set_count_max(self, val):
        return self.write("count_max", val)

    def get_count_max(self):
        return self.read("count_max")

    def set_amplitude(self, val):
        return self.write("amplitude", val)

    def get_amplitude(self):
        return self.read("amplitude")

    def get_trig_counts(self):
        return self.read("trig_counts")

    def trigger(self):
        # sw_trig is now a strobe internally; no need to write to 0 again.
        self.write("sw_trig", 1)
        return

    def enable(self, enabled=True):
        enabled = int(enabled)
        return self.write("enable", enabled)

    def get_enable(self):
        return self.read("enable")

    def set_dds(self, phase_step_l, phase_step_h, modulo):
        addr_l = self._map["phase_step_l"]
        addr_h = self._map["phase_step_h"]
        addr_m = self._map["modulo"]
        val_l = phase_step_l << addr_l[1]
        val_h = phase_step_h << addr_h[1]
        if addr_l[0] == addr_h[0]:
            # l/h Packed into same register
            ph_step = val_l + val_h
            self.write("phase_step_l", ph_step)
        else:
            # Different registers
            self.write("phase_step_l", val_l)
            self.write("phase_step_h", val_h)
        val_mod = modulo << addr_m[1]
        self.write("modulo", val_mod)
        return

    def write(self, regname, val):
        return self._mem[regname].write(0, val)

    def read(self, regname):
        return self._mem[regname].read()

class Inverter():
    def __init__(self, ip_dict_entry):
        base = ip_dict_entry["phys_addr"]
        self._inv = []
        # The toy "inverter" IP has four channels which invert a different mask of bits
        for n in range(4):
            self._inv.append(MMIO(base+4*n))

    def write(self, ch, val):
        return self._inv[int(ch) & 3].write(0, val)

    def read(self, ch):
        return self._inv[int(ch) & 3].read()

    def test_ch(self, ch):
        ch = int(ch) & 3
        val = 0x12345678
        if ch == 0: # all 32 bits inverted
            inv_val = (~val) & 0xffffffff
        elif ch == 1:
            inv_val = (val & 0xff000000) | ((~val) & 0xffffff)
        elif ch == 2:
            inv_val = (val & 0xffff0000) | ((~val) & 0xffff)
        elif ch == 3:
            inv_val = (val & 0xffffff00) | ((~val) & 0xff)
        self.write(ch, val)
        inv_val_rdbk = self.read(ch)
        print(f"Wrote 0x{val:x}; expected 0x{inv_val:x}; read 0x{inv_val_rdbk:x} ", end="")
        if inv_val_rdbk == inv_val:
            print("PASS")
            return True
        else:
            print("FAIL")
        return False

def calc_num_den(f_ref, freq):
    lo_ratio = Fraction(str(f_ref)).limit_denominator(10e9)
    ref2out_ratio = float(freq)/float(lo_ratio)
    ref2out = Fraction(str(ref2out_ratio)).limit_denominator(1000000000)
    num = ref2out.numerator
    den = ref2out.denominator
    return num, den

# calculate registers by given fractional frequency
def calc_dds(num_dds, den_dds, dwh=32, dwl=12):
    m, modulo = divmod((1 << dwl), den_dds)
    r = (1 << dwh) * num_dds
    phase_step_h = int(r/den_dds)
    phase_step_l = int(r % den_dds * m)
    return phase_step_h, phase_step_l, modulo

def get_dds_config(fclk, fdds, dwh=20, dwl=12):
    num, den = calc_num_den(fclk, fdds)
    phase_step_h, phase_step_l, modulo = calc_dds(num, den, dwh, dwl)
    return phase_step_h, phase_step_l, modulo
