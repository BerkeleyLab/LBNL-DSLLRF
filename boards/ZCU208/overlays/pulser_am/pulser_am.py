from pynq import Overlay, MMIO
import xrfclk
import numpy as np
import time
import os
import subprocess

# For dds
from fractions import Fraction

MODULE_PATH = os.path.dirname(os.path.realpath(__file__))
CLOCKWIZARD_LOCK_ADDRESS = 0x0004
CLOCKWIZARD_RESET_ADDRESS = 0x0000
CLOCKWIZARD_RESET_TOKEN = 0x000A

# MHz
ZCU208_LMK_FREQ = 500.0
ZCU208_LMX_FREQ = 4000.0

MTS_START_TILE = 0x01
MAX_DAC_TILES = 4
MAX_ADC_TILES = 4
DAC_REF_TILE = 2
ADC_REF_TILE = 2

ZCU208_DAC_TILES = 0b0110
ZCU208_ADC_TILES = 0b0110


class PulserAMOverlay(Overlay):
    def __init__(self, bitfile_name="pulser_am.bit", **kwargs):
        board = os.getenv("BOARD")
        # Run lsmod command to get the loaded modules list
        output = subprocess.check_output(["lsmod"])
        # Check if "zocl" is present in the output
        if b"zocl" in output:
            # If present, remove the module using rmmod command
            rmmod_output = subprocess.run(["rmmod", "zocl"])
            # Check return code
            assert (rmmod_output.returncode == 0), "Could not restart zocl."
            "Please Shutdown All Kernels and then restart"
            # If successful, load the module using modprobe command
            modprobe_output = subprocess.run(["modprobe", "zocl"])
            assert (
                modprobe_output.returncode == 0
            ), "Could not restart zocl. It did not restart as expected"
        else:
            modprobe_output = subprocess.run(["modprobe", "zocl"])
            # Check return code
            assert modprobe_output.returncode == 0, "Could not restart ZOCL!"

        # must configure clock synthesizers
        # the LMK04828 PL_CLK and PL_SYSREF clocks
        if board == "ZCU208":
            xrfclk.set_ref_clks(
                lmk_freq=ZCU208_LMK_FREQ, lmx_freq=ZCU208_LMX_FREQ
            )  # MHz
            self.ACTIVE_DAC_TILES = ZCU208_DAC_TILES
            self.ACTIVE_ADC_TILES = ZCU208_ADC_TILES
        else:
            assert False, "Board Not Supported"
        time.sleep(0.5)
        super().__init__(resolve_binary_path(bitfile_name), **kwargs)

        self.xrfdc = self.rfdc
        self.xrfdc.mts_dac_config.RefTile = (
            DAC_REF_TILE  # DAC tile distributing reference clock
        )
        self.xrfdc.mts_adc_config.RefTile = ADC_REF_TILE  # ADC

        # Pulse Generator
        self.pulser = PulseGen(self.ip_dict["pulser_axis_0"], count_width=32)

        # DAC Capture Memory - to verify DAC AWG for diagnostics
        self.dac_capture = self.memdict_to_view("hier_dac_cap/axi_bram_ctrl_0")

        # ADC Capture Memories
        nchannels = 2
        self.mode_iq = True
        self.adc_captures = [
            ("hier_adc10_I_cap/axi_bram_ctrl_0",
             "hier_adc10_Q_cap/axi_bram_ctrl_0"),
            ("hier_adc20_I_cap/axi_bram_ctrl_0",
             "hier_adc20_Q_cap/axi_bram_ctrl_0")]
        for nchan in range(nchannels):
            s_i = self.adc_captures[nchan][0]
            chan_i = self.memdict_to_view(s_i)
            if self.mode_iq:
                s_q = self.adc_captures[nchan][1]
                chan_q = self.memdict_to_view(s_q)
                self.adc_captures[nchan] = (chan_i, chan_q)
            else:
                self.adc_captures[nchan] = (chan_i,)
        self.nchannels_adc = nchannels
        if self.mode_iq:
            self.nadc_mem_total = 2 * self.nchannels_adc
        else:
            self.nadc_mem_total = self.nchannels_adc

    def memdict_to_view(self, ip, dtype="int16"):
        """Configures access to internal memory via MMIO"""
        baseAddress = self.mem_dict[ip]["phys_addr"]
        mem_range = self.mem_dict[ip]["addr_range"]
        ipmmio = MMIO(baseAddress, mem_range)
        return ipmmio.array[0:ipmmio.length].view(dtype)

    def verify_clock_tree(self):
        """Verify the PL and PL_SYSREF clocks are active
        by verifying an MMCM is in the LOCKED state"""
        Xstatus = self.clocktreeMTS.MTSclkwiz.read(
            CLOCKWIZARD_LOCK_ADDRESS
        )  # reads the LOCK register
        # the ClockWizard AXILite registers are NOT fully mapped:
        # refer to PG065
        if Xstatus != 1:
            raise Exception(
                "The MTS ClockTree has failed to LOCK."
                "Please verify board clocking configuration"
            )

    def init_tile_sync(self):
        """Resets the MTS alignment engine"""
        self.xrfdc.mts_dac_config.Tiles = 0b0100  # turn only one tile on first
        self.xrfdc.mts_adc_config.Tiles = 0b0100
        self.xrfdc.mts_dac_config.SysRef_Enable = 1
        self.xrfdc.mts_adc_config.SysRef_Enable = 1
        self.xrfdc.mts_dac_config.Target_Latency = -1
        self.xrfdc.mts_adc_config.Target_Latency = -1
        self.xrfdc.mts_dac()
        self.xrfdc.mts_adc()
        # Reset MTS ClockWizard MMCM - refer to PG065
        self.clocktreeMTS.MTSclkwiz.mmio.write_reg(
            CLOCKWIZARD_RESET_ADDRESS, CLOCKWIZARD_RESET_TOKEN
        )
        time.sleep(0.1)
        # Reset only user selected DAC tiles
        bitvector = self.ACTIVE_DAC_TILES
        for n in range(MAX_DAC_TILES):
            if bitvector & 0x1:
                self.xrfdc.dac_tiles[n].Reset()
            bitvector = bitvector >> 1
        # Reset ADC FIFO of only user selected tiles - restarts MTS engine
        for toggleValue in range(0, 1):
            bitvector = self.ACTIVE_ADC_TILES
            for n in range(MAX_ADC_TILES):
                if bitvector & 0x1:
                    self.xrfdc.adc_tiles[n].SetupFIFOBoth(toggleValue)
                bitvector = bitvector >> 1

    def sync_tiles(self, dacTarget=-1, adcTarget=-1):
        """Configures RFSoC MTS alignment"""
        # Set which RF tiles use MTS and turn MTS off
        if self.ACTIVE_DAC_TILES > 0:
            self.xrfdc.mts_dac_config.Tiles = (
                self.ACTIVE_DAC_TILES
            )  # group defined in binary 0b1111
            self.xrfdc.mts_dac_config.SysRef_Enable = 1
            self.xrfdc.mts_dac_config.Target_Latency = dacTarget
            self.xrfdc.mts_dac()
        else:
            self.xrfdc.mts_dac_config.Tiles = 0x0
            self.xrfdc.mts_dac_config.SysRef_Enable = 0
        if self.ACTIVE_ADC_TILES > 0:
            self.xrfdc.mts_adc_config.Tiles = self.ACTIVE_ADC_TILES
            self.xrfdc.mts_adc_config.SysRef_Enable = 1
            self.xrfdc.mts_adc_config.Target_Latency = adcTarget
            self.xrfdc.mts_adc()
        else:
            self.xrfdc.mts_adc_config.Tiles = 0x0
            self.xrfdc.mts_adc_config.SysRef_Enable = 0

    def trigger_capture(self):
        """Internal loopback of DAC waveform to internal capture mirror"""
        self.pulser.trigger()
        return

    def internal_capture(self, membuffer):
        """Captures ADC samples from all channels
        and stores to internal memories"""
        if not np.issubdtype(membuffer.dtype, np.int16):
            raise Exception("buffer not defined or np.int16!")
        if not membuffer.shape[0] == self.nadc_mem_total:
            raise Exception(
                "buffer must be of shape({}, N)!".format(self.nadc_mem_total)
            )
        self.trigger_capture()
        for n in range(self.nchannels_adc):
            n_i = 2 * n
            n_q = n_i + 1
            membuffer[n_i] = np.copy(self.adc_captures[n][0]
                                     [0:len(membuffer[n_i])])
            if self.mode_iq:
                membuffer[n_q] = np.copy(
                    self.adc_captures[n][1][0:len(membuffer[n_q])]
                )
        return


