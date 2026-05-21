from pynq import Overlay, MMIO, PL, DeviceTreeSegment
from mimo_mts.utils.config_clk104 import CLK104Config
from mimo_mts.utils.config_si570 import SI570
from mimo_mts.drivers.evr import EVR
from mimo_mts.drivers.rf_control import RfControl
from mimo_mts.drivers.clocktreeMTS import ClockTreeMTS
from mimo_mts.drivers.frontend_control import FrontendControl
from mimo_mts.config import ol_configs

import xrfdc
import numpy as np
from pathlib import Path
from pprint import pformat
__all__ = ('EVR', 'RfControl', 'ClockTreeMTS', 'FrontendControl')


class MimoMtsOverlay(Overlay):
    """
    The MTS overlay demonstrates the RFSoC multi-tile
    synchronization capability that enables
    multiple RF DAC and ADC tiles to achieve latency alignment.
    """
    def __init__(self, config: str = "MIMO_ZCU208", **kwargs):
        self.ol_info = ol_info = ol_configs[config]
        assert Path(ol_info['bitfile_name']).exists(), f"File {ol_info['bitfile_name']} not found."
        self.board = ol_info['board']

        # Load device-tree overlays before the kernel-modules and drivers get loaded
        if 'device_tree_segments' in ol_info:
            for dtsb_file in ol_info['device_tree_segments']:
                dts = DeviceTreeSegment(str(dtsb_file))
                if dts.is_dtbo_applied():
                    print("Device-tree overlay is already applied:", dtsb_file)
                else:
                    print("Inserting device-tree overlay:", dtsb_file)
                    dts.insert()

        if 'si570_freq_mhz' in ol_info:
            with SI570() as si570:
                si570.set_freq(ol_info['si570_freq_mhz'])

        if 'clk104_tcs' in ol_info:
            self.clk104 = CLK104Config(**ol_info['clk104_tcs'])

        # download overlay after external clocks are configured
        PL.reset()
        super().__init__(str(ol_info['bitfile_name']), **kwargs)

        if "rfdc" in self.ip_dict and "rfdc" in ol_info:
            self.mixer_cfg = ol_info['rfdc']['mixer']
            self.mts_cfg = ol_info['rfdc']['mts']
            self._initialize_dev()
            self._initialize_memories()
            self._initialize_mts()
            self._initialize_mixers()

    def __repr__(self):
        str = f"< {self.__class__.__name__} >:\n"
        str += pformat(self.ol_info, indent=2)
        str += "\n"
        if "rfdc" in self.ip_dict:
            str += self.report_mts_latency()
        return str

    def _initialize_dev(self):
        """Alias xrfdc, rf_control and evr, enumurate rfdc blocks."""
        if 'axil_rf_control_0' in self.ip_dict:
            self.rf_control = self.axil_rf_control_0
        elif 'axil_llrf_0' in self.ip_dict:
            self.rf_control = self.axil_llrf_0

        if 'axil_evr_0' in self.ip_dict:
            self.evr = self.axil_evr_0

        if 'frontend_control_axi_0' in self.ip_dict:
            self.ffe = self.frontend_control_axi_0

        if self.board.converters_per_tile == 2:
            self.dac_blocks = np.array([
                [self.rfdc.dac_tiles[i].blocks[j] for j in [0, 2]]
                for i in range(4)])
            self.adc_blocks = np.array([
                [self.rfdc.adc_tiles[i].blocks[j] for j in [0, 1]]
                for i in range(4)])
        elif self.board.converters_per_tile == 4:
            self.dac_blocks = np.array([
                [self.rfdc.dac_tiles[i].blocks[j] for j in range(4)]
                for i in range(4)])
            self.adc_blocks = np.array([
                [self.rfdc.adc_tiles[i].blocks[j] for j in range(4)]
                for i in range(4)])

    def _initialize_memories(self):
        """ Initialize adc / dac waveform buffers. """
        self.dac_player = self.memdict_to_view(
            "transmitter/hier_dac_play/axi_bram_ctrl_0")
        if 'transmitter/hier_dac_cap/axi_bram_ctrl_0' in self.mem_dict:
            self.dac_capture = self.memdict_to_view(
                "transmitter/hier_dac_cap/axi_bram_ctrl_0")

        self.adc_bufs = []
        for tile in range(self.board.num_adc_tiles):
            for i in range(4):
                self.adc_bufs.append(
                    self.memdict_to_view(
                        f"receiver/m{tile}{i}/axi_bram_ctrl_0"))

    def _initialize_mts(self):
        """
        Initialize the MTS.
        https://docs.amd.com/r/en-US/pg269-rf-data-converter/Main-Sequence-to-Perform-Synchronization-for-AC-or-DC-Coupled-Single-or-Multiple-Device
        """
        # Set tile distributing reference clock
        self.rfdc.mts_adc_init(self.board.adc_ref_index)
        self.rfdc.mts_dac_init(self.board.dac_ref_index)
        self.rfdc.mts_dac()
        self.rfdc.mts_adc()

        self.init_mts_clocks()
        self.sync_mts()
        self.sync_digital_features()
        self.check_mts_latency()

    def _initialize_mixers(self):
        self.set_dac_mixer(
            self.mixer_cfg['dac_mixer_nco_freq_mhz'],
            self.mixer_cfg['dac_mixer_nco_nyquist'],
            self.mixer_cfg['dac_mixer_nco_phase'])
        self.set_adc_mixer(
            self.mixer_cfg['adc_mixer_nco_freq_mhz'],
            self.mixer_cfg['adc_mixer_nco_nyquist'],
            self.mixer_cfg['adc_mixer_nco_phase'])

    def memdict_to_view(self, ip, dtype="int16"):
        """Configures access to internal memory via MMIO"""
        baseAddress = self.mem_dict[ip]["phys_addr"]
        mem_range = self.mem_dict[ip]["addr_range"]
        ipmmio = MMIO(baseAddress, mem_range)
        return ipmmio.array[0:ipmmio.length].view(dtype)

    def init_mts_clocks(self):
        """
        Resets the MTS alignment engine
        Verify the PL and PL_SYSREF clocks are active
        by verifying an MMCM is in the LOCKED state
        """
        self.clocktreeMTS.reset_mmcm()

        # Reset only user selected DAC tiles
        bitvector = self.board.active_dac_tiles
        for n in range(4):
            if bitvector & 0x1:
                self.rfdc.dac_tiles[n].Reset()
            bitvector = bitvector >> 1
        # Reset ADC FIFO of only user selected tiles - restarts MTS engine
        for toggleValue in range(0, 1):
            bitvector = self.board.active_adc_tiles
            for n in range(4):
                if bitvector & 0x1:
                    self.rfdc.adc_tiles[n].SetupFIFOBoth(toggleValue)
                bitvector = bitvector >> 1

        assert self.clocktreeMTS.check_mmcm_locked(), "The MTS ClockTree has failed to LOCK."

    def sync_mts(self):
        """
        Configures RFSoC MTS alignment for deterministic latency, following
        https://github.com/Xilinx/embeddedsw/blob/master/XilinxProcessorIPLib/drivers/rfdc/examples/xrfdc_mts_example.c
        """
        self.rfdc.mts_dac_config.Tiles = self.board.active_dac_tiles
        self.rfdc.mts_dac_config.SysRef_Enable = self.board.num_dac_tiles > 0
        self.rfdc.mts_dac_config.Target_Latency = \
            self.mts_cfg['mts_dac_target_latency']
        self.rfdc.mts_dac()

        self.rfdc.mts_adc_config.Tiles = self.board.active_adc_tiles
        self.rfdc.mts_adc_config.SysRef_Enable = self.board.num_adc_tiles > 0
        self.rfdc.mts_adc_config.Target_Latency = \
            self.mts_cfg['mts_adc_target_latency']
        self.rfdc.mts_adc()

    def sync_digital_features(self):
        """
        Use Case 2: Synchronize Digital Features Using SYSREF
          for Multiple Devices with DC-Coupling
        https://docs.amd.com/r/en-US/pg269-rf-data-converter/Use-Case-2-Synchronize-Digital-Features-Using-SYSREF-for-Multiple-Devices-with-DC-Coupling
        """
        pass

    def check_mts_latency(self):
        for i in range(self.board.num_dac_tiles):
            assert self.rfdc.mts_dac_config.Latency[i] == \
                self.mts_cfg['mts_dac_target_latency'], \
                f"Tile {i} Latency {self.rfdc.mts_dac_config.Latency[i]} != " \
                f"Target Latency {self.mts_cfg['mts_dac_target_latency']}"
        for i in range(self.board.num_adc_tiles):
            assert self.rfdc.mts_adc_config.Latency[i] == \
                self.mts_cfg['mts_adc_target_latency'], \
                f"Tile {i} Latency {self.rfdc.mts_adc_config.Latency[i]} != " \
                f"Target Latency {self.mts_cfg['mts_adc_target_latency']}"

    def report_mts_latency(self):
        """Reports the MTS latency for each tile"""
        str = "< RFDC MTS Latency Report: >\n"
        for i in range(self.board.num_dac_tiles):
            str += (f"DAC Tile {i} Latency: "
                    f"{self.rfdc.mts_dac_config.Latency[i]:3d}, "
                    f"Offset: {self.rfdc.mts_dac_config.Offset[i]}\n")
        for i in range(self.board.num_adc_tiles):
            str += (f"ADC Tile {i} Latency: "
                    f"{self.rfdc.mts_adc_config.Latency[i]:3d}, "
                    f"Offset: {self.rfdc.mts_adc_config.Offset[i]}\n")
        return str

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

    def write_dac_iq_buf(self, i_buffer, q_buffer):
        """Writes DAC samples to all channels
        Follow PG269, DAC I/Q input to Real output (Figure 101/110):
          Dual RF-DAC: Figure 103:
            s00_axis_data: Q7,I7,Q6,I6,Q5,I5,Q4,I4,Q3,I3,Q2,I2,Q1,I1,Q0,I0
            s02_axis_data: Q7,I7,Q6,I6,Q5,I5,Q4,I4,Q3,I3,Q2,I2,Q1,I1,Q0,I0
          Quad RF-DAC: Figure 112:
            s00_axis_data: Q7,I7,Q6,I6,Q5,I5,Q4,I4,Q3,I3,Q2,I2,Q1,I1,Q0,I0
            s01_axis_data: Q7,I7,Q6,I6,Q5,I5,Q4,I4,Q3,I3,Q2,I2,Q1,I1,Q0,I0
            s02_axis_data: Q7,I7,Q6,I6,Q5,I5,Q4,I4,Q3,I3,Q2,I2,Q1,I1,Q0,I0
            s03_axis_data: Q7,I7,Q6,I6,Q5,I5,Q4,I4,Q3,I3,Q2,I2,Q1,I1,Q0,I0
        """
        assert np.issubdtype(i_buffer.dtype, np.int16), \
            "i_buffer dtype of np.int16 required."
        assert np.issubdtype(q_buffer.dtype, np.int16), \
            "q_buffer dtype of np.int16 required."
        assert i_buffer.size == self.dac_player.size // 2, \
            "i_buffer size must be half of the DAC player buffer size."
        assert q_buffer.size == self.dac_player.size // 2, \
            "q_buffer size must be half of the DAC player buffer size."
        self.dac_player[0::2] = i_buffer
        self.dac_player[1::2] = q_buffer

    def capture_dac_iq_buf(ol, i_buffer=None, q_buffer=None):
        length = ol.dac_capture.size // 2
        if i_buffer is None:
            i_buffer = np.empty((length,), dtype=np.int16)
        if q_buffer is None:
            q_buffer = np.empty((length,), dtype=np.int16)
        np.copyto(i_buffer, ol.dac_capture[0::2])
        np.copyto(q_buffer, ol.dac_capture[1::2])
        return i_buffer, q_buffer

    def set_dac_mixer(self, freq_mhz=0, nyquist=1, phase=0):
        self.rfdc.mts_dac_config.SysRef_Enable = 1

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
            dac_block.InterpolationFactor = self.ol_info['rfdc']['dac_interplation_factor']
            dac_block.ResetNCOPhase()

        self.rfdc.mts_dac_config.SysRef_Enable = 0
        # keep track of mixer settings
        self.mixer_cfg['dac_mixer_nco_freq_mhz'] = freq_mhz
        self.mixer_cfg['dac_mixer_nco_nyquist'] = nyquist
        self.mixer_cfg['dac_mixer_nco_phase'] = phase
        print(f"Set DAC mixer: freq={freq_mhz} MHz, nyquist={nyquist}, phase={phase} degrees")

    def set_adc_mixer(self, freq_mhz=0, nyquist=1, phase=0):
        self.rfdc.mts_adc_config.SysRef_Enable = 1

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
            adc_block.ResetNCOPhase()

        self.rfdc.mts_adc_config.SysRef_Enable = 0
        # keep track of mixer settings
        self.mixer_cfg['adc_mixer_nco_freq_mhz'] = freq_mhz
        self.mixer_cfg['adc_mixer_nco_nyquist'] = nyquist
        self.mixer_cfg['adc_mixer_nco_phase'] = phase
        print(f"Set ADC mixer: freq={freq_mhz} MHz, nyquist={nyquist}, phase={phase} degrees")

    def set_dac_mixer_ch(self, ch, freq_mhz=0, nyquist=1, phase=0):
        """Configure a single DAC channel's mixer, all channels should
        have same phase due to rfdc.mts_dac() """
        tile, block = divmod(ch, self.board.converters_per_tile)
        if self.board.converters_per_tile == 2:
            block = [0, 2][block]

        self.rfdc.mts_dac_config.SysRef_Enable = 1

        dac_block = self.rfdc.dac_tiles[tile].blocks[block]
        dac_block.NyquistZone = nyquist
        dac_block.MixerSettings = {
            'Freq': freq_mhz, 'PhaseOffset': phase,
            'EventSource': xrfdc.EVNT_SRC_SYSREF,
            'MixerType': xrfdc.MIXER_TYPE_FINE,
            'CoarseMixFreq': xrfdc.COARSE_MIX_OFF,
            'MixerMode': xrfdc.MIXER_MODE_C2R,
            'FineMixerScale': xrfdc.MIXER_SCALE_1P0
        }
        dac_block.InterpolationFactor = \
            self.ol_info['rfdc']['dac_interplation_factor']
        dac_block.ResetNCOPhase()
        self.rfdc.mts_dac()

        self.rfdc.mts_dac_config.SysRef_Enable = 0
        print(f"DAC ch{ch}: freq={freq_mhz} MHz, "
              f"nyquist={nyquist}, phase={phase} deg")

    def set_adc_mixer_ch(self, ch, freq_mhz=0, nyquist=1, phase=0):
        """Configure a single ADC channel's mixer, all channels should
        have same phase due to rfdc.mts_adc() """
        tile, block = divmod(ch, self.board.converters_per_tile)

        self.rfdc.mts_adc_config.SysRef_Enable = 1

        adc_block = self.rfdc.adc_tiles[tile].blocks[block]
        adc_block.NyquistZone = nyquist
        adc_block.MixerSettings = {
            'Freq': freq_mhz, 'PhaseOffset': phase,
            'EventSource': xrfdc.EVNT_SRC_SYSREF,
            'MixerType': xrfdc.MIXER_TYPE_FINE,
            'CoarseMixFreq': xrfdc.COARSE_MIX_OFF,
            'MixerMode': xrfdc.MIXER_MODE_R2C,
            'FineMixerScale': xrfdc.MIXER_SCALE_1P0
        }
        adc_block.ResetNCOPhase()
        self.rfdc.mts_adc()

        self.rfdc.mts_adc_config.SysRef_Enable = 0
        print(f"ADC ch{ch}: freq={freq_mhz} MHz, "
              f"nyquist={nyquist}, phase={phase} deg")
