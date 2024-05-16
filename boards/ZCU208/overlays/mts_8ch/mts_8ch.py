# -------------------------------------------------------------------------------------------------
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
MTS_START_TILE = 0x01
MAX_DAC_TILES = 4
MAX_ADC_TILES = 4
DAC_REF_TILE = 2
ADC_REF_TILE = 2
DEVICETREE_OVERLAY_FOR_PLDRAM = 'ddr4.dtbo'

RFSOC4X2_LMK_FREQ = 500.0
RFSOC4X2_LMX_FREQ = 500.0
RFSOC4X2_DAC_TILES = 0b0101
RFSOC4X2_ADC_TILES = 0b0101

ZCU208_LMK_FREQ = 500.0
ZCU208_LMX_FREQ = 4000.0
ZCU208_DAC_TILES = 0b1111
ZCU208_ADC_TILES = 0b1111

class mtsOverlay(Overlay):
    """
    The MTS overlay demonstrates the RFSoC multi-tile synchronization capability that enables
    multiple RF DAC and ADC tiles to achieve latency alignment. This capability is key to enabling
    Massive MIMO, phased array RADAR applications and beamforming.
    """
    def __init__(self, bitfile_name='mts.bit', **kwargs):
        """
         This overlay class supports the MTS overlay.  It configures the PL gpio, internal memories,
         PL-DRAM and DMA interfaces.  Additional helper methods are provided to: configure and verify
         MTS, verify the DACRAM and read captured samples from the internal ADC
         memories and the PL-DDR4 memory.  In addition to the bitfile_name, the active ADC and DAC
         tiles must be provided to use in the MTS initialization.
        """
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

        dts = pynq.DeviceTreeSegment(resolve_binary_path(DEVICETREE_OVERLAY_FOR_PLDRAM))
        if not dts.is_dtbo_applied():
            dts.insert()
        # must configure clock synthesizers 
        # the LMK04828 PL_CLK and PL_SYSREF clocks
        if board == 'RFSoC4x2':
            xrfclk.set_ref_clks(lmk_freq = RFSOC4X2_LMK_FREQ, lmx_freq = RFSOC4X2_LMX_FREQ)
            self.ACTIVE_DAC_TILES = RFSOC4X2_DAC_TILES
            self.ACTIVE_ADC_TILES = RFSOC4X2_ADC_TILES
        elif board == 'ZCU208':
            xrfclk.set_ref_clks(lmk_freq = ZCU208_LMK_FREQ, lmx_freq = ZCU208_LMX_FREQ)
            self.ACTIVE_DAC_TILES = ZCU208_DAC_TILES
            self.ACTIVE_ADC_TILES = ZCU208_ADC_TILES
        else:
            assert false, "Board Not Supported"
        time.sleep(0.5)        
        super().__init__(resolve_binary_path(bitfile_name), **kwargs)
        #self.print_ip_dict()
        #self.print_attrs()
        self.xrfdc = self.rfdc
        self.xrfdc.mts_dac_config.RefTile = DAC_REF_TILE  # DAC tile distributing reference clock
        self.xrfdc.mts_adc_config.RefTile = ADC_REF_TILE  # ADC                

        # map PL GPIO registers
        self.dac_enable =  self.gpio_control.axi_gpio_dac.channel1[0]
        self.trig_cap = self.gpio_control.axi_gpio_bram_adc.channel1[0]
        self.fifo_flush = self.gpio_control.axi_gpio_fifoflush.channel1[0]

        # DAC Player Memory - DACs will play this waveform
        self.dac_player = self.memdict_to_view("transmitter/hier_dac_play/axi_bram_ctrl_0")

        # DAC Capture Memory - to verify DAC AWG for diagnostics
        self.dac_capture = self.memdict_to_view("transmitter/hier_dac_cap/axi_bram_ctrl_0")

        # ADC Capture Memories
        self.adc_captures = []
        nchannels = 8
        self.mode_iq = True
        for nchan in range(nchannels):
            s_i = "receiver/chan{}_I/axi_bram_ctrl_0".format(nchan)
            chan_i = self.memdict_to_view(s_i)
            if self.mode_iq:
                s_q = "receiver/chan{}_Q/axi_bram_ctrl_0".format(nchan)
                chan_q = self.memdict_to_view(s_q)
                self.adc_captures.append((chan_i, chan_q))
            else:
                self.adc_captures.append((chan_i,))
        self.nchannels_adc = nchannels
        if self.mode_iq:
            self.nadc_mem_total = 2*self.nchannels_adc
        else:
            self.nadc_mem_total = self.nchannels_adc

        # LEDs
        self._leds = self.leds_gpio.channel1

        # Reset GPIOs and bring to known state
        self.dac_enable.off()
        self.trig_cap.off() 
        self.fifo_flush.off() # active low flush of the DMA fifo

        self.adc_dma = self.deepCapture.axi_dma_adc # PL DMA to DDR4 memory
        self.ADCdeepcapture = self.memdict_to_view("ddr4_0")

    def print_ip_dict(self):
        for dd, name in ((self.ip_dict, "ip_dict"), (self.mem_dict, "mem_dict"), (self.hierarchy_dict, "hierarchy_dict")):
            print(name + ":")
            for key, val in dd.items():
                print("  {}: dict len {}".format(key, len(val)))
    
    def print_attrs(self):
        print("Attrs:")
        for attr in dir(self):
            if not attr.startswith("_"):
                print("  " + attr)
        print(dir(self))

    def set_led(self, state, nled=0):
        nled = min(int(nled), 7)
        val = self._leds.read() & 0xff
        if state:
            val |= (1 << nled)
        else:
            val &= ~(1 << nled)
        self._leds.write(val, mask=0xff)
        return

    def get_led(self, nled=0):
        nled = min(int(nled), 7)
        val = self._leds.read() & 0xff
        return (val >> nled) & 1

    def set_leds(self, bitmap):
        self._leds.write(int(bitmap), mask=0xff)
        return

    def get_leds(self, bitmap):
        return self._leds.read()

    def memdict_to_view(self, ip, dtype='int16'):
        """ Configures access to internal memory via MMIO"""
        baseAddress = self.mem_dict[ip]["phys_addr"]
        mem_range = self.mem_dict[ip]["addr_range"]
        ipmmio = MMIO(baseAddress, mem_range)
        return ipmmio.array[0:ipmmio.length].view(dtype)

    def sync_tiles(self, dacTarget=-1, adcTarget=-1):
        """ Configures RFSoC MTS alignment"""
        # Set which RF tiles use MTS and turn MTS off
        if self.ACTIVE_DAC_TILES > 0:
            self.xrfdc.mts_dac_config.Tiles = self.ACTIVE_DAC_TILES # group defined in binary 0b1111
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

    def init_tile_sync(self):
        """ Resets the MTS alignment engine"""
        self.xrfdc.mts_dac_config.Tiles = 0b0001 # turn only one tile on first
        self.xrfdc.mts_adc_config.Tiles = 0b0001
        self.xrfdc.mts_dac_config.SysRef_Enable = 1
        self.xrfdc.mts_adc_config.SysRef_Enable = 1
        self.xrfdc.mts_dac_config.Target_Latency = -1
        self.xrfdc.mts_adc_config.Target_Latency = -1
        self.xrfdc.mts_dac()
        self.xrfdc.mts_adc()
        # Reset MTS ClockWizard MMCM - refer to PG065
        self.clocktreeMTS.MTSclkwiz.mmio.write_reg(CLOCKWIZARD_RESET_ADDRESS, CLOCKWIZARD_RESET_TOKEN)
        time.sleep(0.1)
        # Reset only user selected DAC tiles
        bitvector = self.ACTIVE_DAC_TILES
        for n in range(MAX_DAC_TILES):
            if (bitvector & 0x1):
                self.xrfdc.dac_tiles[n].Reset()
            bitvector = bitvector >> 1
        # Reset ADC FIFO of only user selected tiles - restarts MTS engine
        for toggleValue in range(0,1):
            bitvector = self.ACTIVE_ADC_TILES
            for n in range(MAX_ADC_TILES):
                if (bitvector & 0x1):
                    self.xrfdc.adc_tiles[n].SetupFIFOBoth(toggleValue)
                bitvector = bitvector >> 1
 
    def verify_clock_tree(self):
        """ Verify the PL and PL_SYSREF clocks are active by verifying an MMCM is in the LOCKED state"""
        Xstatus = self.clocktreeMTS.MTSclkwiz.read(CLOCKWIZARD_LOCK_ADDRESS) # reads the LOCK register
        # the ClockWizard AXILite registers are NOT fully mapped: refer to PG065
        if (Xstatus != 1):
            raise Exception("The MTS ClockTree has failed to LOCK. Please verify board clocking configuration")

    def trigger_capture(self):
        """ Internal loopback of DAC waveform to internal capture mirror"""        
        self.trig_cap.off()
        self.dac_enable.off()
        self.dac_enable.on()
        self.trig_cap.on() # actually triggers adc[A..C] to capture too
        time.sleep(0.5)
        self.trig_cap.off()

    def internal_capture(self, membuffer):
        """ Captures ADC samples from all channels and stores to internal memories """
        if not np.issubdtype(membuffer.dtype, np.int16):
            raise Exception("buffer not defined or np.int16!")
        if not membuffer.shape[0] == self.nadc_mem_total:
            raise Exception("buffer must be of shape({}, N)!".format(self.nadc_mem_total))
        self.trigger_capture()
        for n in range(self.nchannels_adc):
            n_i = 2*n
            n_q = n_i + 1
            membuffer[n_i] = np.copy(self.adc_captures[n][0][0:len(membuffer[n_i])])
            if self.mode_iq:
                membuffer[n_q] = np.copy(self.adc_captures[n][1][0:len(membuffer[n_q])])
        return

    def dram_capture(self, buffer):
        """ Captures ADC samples to the PL-DRAM memory notebook provided buffer """
        if type(buffer) != pynq.buffer.PynqBuffer:
            raise Exception("A PYNQ allocated buffer is required!")

        if not np.issubdtype(buffer.dtype, np.int16):
            raise Exception("buffer not defined or np.int16")
        
        self.dac_enable.on()
        self.adc_dma.register_map.S2MM_DMACR.Reset = 1
        self.adc_dma.recvchannel.stop()
        self.fifo_flush.off() # clear FIFO
        # because TLAST is not used, we must soft-reset the S2MM/recvchannel
        self.adc_dma.register_map.S2MM_DMACR.Reset = 0
        self.adc_dma.recvchannel.start()
        self.adc_dma.recvchannel.transfer(buffer)
        self.fifo_flush.on() # enable FIFO and samples will start flowing

def resolve_binary_path(bitfile_name):
    """ this helper function is necessary to locate the bit file during overlay loading"""
    if os.path.isfile(bitfile_name):
        return bitfile_name
    elif os.path.isfile(os.path.join(MODULE_PATH, bitfile_name)):
        return os.path.join(MODULE_PATH, bitfile_name)
    else:
        raise FileNotFoundError(f'Cannot find {bitfile_name}.')
# -------------------------------------------------------------------------------------------------