def resolve_binary_path(bitfile_name):
    """this helper function is necessary to locate
    the bit file during overlay loading"""
    if os.path.isfile(bitfile_name):
        return bitfile_name
    elif os.path.isfile(os.path.join(MODULE_PATH, bitfile_name)):
        return os.path.join(MODULE_PATH, bitfile_name)
    else:
        raise FileNotFoundError(f"Cannot find {bitfile_name}.")


# -------------------------------------------------------------------------------------------------


class PulseGen:
    # ========================= Memory Map =================================
    # Addr     Slice     Usage
    # ------------------------
    # 0        [11:0]    phase_step_l
    ADDR_PHASE_STEP_L = (0, 0, 11)  # (reg_num, bitlow, bithigh)
    # 0        [31:12]   phase_step_h
    ADDR_PHASE_STEP_H = (0, 12, 31)
    # 1        [11:0]    modulo
    ADDR_MODULO = (1, 0, 11)
    # 2        [CW-1:0]  count_max
    # Default max can be clobbered at initialization
    ADDR_COUNT_MAX = (2, 0, 7)
    # 3        [13:0]    amplitude
    ADDR_AMPLITUDE = (3, 0, 13)
    # 4        [0:0]     sw_trig
    ADDR_SW_TRIG = (4, 0, 0)
    # 5        [0:0]     enable
    ADDR_ENABLE = (5, 0, 0)
    # 6        [31:0]    trigger_counts (read-only)
    ADDR_TRIG_COUNTS = (6, 0, 31)
    # 7        [0:0]     enable
    ADDR_FORCE_ON = (7, 0, 0)
    _map = {
        "phase_step_l": ADDR_PHASE_STEP_L,
        "phase_step_h": ADDR_PHASE_STEP_H,
        "modulo": ADDR_MODULO,
        "count_max": ADDR_COUNT_MAX,
        "amplitude": ADDR_AMPLITUDE,
        "sw_trig": ADDR_SW_TRIG,
        "enable": ADDR_ENABLE,
        "trig_counts": ADDR_TRIG_COUNTS,
        "force_on": ADDR_FORCE_ON,
    }

    def __init__(self, ip_dict_item, count_width=8,
                 fclk=250.0e6, dwh=20, dwl=12):
        self._dwh = dwh
        self._dwl = dwl
        base = ip_dict_item["phys_addr"]
        self.count_width = count_width
        self._fclk = fclk
        # Clobber count_max memory map to map to the correct count_width
        addr_count_max = self._map["count_max"]
        self._map["count_max"] = (
            addr_count_max[0],
            addr_count_max[1],
            addr_count_max[1] + count_width - 1,
        )
        self._mem = {}
        # Only create a single MMIO instance if
        # two values are mapped to the same register
        addr_l = self._map["phase_step_l"]
        addr_h = self._map["phase_step_h"]
        merged_ph = addr_l[0] == addr_h[0]
        if merged_ph:
            phase_mmio = MMIO(base + 4 * addr_l[0])  # 32-bit access

        for reg, addr in self._map.items():
            base_addr = base + 4 * addr[0]  # 32-bit access
            if merged_ph and reg in ("phase_step_l", "phase_step_h"):
                # Two references to the same MMIO instance
                self._mem[reg] = phase_mmio
            else:
                # New MMIO for every register
                self._mem[reg] = MMIO(base_addr)
        self.force_off()

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

    def force_on(self):
        return self.write("force_on", 1)

    def force_off(self):
        return self.write("force_on", 0)

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

    def get_dds(self):
        pl = self.read_field("phase_step_l")
        ph = self.read_field("phase_step_h")
        mod = self.read_field("modulo")
        print("phase_step_l = {}".format(pl))
        print("phase_step_h = {}".format(ph))
        print("modulo = {}".format(mod))
        check_ratio = invert_dds(
            ph, pl, mod, dwh=self._dwh, dwl=self._dwl
        )
        check_fdds = self._fclk * check_ratio
        return check_fdds

    def set_dds_freq(self, fdds):
        ph, pl, mod = get_dds_config(self._fclk, fdds,
                                     dwh=self._dwh, dwl=self._dwl)
        self.set_dds(ph, pl, mod)
        return

    def write_reg(self, regname, val):
        return self._mem[regname].write(0, val)

    def read_reg(self, regname):
        return self._mem[regname].read()

    def write_field(self, regname, val):
        shift = self._map[regname][1]
        return self._mem[regname].write(0, (val << shift))

    def read_field(self, regname):
        shift = self._map[regname][1]
        return self._mem[regname].read() >> shift


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


