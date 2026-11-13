import atexit
import json
from enum import IntFlag
from pathlib import Path
from time import sleep

import numpy as np
from pynq import DefaultIP
from pynq.registers import RegisterMap


class EV(IntFlag):
    # Meaning of the bits in the value returned by get_event_flags()
    # It indicates which events happened since the last call
    # Instantaneous value (1 = pushed)
    ENC = 1 << 0  # encoder button
    BACK = 1 << 1  # back button
    # On push
    ENC_P = 1 << 4
    BACK_P = 1 << 5
    # Short push and release
    ENC_S = 1 << 8
    BACK_S = 1 << 9
    # Long push
    ENC_L = 1 << 12
    BACK_L = 1 << 13
    # Encoder ticks. Alternative to get_encoder_ticks(). Not implemented here.
    ROT_CCW = 1 << 16
    ROT_CW = 1 << 17


def sign_extend(value, bits):
    sign_bit = 1 << (bits - 1)
    return (value & (sign_bit - 1)) - (value & sign_bit)


class UiBoard(DefaultIP):
    bindto = ["xilinx.com:module_ref:ui_board_hard_axi:1.0"]

    def __init__(self, description, is_legacy=True):
        """PYNQ driver for the ui_board using the ui_board_hard memory-mapped interface
        is_legacy: True for ui_board, False for ui_board_1u
        """
        self.is_legacy = is_legacy

        # Note the LSB is connected to the SSD1322 reset pin on legacy ui_board
        self.mcp_output_state = 1 if is_legacy else 0xFFFF

        root_path = Path(__file__).parent.parent.parent
        json_path = root_path / "designs/ip/rtl/ui_board_hard_axi.json"
        # json_path = "/home/xilinx/pynq_llrf/designs/ip/rtl/ui_board_hard_axi.json"

        with open(json_path) as f:
            self.json_dat = json.load(f)

        description["registers"] = self.json_dat["csr_registers"]
        super().__init__(description)

        # `fb` = uint32 view of the framebuffer region
        # CAREFUL: never print the `fb`. Numpy will try 64 bit access on the AXI-lite bus,
        # which will fail the whole process with an BUS_ERROR exception.
        FB_BASE = self.json_dat["csr_bases"]["ui_ssd1322_framebuffer"] // 4  # offset in [32 bit words]
        self.fb = self.mmio.array[FB_BASE : FB_BASE + 2048]

        # shortcut for the register map (which is used here a lot)
        self.rm: RegisterMap = self.register_map

        self.reset()
        atexit.register(self.clear)

    def clear(self):
        """clear the screen, disable LEDs. Call it on shutdown."""
        self.set_led(0, 0)
        self.fb[:] = 0
        self.rm.ui_send_fb[:] = 1

    def reset(self):
        """reset the chips, clear the screen"""
        self.rm.ui_reset[:] = 1
        sleep(0.01)

        # Disable the LEDs
        self.mcp_output_state = 1 if self.is_legacy else 0xFFFF
        self.rm.ui_outputs[:] = self.mcp_output_state

        # How many buttons do we have?
        self.rm.ui_event_active[:] = 0b01 if self.is_legacy else 0b11
        # Always active low
        self.rm.ui_event_invert[:] = 0b11
        self.rm.ui_enable_interrupt[:] = 1

        # Read encoder once to clear
        self.rm.ui_event_flags[:]

        self.clear()

    def send_fb_image(self, img: bytes):
        """Display the bitmap image on the OLED
        img must be 256 x 64 pixels with 8 bit greyscale (L)
        only the 4 MSBs of each pixel are sent to the display
        """
        img_np = np.frombuffer(img, dtype=np.uint8)
        bytes_np = (img_np[0::2] & 0xF0) | ((img_np[1::2] >> 4) & 0xF)
        self.fb[:] = bytes_np.view("<u4")
        self.rm.ui_send_fb[:] = 1

    def get_encoder_ticks(self):
        """returns hardware encoder count as int16"""
        return sign_extend(self.rm.ui_encoder[:], 16)

    def set_led(self, leda=None, ledb=None):
        """set the RGB-LED color to the 3 LSBs. Value is from 0 - 7.
        Legacy UI_BOARD only supports the 2 LSBs of ledb"""

        # Only supported on ui_board_1u
        if leda is not None and not self.is_legacy:
            # LEDs are active high for the legacy ui_board and active low for ui_board_1u
            leda = ~leda
            self.mcp_output_state &= ~(7 << 8)
            self.mcp_output_state |= (leda & 7) << 8

        # 2 bits on ui_board, 3 bits on ui_board_1u
        if ledb is not None:
            if not self.is_legacy:
                ledb = ~ledb
            self.mcp_output_state &= ~(7 << 4)
            self.mcp_output_state |= (ledb & 7) << 4

        self.rm.ui_outputs[:] = self.mcp_output_state

    def get_event_flags(self):
        """returns the event-flags as defined in EV"""
        return EV(self.rm.ui_event_flags[:])
