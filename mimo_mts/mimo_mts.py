import pynq
from pynq import Overlay, MMIO
from .utils.boards import board_info
from .utils.config_clk104 import CLK104Config
from .drivers.evr_gty import GTY_EVR
from .drivers.rf_control import RfControl
import xrfdc
import numpy as np
import time
from pathlib import Path
import subprocess
__all__ = ('GTY_EVR', 'RfControl')


class MimoMtsOverlay(Overlay):
    """
    The MTS overlay demonstrates the RFSoC multi-tile
    synchronization capability that enables
    multiple RF DAC and ADC tiles to achieve latency alignment.
    This capability is key to enabling
    Massive MIMO, phased array RADAR applications and beamforming.
    """
    def __init__(self, bitfile_name: str = "mts_8ch.bit",
                 board: str = 'ZCU208',
                 lmk_tcs: str = 'LMK04828.tcs',
                 lmxadc_tcs: str = 'LMX2594.tcs',
                 lmxdac_tcs: str = 'LMX2594.tcs',
                 **kwargs):
        """
        This overlay class supports the MTS overlay.
        It configures the PL gpio, internal memories,
        PL-DRAM and DMA interfaces.
        Additional helper methods are provided to: configure and verify
        MTS, verify the DACRAM and read captured samples from the internal ADC
        memories and the PL-DDR4 memory. In addition to the bitfile_name,
        the active ADC and DAC
        tiles must be provided to use in the MTS initialization.
        """
        self.board = board_info[board]

        # self._restart_zocl()
        self.clk104 = CLK104Config(lmk_tcs, lmxadc_tcs, lmxdac_tcs)
        self.clk104.write_regs()

        super().__init__(resolve_binary_path(bitfile_name), **kwargs)
        """ Check if RFDC IP core is used in the design"""
        if "rfdc" in self.ip_dict:
            self._initialize_dev()
            self._initialize_memories()
            self._initialize_dma()
            self._initialize_mts()
            self._initialize_mixers()

    def _restart_zocl(self):
        """Restart the ZOCL module if necessary."""
        output = subprocess.check_output(["lsmod"])
        if b"zocl" in output:
            rmmod_output = subprocess.run(["rmmod", "zocl"])
            assert rmmod_output.returncode == 0, (
                "Could not restart zocl. Shutdown All Kernels and then restart"
            )
            modprobe_output = subprocess.run(["modprobe", "zocl"])
            assert modprobe_output.returncode == 0, (
                "Could not restart zocl. It did not restart as expected")
        else:
            modprobe_output = subprocess.run(["modprobe", "zocl"])
            assert modprobe_output.returncode == 0, "Could not restart ZOCL!"

    def _initialize_dev(self):
        """Alias xrfdc, rf_control and evr, enumurate rfdc blocks."""
        self.xrfdc = self.rfdc
        self.rf_control = self.axil_rf_control_0
        if 'axil_evr_gty_wrapper_0' in self.ip_dict:
            self.evr = self.axil_evr_gty_wrapper_0

        if self.board.converters_per_tile == 2:
            self.dac_blocks = np.array([
                [self.xrfdc.dac_tiles[i].blocks[j] for j in [0, 2]]
                for i in range(4)])
            self.adc_blocks = np.array([
                [self.xrfdc.adc_tiles[i].blocks[j] for j in [0, 1]]
                for i in range(4)])
        elif self.board.converters_per_tile == 4:
            self.dac_blocks = np.array([
                [self.xrfdc.dac_tiles[i].blocks[j] for j in range(4)]
                for i in range(4)])
            self.adc_blocks = np.array([
                [self.xrfdc.adc_tiles[i].blocks[j] for j in range(4)]
                for i in range(4)])

        self.sysref_freqcnt = self.clocktreeMTS.freqcnt_gpio.channel1
        self.dspclk_freqcnt = self.clocktreeMTS.freqcnt_gpio.channel2

    def convert_freq_to_hz(self, f_cnt, f_ref=100.0e6):
        """Convert the frequency counter value to Hz"""
        return (f_cnt / 2**24) * f_ref

    @property
    def sysref_freq_hz(self):
        return self.convert_freq_to_hz(self.sysref_freqcnt.read())

    @property
    def dspclk_freq_hz(self):
        return self.convert_freq_to_hz(self.dspclk_freqcnt.read())

    def _initialize_memories(self):
        """ Initialize adc / dac waveform buffers. """
        self.dac_player = self.memdict_to_view(
            "transmitter/hier_dac_play/axi_bram_ctrl_0")
        self.dac_capture = self.memdict_to_view(
            "transmitter/hier_dac_cap/axi_bram_ctrl_0")

        self.adc_bufs = []
        for tile in range(self.board.num_adc_tiles):
            for i in range(4):
                self.adc_bufs.append(
                    self.memdict_to_view(
                        f"receiver/m{tile}{i}/axi_bram_ctrl_0"))

    def _initialize_dma(self):
        """Initialize DMA for ADC deep capture."""
        if 'deepCapture/axi_dma_adc' in self.ip_dict:
            self.adc_dma = self.deepCapture.axi_dma_adc  # PL DMA to DDR4
            self.ADCdeepcapture = self.memdict_to_view("ddr4_0")
            dts = pynq.DeviceTreeSegment(resolve_binary_path("ddr4.dtbo"))
            if not dts.is_dtbo_applied():
                dts.insert()

    def _initialize_mts(self):
        """Initialize the MTS engine."""
        self.init_tile_sync()
        self.verify_clock_tree()
        self.sync_tiles()

    def _initialize_mixers(self):
        self.set_dac_mixer_dco(0)
        self.set_adc_mixer_dco(0)

    def memdict_to_view(self, ip, dtype="int16"):
        """Configures access to internal memory via MMIO"""
        baseAddress = self.mem_dict[ip]["phys_addr"]
        mem_range = self.mem_dict[ip]["addr_range"]
        ipmmio = MMIO(baseAddress, mem_range)
        return ipmmio.array[0:ipmmio.length].view(dtype)

    def sync_tiles(self):
        """Configures RFSoC MTS alignment for deterministic latency
        Measured max latency is 112 DAC samples and 88 ADC samples,
        Add margin to the target latency to ensure alignment.
        """
        if self.board.num_dac_tiles > 0:
            self.xrfdc.mts_dac_config.Tiles = self.board.active_dac_tiles
            self.xrfdc.mts_dac_config.SysRef_Enable = 1
            self.xrfdc.mts_dac_config.Target_Latency = \
                self.board.mts_dac_target_latency
            self.xrfdc.mts_dac()
        else:
            self.xrfdc.mts_dac_config.Tiles = 0x0
            self.xrfdc.mts_dac_config.SysRef_Enable = 0
        if self.board.num_adc_tiles > 0:
            self.xrfdc.mts_adc_config.Tiles = self.board.active_adc_tiles
            self.xrfdc.mts_adc_config.SysRef_Enable = 1
            self.xrfdc.mts_adc_config.Target_Latency = \
                self.board.mts_adc_target_latency
            self.xrfdc.mts_adc()
        else:
            self.xrfdc.mts_adc_config.Tiles = 0x0
            self.xrfdc.mts_adc_config.SysRef_Enable = 0

    def init_tile_sync(self):
        """Resets the MTS alignment engine"""
        # Set tile distributing reference clock
        self.xrfdc.mts_adc_init(self.board.adc_ref_index)
        self.xrfdc.mts_dac_init(self.board.dac_ref_index)
        self.xrfdc.mts_dac()
        self.xrfdc.mts_adc()

        # Reset MTS ClockWizard MMCM - refer to PG065
        self.clocktreeMTS.MTSclkwiz.mmio.write_reg(0, 0xA)
        time.sleep(0.1)
        # Reset only user selected DAC tiles
        bitvector = self.board.active_dac_tiles
        for n in range(4):
            if bitvector & 0x1:
                self.xrfdc.dac_tiles[n].Reset()
            bitvector = bitvector >> 1
        # Reset ADC FIFO of only user selected tiles - restarts MTS engine
        for toggleValue in range(0, 1):
            bitvector = self.board.active_adc_tiles
            for n in range(4):
                if bitvector & 0x1:
                    self.xrfdc.adc_tiles[n].SetupFIFOBoth(toggleValue)
                bitvector = bitvector >> 1

    def verify_clock_tree(self):
        """Verify the PL and PL_SYSREF clocks are active
        by verifying an MMCM is in the LOCKED state"""
        # reads the LOCK register
        status = self.clocktreeMTS.MTSclkwiz.read(0x0004)
        # the ClockWizard AXILite registers are NOT fully mapped:
        # refer to PG065
        assert status == 1, "The MTS ClockTree has failed to LOCK."

    def capture_adc_iq_buf(self, i_buffer=None, q_buffer=None):
        """Captures ADC samples from all channels
        Follow PG269, ADC Real input to I/Q output:
          Dual RF-ADC: Figure 57:
            m00_axis_data -> Tile0, ADC0: I7, I6, I5, I4, I3, I2, I1, I0
            m01_axis_data -> Tile0, ADC0: Q7, Q6, Q5, Q4, Q3, Q2, Q1, Q0
            m02_axis_data -> Tile0, ADC1: I7, I6, I5, I4, I3, I2, I1, I0
            m03_axis_data -> Tile0, ADC1: Q7, Q6, Q5, Q4, Q3, Q2, Q1, Q0
        Quad RF-ADC: Figure 63:
            m00_axis_data -> Tile0, ADC0: Q3, I3, Q2, I2, Q1, I1, Q0, I0
            m01_axis_data -> Tile0, ADC1: Q7, Q6, Q5, Q4, Q3, Q2, Q1, Q0
            m02_axis_data -> Tile0, ADC2: Q3, I3, Q2, I2, Q1, I1, Q0, I0
            m03_axis_data -> Tile0, ADC3: Q7, Q6, Q5, Q4, Q3, Q2, Q1, Q0
        """
        length = len(self.adc_bufs[0])
        if self.board.adc_iq_interleave:
            length //= 2  # interleave I/Q samples
        if i_buffer is None:
            i_buffer = np.empty((self.board.n_adcs, length), dtype=np.int16)
        if q_buffer is None:
            q_buffer = np.empty((self.board.n_adcs, length), dtype=np.int16)

        assert np.issubdtype(i_buffer.dtype, np.int16), \
            "i_buffer dtype of np.int16 required."
        assert np.issubdtype(q_buffer.dtype, np.int16), \
            "q_buffer dtype of np.int16 required."

        for i in range(self.board.n_adcs):
            if self.board.adc_iq_interleave:
                np.copyto(i_buffer[i], self.adc_bufs[i][0::2])
                np.copyto(q_buffer[i], self.adc_bufs[i][1::2])
            else:
                np.copyto(i_buffer[i], self.adc_bufs[2*i])
                np.copyto(q_buffer[i], self.adc_bufs[2*i+1])
        return i_buffer, q_buffer

    def set_dac_mixer_dco(self, freq_mhz=0, nyquist=1, phase=0):
        self.xrfdc.mts_dac_config.SysRef_Enable = False

        # Set up mixer settings for each DAC tile
        mixer_settings_dac = {
            'Freq': freq_mhz,
            'PhaseOffset': phase,
            'EventSource': xrfdc.EVNT_SRC_SYSREF,
            'MixerType': xrfdc.MIXER_TYPE_FINE,
            'CoarseMixFreq': xrfdc.COARSE_MIX_OFF,
            'MixerMode': xrfdc.MIXER_MODE_C2R,
            'FineMixerScale': xrfdc.MIXER_SCALE_1P0
        }
        for dac_block in self.dac_blocks.ravel():
            dac_block.NyquistZone = nyquist
            dac_block.MixerSettings = mixer_settings_dac
            # Reset NCO phase
            dac_block.ResetNCOPhase()

        # Configure the MTS to use the SYSREF event source
        self.xrfdc.mts_dac_config.SysRef_Enable = True

    def set_adc_mixer_dco(self, freq_mhz=0, nyquist=1, phase=0):
        self.xrfdc.mts_adc_config.SysRef_Enable = False

        # Set up mixer settings for each ADC tile
        mixer_settings_adc = {
            'Freq': freq_mhz,
            'PhaseOffset': phase,
            'EventSource': xrfdc.EVNT_SRC_SYSREF,
            'MixerType': xrfdc.MIXER_TYPE_FINE,
            'CoarseMixFreq': xrfdc.COARSE_MIX_OFF,
            'MixerMode': xrfdc.MIXER_MODE_R2C,
            'FineMixerScale': xrfdc.MIXER_SCALE_1P0
        }
        for adc_block in self.adc_blocks.ravel():
            adc_block.NyquistZone = nyquist
            adc_block.MixerSettings = mixer_settings_adc
            # Reset NCO phase
            adc_block.ResetNCOPhase()

        # Configure the MTS to use the SYSREF event source
        self.xrfdc.mts_adc_config.SysRef_Enable = True


def resolve_binary_path(bitfile_name):
    """this helper function is necessary to locate
    the bit file during overlay loading"""
    p = Path(__file__).resolve().parent

    if Path(bitfile_name).exists():
        return bitfile_name
    elif Path(p / bitfile_name).exists():
        return str(p / bitfile_name)
    else:
        raise FileNotFoundError(f"Cannot find {bitfile_name}.")