def calc_num_den(f_ref, freq):
    lo_ratio = Fraction(str(f_ref)).limit_denominator(10e9)
    ref2out_ratio = float(freq) / float(lo_ratio)
    ref2out = Fraction(str(ref2out_ratio)).limit_denominator(1000000000)
    num = ref2out.numerator
    den = ref2out.denominator
    return num, den


# calculate registers by given fractional frequency
def calc_dds(num_dds, den_dds, dwh=20, dwl=12):
    m, modulo = divmod((1 << dwl), den_dds)
    r = (1 << dwh) * num_dds
    phase_step_h = int(r / den_dds)
    phase_step_l = int(r % den_dds * m)
    return phase_step_h, phase_step_l, modulo


def get_dds_config(fclk, fdds, dwh=20, dwl=12):
    num, den = calc_num_den(fclk, fdds)
    phase_step_h, phase_step_l, modulo = calc_dds(num, den, dwh, dwl)
    return phase_step_h, phase_step_l, modulo


def invert_dds(phase_step_h, phase_step_l, modulo, dwh=32, dwl=12):
    """Return num/den = f_dds/f_clk given
    phase_step_h, phase_step_l, and modulo."""
    m_den_dds = (1 << dwl) - modulo
    m_r = phase_step_h * m_den_dds + phase_step_l
    m_num_dds = m_r / (1 << dwh)
    return m_num_dds / m_den_dds
