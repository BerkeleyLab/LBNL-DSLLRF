from pynq import Overlay, MMIO, PL, DeviceTreeSegment, Interrupt
from mimo_mts.utils.config_clk104 import CLK104Config
from mimo_mts.utils.config_si570 import SI570
from mimo_mts.drivers.evr import EVR
from mimo_mts.drivers.rf_control import RfControl
from mimo_mts.drivers.clocktreeMTS import ClockTreeMTS
from mimo_mts.drivers.frontend_control import FrontendControl
from mimo_mts.drivers.wave_gen import WaveGen
from mimo_mts.config import ol_configs

import xrfdc
import numpy as np
import pandas as pd
from pathlib import Path
from pprint import pformat
__all__ = ('EVR', 'RfControl', 'ClockTreeMTS', 'FrontendControl', 'WaveGen')


class MimoMtsOverlay(Overlay):
    """
    The MTS overlay demonstrates the RFSoC multi-tile
    synchronization capability that enables
    multiple RF DAC and ADC tiles to achieve latency alignment.
    """
    def __init__(self, config: str = "MIMO_ZCU208", **kwargs):
        self.ol_info = ol_info = ol_configs[config].copy()
        self.ol_info.update({k: kwargs[k] for k in self.ol_info if k in kwargs})
        kwargs = {k: kwargs[k] for k in kwargs.keys() - self.ol_info.keys()}
        assert Path(ol_info['bitfile_name']).exists(), f"File {ol_info['bitfile_name']} not found."
        self.board = ol_info['board']

        # Load device-tree segments before the kernel-modules and drivers get loaded
        if 'device_tree_segments' in ol_info:
            for dtsb_file in ol_info['device_tree_segments']:
                dts = DeviceTreeSegment(str(dtsb_file))
                if dts.is_dtbo_applied():
                    print("Found device-tree segment:", dts.sysfs_dir)
                else:
                    print("Inserting device-tree segment:", dts.sysfs_dir)
                    dts.insert()

        if 'si570_freq_mhz' in ol_info:
            with SI570() as si570:
                si570.set_freq(ol_info['si570_freq_mhz'])

        if 'clk104_tcs' in ol_info:
            self.clk104 = CLK104Config(**ol_info['clk104_tcs'])

        # download overlay after external clocks are configured
        PL.reset()
        super().__init__(str(ol_info['bitfile_name']), **kwargs)

        self._initialize_dev()

        if "rfdc" in self.ip_dict and "rfdc" in ol_info:
            self.adc_sampling_rate = ol_info['sampling_rate_hz']['adc']
            self.dac_sampling_rate = ol_info['sampling_rate_hz']['dac']
            assert self.adc_sampling_rate <= self.board.max_adc_sampling_rate, \
                f"ADC sampling rate {self.adc_sampling_rate / 1e9} GHz too high"
            assert self.dac_sampling_rate <= self.board.max_dac_sampling_rate, \
                f"DAC sampling rate {self.dac_sampling_rate / 1e9} GHz too high"
            self._adc_mixer_nco_freq_mhz = ol_info['rfdc']['mixer']['adc_mixer_nco_freq_mhz']
            self._adc_mixer_nco_nyquist = ol_info['rfdc']['mixer']['adc_mixer_nco_nyquist']
            self._adc_mixer_nco_phase = ol_info['rfdc']['mixer']['adc_mixer_nco_phase']
            self._dac_mixer_nco_freq_mhz = ol_info['rfdc']['mixer']['dac_mixer_nco_freq_mhz']
            self._dac_mixer_nco_nyquist = ol_info['rfdc']['mixer']['dac_mixer_nco_nyquist']
            self._dac_mixer_nco_phase = ol_info['rfdc']['mixer']['dac_mixer_nco_phase']
            self.mts_cfg = ol_info['rfdc']['mts']
            self.adc_mixer_mode = self.ol_info['rfdc']['mixer']['adc_mixer_mode']
            self.dac_mixer_mode = self.ol_info['rfdc']['mixer']['dac_mixer_mode']
            assert self.adc_mixer_mode in (xrfdc.MIXER_MODE_R2C, xrfdc.MIXER_MODE_C2C), \
                f"Unsupported ADC mixer mode: {self.adc_mixer_mode}"
            assert self.dac_mixer_mode in (xrfdc.MIXER_MODE_C2R, xrfdc.MIXER_MODE_C2C), \
                f"Unsupported DAC mixer mode: {self.dac_mixer_mode}"
            self._initialize_rfdc_dev()
            self._initialize_memories()
            self._initialize_mts()
            self._initialize_mixers()

    def __repr__(self):
        description = f"< {self.__class__.__name__} >:\n"
        description += pformat(self.ol_info, indent=2)
        description += "\n"
        if "rfdc" in self.ip_dict:
            description += self.report_mts_latency()
            description += self.report_mixers()
        if hasattr(self, 'write_done_irq'):
            description += f"< Interrupt:>\n   write_done_irq at {self.write_done_irq.number}\n"
        return description

    @property
    def dac_mixer_nco_freq_mhz(self):
        return self._dac_mixer_nco_freq_mhz

    @dac_mixer_nco_freq_mhz.setter
    def dac_mixer_nco_freq_mhz(self, val):
        self.set_dac_mixer(freq_mhz=val, nyquist=self.dac_mixer_nco_nyquist, phase=self.dac_mixer_nco_phase)

    @property
    def dac_mixer_nco_nyquist(self):
        return self._dac_mixer_nco_nyquist

    @dac_mixer_nco_nyquist.setter
    def dac_mixer_nco_nyquist(self, val):
        self.set_dac_mixer(freq_mhz=self.dac_mixer_nco_freq_mhz, nyquist=val, phase=self.dac_mixer_nco_phase)

    @property
    def dac_mixer_nco_phase(self):
        return self._dac_mixer_nco_phase

    @dac_mixer_nco_phase.setter
    def dac_mixer_nco_phase(self, val):
        self.set_dac_mixer(freq_mhz=self.dac_mixer_nco_freq_mhz, nyquist=self.dac_mixer_nco_nyquist, phase=val)

    @property
    def adc_mixer_nco_freq_mhz(self):
        return self._adc_mixer_nco_freq_mhz

    @adc_mixer_nco_freq_mhz.setter
    def adc_mixer_nco_freq_mhz(self, val):
        self.set_adc_mixer(freq_mhz=val, nyquist=self.adc_mixer_nco_nyquist, phase=self.adc_mixer_nco_phase)

    @property
    def adc_mixer_nco_nyquist(self):
        return self._adc_mixer_nco_nyquist

    @adc_mixer_nco_nyquist.setter
    def adc_mixer_nco_nyquist(self, val):
        self.set_adc_mixer(freq_mhz=self.adc_mixer_nco_freq_mhz, nyquist=val, phase=self.adc_mixer_nco_phase)

    @property
    def adc_mixer_nco_phase(self):
        return self._adc_mixer_nco_phase

    @adc_mixer_nco_phase.setter
    def adc_mixer_nco_phase(self, val):
        self.set_adc_mixer(freq_mhz=self.adc_mixer_nco_freq_mhz, nyquist=self.adc_mixer_nco_nyquist, phase=val)

    @property
    def mixer_cfg(self):
        return {
            'adc_mixer_nco_freq_mhz': self.adc_mixer_nco_freq_mhz,
            'adc_mixer_nco_nyquist': self.adc_mixer_nco_nyquist,
            'adc_mixer_nco_phase': self.adc_mixer_nco_phase,
            'dac_mixer_nco_freq_mhz': self.dac_mixer_nco_freq_mhz,
            'dac_mixer_nco_nyquist': self.dac_mixer_nco_nyquist,
            'dac_mixer_nco_phase': self.dac_mixer_nco_phase,
        }

    def _initialize_dev(self):
        """Alias xrfdc, rf_control and evr, enumurate rfdc blocks."""
        if 'axil_rf_control_0' in self.ip_dict:
            self.rf_control = self.axil_rf_control_0
        elif 'hier_llrf/axil_rf_control_0' in self.ip_dict:
            self.rf_control = self.hier_llrf.axil_rf_control_0
        elif 'axil_llrf_0' in self.ip_dict:
            self.rf_control = self.axil_llrf_0

        if 'axil_evr_0' in self.ip_dict:
            self.evr = self.axil_evr_0

        if 'frontend_control_axi_0' in self.ip_dict:
            self.ffe = self.frontend_control_axi_0

        if 'transmitter/hier_dac_play/axil_wave_gen_0' in self.ip_dict:
            self.wave_gen = self.transmitter.hier_dac_play.axil_wave_gen_0

        for path in self.interrupt_pins.keys():
            if path.endswith('xpm_cdc_irq/dest_pulse') \
                    or path.endswith('write_done'):
                self.write_done_irq = Interrupt(path)
                print(f"Interrupt {path} created with number {self.write_done_irq.number}")

    def _initialize_rfdc_dev(self):
        if self.board.converters_per_tile == 2:
            # See PG269 Dual RF-ADC Configuration Options, Figure 52-57
            active_adc_blocks = {
                xrfdc.MIXER_MODE_R2C: [0, 1],
                xrfdc.MIXER_MODE_C2C: [0]
            }
            # See PG269 Dual RF-DAC Configuration Options, Figure 101-106
            active_dac_blocks = {
                xrfdc.MIXER_MODE_C2R: [0, 2],
                xrfdc.MIXER_MODE_C2C: [0]
            }
        elif self.board.converters_per_tile == 4:
            # See PG269 Quad RF-ADC Configuration Options, Figure 61-66
            active_adc_blocks = {
                xrfdc.MIXER_MODE_R2C: [0, 1, 2, 3],
                xrfdc.MIXER_MODE_C2C: [0, 2]
            }
            # See PG269 Quad RF-DAC Configuration Options, Figure 110-115
            active_dac_blocks = {
                xrfdc.MIXER_MODE_C2R: [0, 1, 2, 3],
                xrfdc.MIXER_MODE_C2C: [0, 2]
            }

        self.dac_blocks = np.array([
            [self.rfdc.dac_tiles[i].blocks[j] for j in active_dac_blocks[self.dac_mixer_mode]]
            for i in range(4)])
        self.adc_blocks = np.array([
            [self.rfdc.adc_tiles[i].blocks[j] for j in active_adc_blocks[self.adc_mixer_mode]]
            for i in range(4)])

    def _initialize_memories(self):
        """Initialize ADC/DAC waveform buffers."""
        self.dac_player = None
        self.dac_capture = None

        # DAC player is broadcasted to all DAC tiles, so only one buffer is needed
        if 'transmitter/hier_dac_play/axi_bram_ctrl_0' in self.mem_dict:
            self.dac_player = self._memdict_to_view(
                "transmitter/hier_dac_play/axi_bram_ctrl_0")
        elif hasattr(self, 'wave_gen'):
            self.dac_player = self.wave_gen.wave_mem

        if 'transmitter/hier_dac_cap/axi_bram_ctrl_0' in self.mem_dict:
            self.dac_capture = self._memdict_to_view(
                "transmitter/hier_dac_cap/axi_bram_ctrl_0")

        adc_streams = {
            xrfdc.MIXER_MODE_R2C: [0, 1, 2, 3],
            xrfdc.MIXER_MODE_C2C: [0, 1]
        }

        self.adc_bufs = []
        for tile in range(self.board.num_adc_tiles):
            for i in adc_streams[self.adc_mixer_mode]:
                self.adc_bufs.append(
                    self._memdict_to_view(
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
            self.dac_mixer_nco_freq_mhz,
            self.dac_mixer_nco_nyquist,
            self.dac_mixer_nco_phase)
        self.set_adc_mixer(
            self.adc_mixer_nco_freq_mhz,
            self.adc_mixer_nco_nyquist,
            self.adc_mixer_nco_phase)

    def _memdict_to_view(self, ip, dtype="int16"):
        """Configures access to internal memory via MMIO."""
        try:
            info = self.mem_dict[ip]
        except KeyError as exc:
            raise KeyError(f"Memory IP '{ip}' not found in overlay mem_dict.") from exc

        base_address = info["phys_addr"]
        addr_range = info["addr_range"]
        ipmmio = MMIO(base_address, addr_range)
        return ipmmio.array[:ipmmio.length].view(dtype)

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
        str = "< RFDC MTS Latency: >\n"
        for i in range(self.board.num_dac_tiles):
            str += (f"  DAC Tile {i} Latency: "
                    f"{self.rfdc.mts_dac_config.Latency[i]:3d}, "
                    f"Offset: {self.rfdc.mts_dac_config.Offset[i]}\n")
        for i in range(self.board.num_adc_tiles):
            str += (f"  ADC Tile {i} Latency: "
                    f"{self.rfdc.mts_adc_config.Latency[i]:3d}, "
                    f"Offset: {self.rfdc.mts_adc_config.Offset[i]}\n")
        return str

    def report_mixers(self):
        """Reports the mixer settings"""
        str = "< RFDC Mixer: >\n"
        str += (f"  DAC mixer: freq={self.dac_mixer_nco_freq_mhz} MHz, "
                f"nyquist={self.dac_mixer_nco_nyquist}, "
                f"phase={self.dac_mixer_nco_phase} deg\n")
        str += (f"  ADC mixer: freq={self.adc_mixer_nco_freq_mhz} MHz, "
                f"nyquist={self.adc_mixer_nco_nyquist}, "
                f"phase={self.adc_mixer_nco_phase} deg\n")
        return str

    def capture_adc_iq_buf(self, i_buffer=None, q_buffer=None):
        """Captures ADC samples from all channels
        Follow PG269:
          Dual RF-ADC Real Input to I/Q Output, Figure 52-54:
            m00_axis_data -> ADC0: I7, I6, I5, I4, I3, I2, I1, I0
            m01_axis_data -> ADC0: Q7, Q6, Q5, Q4, Q3, Q2, Q1, Q0
            m02_axis_data -> ADC1: I7, I6, I5, I4, I3, I2, I1, I0
            m03_axis_data -> ADC1: Q7, Q6, Q5, Q4, Q3, Q2, Q1, Q0
          Dual RF-ADC I/Q Input to I/Q Output Figure 55-57:
            m00_axis_data -> ADC0/1: I7, I6, I5, I4, I3, I2, I1, I0
            m01_axis_data -> ADC0/1: Q7, Q6, Q5, Q4, Q3, Q2, Q1, Q0
          Quad RF-ADC Real Input to I/Q Output, Figure 61-63:
            adc_iq_interleave = True
            m00_axis_data -> ADC0: Q3, I3, Q2, I2, Q1, I1, Q0, I0
            m01_axis_data -> ADC1: Q3, I3, Q2, I2, Q1, I1, Q0, I0
            m02_axis_data -> ADC2: Q3, I3, Q2, I2, Q1, I1, Q0, I0
            m03_axis_data -> ADC3: Q3, I3, Q2, I2, Q1, I1, Q0, I0
          Quad RF-ADC I/Q Input to I/Q Output, Figure 64-66:
            XXX: Figure 66 conflicts with Figure 64!
            XXX: should be: adc_iq_interleave = True
            m00_axis_data -> ADC0/1: Q3, I3, Q2, I2, Q1, I1, Q0, I0
            m02_axis_data -> ADC2/3: Q3, I3, Q2, I2, Q1, I1, Q0, I0
        """
        length = len(self.adc_bufs[0])
        if self.board.adc_iq_interleave:
            length //= 2  # interleave I/Q samples
        if self.adc_mixer_mode == xrfdc.MIXER_MODE_C2C:
            n_signals = self.board.n_adcs // 2
        else:
            n_signals = self.board.n_adcs
        if i_buffer is None:
            i_buffer = np.empty((n_signals, length), dtype=np.int16)
        if q_buffer is None:
            q_buffer = np.empty((n_signals, length), dtype=np.int16)

        assert np.issubdtype(i_buffer.dtype, np.int16), \
            "i_buffer dtype of np.int16 required."
        assert np.issubdtype(q_buffer.dtype, np.int16), \
            "q_buffer dtype of np.int16 required."

        for i in range(n_signals):
            if self.board.adc_iq_interleave:
                np.copyto(i_buffer[i], self.adc_bufs[i][0::2])
                np.copyto(q_buffer[i], self.adc_bufs[i][1::2])
            else:
                np.copyto(i_buffer[i], self.adc_bufs[2*i])
                np.copyto(q_buffer[i], self.adc_bufs[2*i+1])
        return i_buffer, q_buffer

    def capture_adc_iq_df(self):
        fs_ghz = self.adc_sampling_rate / 1e9
        adc_cap_i, adc_cap_q = self.capture_adc_iq_buf()
        n_ch, n_samples = adc_cap_i.shape
        adc_data = {
            'Time [ns]': np.arange(n_samples) / fs_ghz
        }
        for ch in range(n_ch):
            adc_data[f'adc{ch}_i'] = adc_cap_i[ch]
            adc_data[f'adc{ch}_q'] = adc_cap_q[ch]
        df = pd.DataFrame(data=adc_data)
        df.set_index('Time [ns]', inplace=True)
        return df

    def write_dac_iq_buf(self, i_buffer, q_buffer):
        """Writes DAC samples to all channels
        TBD: currently only supports s00_axis_tdata which is broadcasted to all.
        Follow PG269:
          Dual RF-DAC I/Q Input to Real Output, Figure 101-103:
            s00_axis_data -> DAC0: Q7,I7,Q6,I6,...,Q0,I0
            s02_axis_data -> DAC1: Q7,I7,Q6,I6,...,Q0,I0
          Dual RF-DAC I/Q Input to I/Q Output, Figure 104-106:
            s00_axis_data -> DAC0/1: Q7,I7,Q6,I6,...,Q0,I0
          Quad RF-DAC I/Q Input to Real Output, Figure 110-112:
            s00_axis_data -> DAC0: Q7,I7,Q6,I6,...,Q0,I0
            s01_axis_data -> DAC1: Q7,I7,Q6,I6,...,Q0,I0
            s02_axis_data -> DAC2: Q7,I7,Q6,I6,...,Q0,I0
            s03_axis_data -> DAC3: Q7,I7,Q6,I6,...,Q0,I0
          Quad RF-DAC I/Q Input to I/Q Output, Figure 113-115:
            s00_axis_data -> DAC0/1: Q7,I7,Q6,I6,...,Q0,I0
            s02_axis_data -> DAC2/3: Q7,I7,Q6,I6,...,Q0,I0
        """
        assert i_buffer.size == self.dac_player.size // 2, \
            "i_buffer size must be half of the DAC player buffer size."
        assert q_buffer.size == self.dac_player.size // 2, \
            "q_buffer size must be half of the DAC player buffer size."
        self.dac_player[0::2] = i_buffer.astype(np.int16)
        self.dac_player[1::2] = q_buffer.astype(np.int16)

        if hasattr(self, 'wave_gen'):
            self.wave_gen.flush()

    def write_dac_complex(self, c_buffer):
        """Writes complex DAC samples to all channels"""
        self.write_dac_iq_buf(c_buffer.real, c_buffer.imag)

    def capture_dac_iq_buf(self, i_buffer=None, q_buffer=None):
        length = self.dac_capture.size // 2
        if i_buffer is None:
            i_buffer = np.empty((length,), dtype=np.int16)
        if q_buffer is None:
            q_buffer = np.empty((length,), dtype=np.int16)
        np.copyto(i_buffer, self.dac_capture[0::2])
        np.copyto(q_buffer, self.dac_capture[1::2])
        return i_buffer, q_buffer

    def capture_dac_iq_df(self):
        fs_ghz = self.dac_sampling_rate / 1e9
        dac_cap_i, dac_cap_q = self.capture_dac_iq_buf()
        dac_data = {
            'dac_i': dac_cap_i,
            'dac_q': dac_cap_q,
            'Time [ns]': np.arange(len(dac_cap_i)) / fs_ghz * 2
        }
        df = pd.DataFrame(data=dac_data)
        df.set_index('Time [ns]', inplace=True)
        return df

    def set_dac_mixer(self, freq_mhz=0, nyquist=1, phase=0):
        self.rfdc.mts_dac_config.SysRef_Enable = 1

        # Set up mixer settings for each DAC tile
        mixer_settings_dac = {
            'Freq': freq_mhz,
            'PhaseOffset': phase,
            'EventSource': xrfdc.EVNT_SRC_SYSREF,
            'MixerType': xrfdc.MIXER_TYPE_FINE,
            'CoarseMixFreq': xrfdc.COARSE_MIX_OFF,
            'MixerMode': self.dac_mixer_mode,
            'FineMixerScale': xrfdc.MIXER_SCALE_1P0
        }
        for dac_block in self.dac_blocks.ravel():
            dac_block.NyquistZone = nyquist
            dac_block.MixerSettings = mixer_settings_dac
            dac_block.InterpolationFactor = self.ol_info['rfdc']['dac_interpolation_factor']
            dac_block.ResetNCOPhase()

        self.rfdc.mts_dac_config.SysRef_Enable = 0
        # keep track of mixer settings
        self._dac_mixer_nco_freq_mhz = freq_mhz
        self._dac_mixer_nco_nyquist = nyquist
        self._dac_mixer_nco_phase = phase

    def set_adc_mixer(self, freq_mhz=0, nyquist=1, phase=0):
        self.rfdc.mts_adc_config.SysRef_Enable = 1

        # Set up mixer settings for each ADC tile
        mixer_settings_adc = {
            'Freq': freq_mhz,
            'PhaseOffset': phase,
            'EventSource': xrfdc.EVNT_SRC_SYSREF,
            'MixerType': xrfdc.MIXER_TYPE_FINE,
            'CoarseMixFreq': xrfdc.COARSE_MIX_OFF,
            'MixerMode': self.adc_mixer_mode,
            'FineMixerScale': xrfdc.MIXER_SCALE_1P0
        }
        for adc_block in self.adc_blocks.ravel():
            adc_block.NyquistZone = nyquist
            adc_block.MixerSettings = mixer_settings_adc
            adc_block.ResetNCOPhase()

        self.rfdc.mts_adc_config.SysRef_Enable = 0
        # keep track of mixer settings
        self._adc_mixer_nco_freq_mhz = freq_mhz
        self._adc_mixer_nco_nyquist = nyquist
        self._adc_mixer_nco_phase = phase

    def set_dac_mixer_ch(self, ch, freq_mhz=0, nyquist=1, phase=0):
        """ Configure a single DAC channel's mixer """
        tile, block = divmod(ch, self.board.converters_per_tile)
        if self.board.converters_per_tile == 2:
            block = [0, 2][block]

        self.rfdc.mts_dac_config.SysRef_Enable = 1

        dac_block = self.rfdc.dac_tiles[tile].blocks[block]
        dac_block.NyquistZone = nyquist
        dac_block.MixerSettings = {
            'Freq': freq_mhz,
            'PhaseOffset': phase,
            'EventSource': xrfdc.EVNT_SRC_SYSREF,
            'MixerType': xrfdc.MIXER_TYPE_FINE,
            'CoarseMixFreq': xrfdc.COARSE_MIX_OFF,
            'MixerMode': self.dac_mixer_mode,
            'FineMixerScale': xrfdc.MIXER_SCALE_1P0
        }
        dac_block.InterpolationFactor = \
            self.ol_info['rfdc']['dac_interpolation_factor']
        dac_block.ResetNCOPhase()

        self.rfdc.mts_dac_config.SysRef_Enable = 0

    def set_adc_mixer_ch(self, ch, freq_mhz=0, nyquist=1, phase=0):
        """ Configure a single ADC channel's mixer """
        tile, block = divmod(ch, self.board.converters_per_tile)

        self.rfdc.mts_adc_config.SysRef_Enable = 1

        adc_block = self.rfdc.adc_tiles[tile].blocks[block]
        adc_block.NyquistZone = nyquist
        adc_block.MixerSettings = {
            'Freq': freq_mhz,
            'PhaseOffset': phase,
            'EventSource': xrfdc.EVNT_SRC_SYSREF,
            'MixerType': xrfdc.MIXER_TYPE_FINE,
            'CoarseMixFreq': xrfdc.COARSE_MIX_OFF,
            'MixerMode': self.adc_mixer_mode,
            'FineMixerScale': xrfdc.MIXER_SCALE_1P0
        }
        adc_block.ResetNCOPhase()

        self.rfdc.mts_adc_config.SysRef_Enable = 0
