# -------------------------------------------------------------------------------------------------
# Copyright (C) 2023 Advanced Micro Devices, Inc
# SPDX-License-Identifier: MIT
# based on mts.py
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

RFSOC4X2_LMK_FREQ = 500.0
RFSOC4X2_LMX_FREQ = 500.0
RFSOC4X2_DAC_TILES = 0b0101
RFSOC4X2_ADC_TILES = 0b0101

ZCU208_LMK_FREQ = 500.0
ZCU208_LMX_FREQ = 4000.0
ZCU208_DAC_TILES = 0b0011
ZCU208_ADC_TILES = 0b0011

class dcOverlay(Overlay):
    def __init__(self, bitfile_name='mts.bit', **kwargs):
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

        # map PL GPIO registers
        self.dac_enable =  self.gpio_control.axi_gpio_dac.channel1[0]       
        self.trig_cap = self.gpio_control.axi_gpio_bram_adc.channel1[0]
        self.fifo_flush = self.gpio_control.axi_gpio_fifoflush.channel1[0]

        # DAC Player Memory - DACs will play this waveform
        self.dac_player = self.memdict_to_view("hier_dac_play/axi_bram_ctrl_0")

        # DAC Capture Memory - to verify DAC AWG for diagnostics
        self.dac_capture = self.memdict_to_view("hier_dac_cap/axi_bram_ctrl_0")

        # Reset GPIOs and bring to known state
        self.dac_enable.off()
        self.trig_cap.off() 
        self.fifo_flush.off() # active low flush of the DMA fifo

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
        self.dac_enable.off()
        self.dac_enable.on()
        self.trig_cap.on() # actually triggers adc[A..C] to capture too
        time.sleep(0.5)
        self.trig_cap.off()

def resolve_binary_path(bitfile_name):
    """ this helper function is necessary to locate the bit file during overlay loading"""
    if os.path.isfile(bitfile_name):
        return bitfile_name
    elif os.path.isfile(os.path.join(MODULE_PATH, bitfile_name)):
        return os.path.join(MODULE_PATH, bitfile_name)
    else:
        raise FileNotFoundError(f'Cannot find {bitfile_name}.')
# -------------------------------------------------------------------------------------------------

