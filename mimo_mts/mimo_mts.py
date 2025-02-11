import pynq
from pynq import Overlay, MMIO
from .drivers import GTY_EVR
import xrfclk
import xrfdc
import numpy as np
import time
from pathlib import Path
import subprocess
__all__ = ('GTY_EVR',)
MAX_DAC_TILES = 4
MAX_ADC_TILES = 4


class MimoMtsOverlay(Overlay):
    """
    The MTS overlay demonstrates the RFSoC multi-tile
    synchronization capability that enables
    multiple RF DAC and ADC tiles to achieve latency alignment.
    This capability is key to enabling
    Massive MIMO, phased array RADAR applications and beamforming.
    """
    def __init__(self, bitfile_name: str = "mts_8ch.bit",
                 lmk_freq: float = 500.0,
                 lmx_freq: float = 4000.0,
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
        self._restart_zocl()
        self._apply_device_tree_overlay()
        self.ACTIVE_DAC_TILES = kwargs.get("ACTIVE_DAC_TILES", 0b1111)
        self.ACTIVE_ADC_TILES = kwargs.get("ACTIVE_ADC_TILES", 0b1111)
        self.n_adcs = self.ACTIVE_ADC_TILES.bit_count() * 2
        self.n_dacs = self.ACTIVE_DAC_TILES.bit_count() * 2
        self._configure_clocks(lmk_freq, lmx_freq)

        super().__init__(resolve_binary_path(bitfile_name), **kwargs)
        """ Check if RFDC IP core is used in the design"""
        if "rfdc" in self.ip_dict:
            self._initialize_dev()
            self._initialize_memories()
            self._initialize_dma()
            self._initialize_rf_data()
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
                "Could not restart zocl. It did not restart as expected"
            )
        else:
            modprobe_output = subprocess.run(["modprobe", "zocl"])
            assert modprobe_output.returncode == 0, "Could not restart ZOCL!"

    def _apply_device_tree_overlay(self):
        """Apply the device tree overlay for PL-DRAM."""
        dts = pynq.DeviceTreeSegment(resolve_binary_path("ddr4.dtbo"))
        if not dts.is_dtbo_applied():
            dts.insert()

    def _configure_clocks(self, lmk_freq: float, lmx_freq: float):
        """Configure the clk104 registers."""
        xrfclk.set_ref_clks(lmk_freq=lmk_freq, lmx_freq=lmx_freq)

    def _initialize_dev(self):
        """Initialize XRFDC and GPIO registers."""
        self.xrfdc = self.rfdc
        self.dac_blocks = np.array([
            [self.xrfdc.dac_tiles[i].blocks[j] for j in [0, 2]]
            for i in range(MAX_DAC_TILES)])
        self.adc_blocks = np.array([
            [self.xrfdc.adc_tiles[i].blocks[j] for j in [0, 1]]
            for i in range(MAX_ADC_TILES)])
        # Set tile distributing reference clock
        self.xrfdc.mts_adc_config.RefTile = 0  # XXX should be Tile 225
        self.xrfdc.mts_dac_config.RefTile = 0  # XXX should be Tile 230
        self.dac_enable = self.gpio_control.axi_gpio_dac.channel1[0]
        self.trig_cap = self.gpio_control.axi_gpio_bram_adc.channel1[0]
        self.fifo_flush = self.gpio_control.axi_gpio_fifoflush.channel1[0]

    def _initialize_memories(self):
        """Initialize adc / dac waveform buffers."""
        self.dac_player = self.memdict_to_view(
            "transmitter/hier_dac_play/axi_bram_ctrl_0")
        self.dac_capture = self.memdict_to_view(
            "transmitter/hier_dac_cap/axi_bram_ctrl_0")
        self.adc_i_bufs = [
            self.memdict_to_view(f"receiver/chan{ix}_I/axi_bram_ctrl_0")
            for ix in range(self.n_adcs)]
        self.adc_q_bufs = [
            self.memdict_to_view(f"receiver/chan{ix}_Q/axi_bram_ctrl_0")
            for ix in range(self.n_adcs)]

    def _initialize_dma(self):
        """Initialize DMA for ADC deep capture."""
        self.adc_dma = self.deepCapture.axi_dma_adc  # PL DMA to DDR4 memory
        self.ADCdeepcapture = self.memdict_to_view("ddr4_0")

    def _initialize_rf_data(self):
        # Reset GPIOs and bring to known state
        self.dac_enable.on()
        self.trig_cap.off()
        self.fifo_flush.off()  # active low flush of the DMA fifo

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

    def sync_tiles(self, dacTarget=-1, adcTarget=-1):
        """Configures RFSoC MTS alignment"""
        # Set which RF tiles use MTS and turn MTS off
        if self.ACTIVE_DAC_TILES > 0:
            self.xrfdc.mts_dac_config.Tiles = self.ACTIVE_DAC_TILES
            self.xrfdc.mts_dac_config.SysRef_Enable = 1
            self.xrfdc.mts_dac_config.Target_Latency = dacTarget
            # deterministic latency adjustment
            # reference:
            # https://adaptivesupport.amd.com/s/article/1071111?language=en_US
            for n in range(MAX_DAC_TILES):
                if self.xrfdc.mts_dac_config.Latency[n] > dacTarget:
                    dacTarget = self.xrfdc.mts_dac_config.Latency[n]
            # add a margin of suggested 16
            self.xrfdc.mts_dac_config.Target_Latency = dacTarget + 16
            self.xrfdc.mts_dac()
        else:
            self.xrfdc.mts_dac_config.Tiles = 0x0
            self.xrfdc.mts_dac_config.SysRef_Enable = 0
        if self.ACTIVE_ADC_TILES > 0:
            self.xrfdc.mts_adc_config.Tiles = self.ACTIVE_ADC_TILES
            self.xrfdc.mts_adc_config.SysRef_Enable = 1
            self.xrfdc.mts_adc_config.Target_Latency = adcTarget
            for n in range(MAX_ADC_TILES):
                if self.xrfdc.mts_adc_config.Latency[n] > adcTarget:
                    adcTarget = self.xrfdc.mts_adc_config.Latency[n]
            # 8 is the number of sample clocks
            # number of FIFO read-words X the decimation factor
            self.xrfdc.mts_adc_config.Target_Latency = adcTarget + 8
            self.xrfdc.mts_adc()
        else:
            self.xrfdc.mts_adc_config.Tiles = 0x0
            self.xrfdc.mts_adc_config.SysRef_Enable = 0

    def init_tile_sync(self):
        """Resets the MTS alignment engine"""
        self.xrfdc.mts_dac_config.Tiles = 0b0001  # turn only one tile on first
        self.xrfdc.mts_adc_config.Tiles = 0b0001
        self.xrfdc.mts_dac_config.SysRef_Enable = 1
        self.xrfdc.mts_adc_config.SysRef_Enable = 1
        self.xrfdc.mts_dac_config.Target_Latency = -1
        self.xrfdc.mts_adc_config.Target_Latency = -1
        self.xrfdc.mts_dac()
        self.xrfdc.mts_adc()
        # Reset MTS ClockWizard MMCM - refer to PG065
        self.clocktreeMTS.MTSclkwiz.mmio.write_reg(0, 0xA)
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

    def verify_clock_tree(self):
        """Verify the PL and PL_SYSREF clocks are active
        by verifying an MMCM is in the LOCKED state"""
        # reads the LOCK register
        status = self.clocktreeMTS.MTSclkwiz.read(0x0004)
        # the ClockWizard AXILite registers are NOT fully mapped:
        # refer to PG065
        assert status == 1, "The MTS ClockTree has failed to LOCK."

    def trigger_capture(self):
        """Internal loopback of DAC waveform to internal capture mirror"""
        self.trig_cap.on()  # actually triggers all dac and adc channels
        self.trig_cap.off()

    def capture_adc_iq_buf(self, i_buffer=None, q_buffer=None):
        """Captures ADC samples from all channels """
        if i_buffer is None:
            i_buffer = np.empty((self.n_adcs, len(self.adc_i_bufs[0])))
        if q_buffer is None:
            q_buffer = np.empty((self.n_adcs, len(self.adc_q_bufs[0])))

        assert np.issubdtype(i_buffer.dtype, np.int16), \
            "i_buffer dtype of np.int16 required."
        assert np.issubdtype(q_buffer.dtype, np.int16), \
            "q_buffer dtype of np.int16 required."

        self.trigger_capture()
        for i in range(self.n_adcs):
            np.copyto(i_buffer[i], self.adc_i_bufs[i])
            np.copyto(q_buffer[i], self.adc_q_bufs[i])
        return i_buffer, q_buffer

    def dram_capture(self, buffer):
        """Captures ADC samples to the
        PL-DRAM memory notebook provided buffer"""
        assert isinstance(buffer, pynq.buffer.PynqBuffer), \
            "A PYNQ allocated buffer is required!"

        if not np.issubdtype(buffer.dtype, np.int16):
            raise Exception("buffer not defined or np.int16")

        self.dac_enable.on()
        self.adc_dma.register_map.S2MM_DMACR.Reset = 1
        self.adc_dma.recvchannel.stop()
        self.fifo_flush.off()  # clear FIFO
        # because TLAST is not used, we must soft-reset the S2MM/recvchannel
        self.adc_dma.register_map.S2MM_DMACR.Reset = 0
        self.adc_dma.recvchannel.start()
        self.adc_dma.recvchannel.transfer(buffer)
        self.fifo_flush.on()  # enable FIFO and samples will start flowing

    def set_dac_mixer_dco(self, freq_mhz=0, nyquist=1, phase=0):
        # Set up the MTS for DAC tiles
        self.xrfdc.mts_dac()

        # Set up the mixer settings for DAC tiles
        self.xrfdc.mts_dac_config.SysRef_Enable = False
        self.xrfdc.mts_dac_config.Tiles = self.ACTIVE_DAC_TILES

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
        # Set up the MTS for ADC tiles
        self.xrfdc.mts_adc()

        # Set up the mixer settings for ADC tiles
        self.xrfdc.mts_adc_config.SysRef_Enable = False
        self.xrfdc.mts_adc_config.Tiles = self.ACTIVE_ADC_TILES

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
