from enum import IntEnum
from pynq import DefaultIP, Register
from pathlib import Path
import json
import time


def sign_extend(value, bits):
    sign_bit = 1 << (bits - 1)
    return (value & (sign_bit - 1)) - (value & sign_bit)


class Mcp23:
    OPCODE_W = 0x40
    OPCODE_R = 0x41
    B_SEQOP = 1 << 5

    class R(IntEnum):
        # Registers of MCP23S08 IO expander
        IODIR = 0  # GPIO directions, 1 = input, 0 = output
        IPOL = 1
        GPINTEN = 2
        DEFVAL = 3
        INTCON = 4
        IOCON = 5  # Configuration
        GPPU = 6  # Pull-up enable (for inputs only)
        INTF = 7
        INTCAP = 8
        GPIO = 9  # Port pin value
        OLAT = 10  # Output latch value

    def __init__(self, regs: list[Register]):
        # Get the SPI control and status registers for this slice
        self.control, self.status, self.sdo, self.sdi = regs

        # Initialize the MCP
        # always use 8 bit payload. Don't auto-increment addresses
        self.write_reg(Mcp23.R.IOCON, Mcp23.B_SEQOP)
        # Set all output pins high
        self.write_reg(Mcp23.R.OLAT, 0xFF)
        # Enable Outputs
        self.write_reg(Mcp23.R.IODIR, 0)

    def write_reg(self, addr: int, val: int):
        """write to a Mcp23 register. Note that its MISO is not connected, no reads possible"""
        # select the MCP23, disable shared SPI clock for the other chips on the slice
        self.control.mode = 0  # sample on rising edge (CPHA = 0)
        self.control.cs = 1

        # construct a 24 bit data-frame
        self.control.length = 24
        tmp = (Mcp23.OPCODE_W << 16) | ((addr & 0xFF) << 8) | (val & 0xFF)

        # send it by writing to the 32 bit sdo register. Left-aligned!
        self.sdo[:] = tmp << 8
        while int(self.status) == 0:
            time.sleep(1e-4)

        # de-select MCP23, enable shared SPI clock
        self.control.cs = 0

    def select_chip(self, chip_id: int | None = None):
        """selects a chip (chip_id from 0 - 7) on the shared SPI bus of the slice.
        It does this by setting an output of the MCP23 low.
        If chip_id = None is given, no chip will be selected (all outputs of the MCP23 high).
        """
        val = 0xFF
        if chip_id is not None:
            val = ~(1 << chip_id) & 0xFF
        self.write_reg(Mcp23.R.OLAT, val)

    def spi_transaction(self, chip_id: int, data_word: int, n_bits: int, spi_mode=0):
        """carry out a general SPI transaction on the shared SPI bus
        chip_id (0 - 7): which CS_N output to set low on the MCP23 for this transaction
        data_word: the value to send on the bus. MSB first.
        n_bits (1 - 32): the number of bits to send / receive.
        spi_mode: bit 0 is the value of CPHA, bit 1 is CPOL
        returns the received value as int
        """
        self.select_chip(chip_id)

        self.control.mode = spi_mode
        self.control.length = n_bits
        self.sdo[:] = data_word << (32 - n_bits)  # left align
        while int(self.status) == 0:
            time.sleep(1e-4)

        r_dat = int(self.sdi[:])

        self.select_chip(None)  # set CS_N high for next transaction

        return r_dat


class Ina239:
    def __init__(
        self,
        mcp: Mcp23,
        chip_id: int,
        r_shunt=115e-3,
        MODE=0xF,
        VBUSCT=0x5,
        VSHCT=0x5,
        VTCT=0x5,
        AVG=0,
    ):
        """initialize and configure a INA239
        chip_id (0 - 7): which chip-select to enable on the MCP23
        r_shunt is the value of the shunt resistor in [Ohm]
        the other parameters are written to the config register.
        See Table 7-6 in INA239 datasheet
        """
        self.chip_id = chip_id
        self.r_shunt = r_shunt
        self.mcp = mcp

        # Write the configuration register
        self.cfg_val = (
            ((MODE & 0xF) << 12)
            | ((VBUSCT & 7) << 9)
            | ((VSHCT & 7) << 6)
            | ((VTCT & 7) << 3)
            | (AVG & 7)
        )
        self.write_reg(0x01, self.cfg_val)

    def read_reg(self, addr: int):
        """Reads a INA239 register on the shared SPI bus
        addr: INA239 register address to read, 6 bits
        """
        return self.mcp.spi_transaction(self.chip_id, (addr << 18) | (1 << 16), 24, 1)

    def write_reg(self, addr: int, value: int):
        """Writes a INA239 register on the shared SPI bus
        addr: register address to write, 6 bits
        value: the 16 bit value to write to the register
        """
        return self.mcp.spi_transaction(
            self.chip_id, (addr << 18) | (value & 0xFFFF), 24, 1
        )

    def get_current(self):
        """returns shunt current in [A]"""
        val_uint = self.read_reg(0x4)
        val_int = sign_extend(val_uint, 16)
        return val_int * 5e-6 / self.r_shunt

    def get_voltage(self):
        """returns bus voltage in [V]"""
        val_uint = self.read_reg(0x5)
        val_int = sign_extend(val_uint, 16)
        return val_int * 3.125e-3

    def get_temperature(self):
        """returns chip temperature in [degC]"""
        val_uint = self.read_reg(0x6) >> 4
        val_int = sign_extend(val_uint, 12)
        return val_int * 0.125


class Hmc1122:
    def __init__(self, mcp: Mcp23, chip_id: int):
        """chip_id (3 - 7): which chip-select to enable on the MCP23"""
        self.mcp = mcp
        self.chip_id = chip_id
        self.last_value = 0

    def write_reg(self, value: int):
        """set attenuation value
        value (0 - 63): the raw 6 bit attenuation value to write
        """
        self.last_value = value & 0x3F
        self.mcp.spi_transaction(self.chip_id, self.last_value, 6)

    def get_db(self):
        """returns the last written attenuation value in [dB]"""
        return ((~self.last_value) & 0x3F) / 2

    def set_db(self, value: float):
        """set the attenuation value in [dB]
        value: attenuation value in [dB] between 0.0 and 31.5,
        only 0.5 dB steps are allowed
        """
        value = float(value * 2)
        if not value.is_integer() or value < 0 or value > (31.5 * 2):
            raise RuntimeError("Attenuation value not supported")
        self.write_reg((~int(value)) & 0x3F)


class Slice:
    def __init__(self, reg_map, slice_id: int, clk_div=0x80):
        """Represents a frontend-slice with attenuators and sensors
        reg_map is a DefaultIP.register_map instance
        slice_id (0 - 7) defines which SPI-peripheral to attach to (there is 1 per slice)
        clk_div is the SPI clock-divider, driven from a 100 MHz clock

        Each slice features
          * 1x MCP23S8 (self.mcp)
          * 3x INA239 (self.sensors)
          * Nx HMC1122 (self.attenuators)
        """
        # Extract relevant SPI control registers. Order is important.
        self.regs = [
            reg_map._instances[f"spi{slice_id}_control"],
            reg_map._instances[f"spi{slice_id}_status"],
            reg_map._instances[f"spi{slice_id}_sdo"],
            reg_map._instances[f"spi{slice_id}_sdi"],
        ]
        self.regs[0].clk_divider = clk_div

        self.mcp = Mcp23(self.regs)
        # Every slice always has 3x INA239 connected to the first 3 CS_N outputs of the MCP23
        self.sensors = [Ina239(self.mcp, chip_id, AVG=3) for chip_id in range(3)]
        # On the other CS_N pins, there are 2x or 4x HMC1122, depending on the slice type.
        # I will instantiate 4 here, for some slices the last 2 will not be connected.
        self.attenuators = [Hmc1122(self.mcp, chip_id) for chip_id in (3, 4, 5, 6)]

    def is_present(self):
        """returns True if the first INA239 on the slice is responding"""
        return self.sensors[0].read_reg(0x3E) == 0x5449


class FrontendControl(DefaultIP):
    bindto = ["xilinx.com:module_ref:frontend_control_axi:1.0"]

    def __init__(self, description):
        """PYNQ driver for the Flexible analog Front End
        Supports reading the IN239 sensors and setting the HMC1122 attenuation values
        for each of the 8 slices.

        For example, set first attenuator on the 2nd slice to 3 dB:
            self.slices[1].attenuators[0].set_db(3.0)

        Read temperature of the 3rd slice:
            self.slices[2].sensors[0].get_temperature()
        """
        root_path = Path(__file__).parent.parent.parent
        json_path = root_path / "designs/ip/rtl/frontend_control_axi.json"
        # json_path = "/home/xilinx/pynq_llrf/designs/ip/rtl/frontend_control_axi.json"

        with open(json_path, "r") as f:
            self.json_dat = json.load(f)

        description["registers"] = self.json_dat["csr_registers"]
        super().__init__(description)

        print("Powering up and initializing analog frontend ...")
        self.set_power(True)
        time.sleep(100e-3)

        # We only have 7 slices actually, because Slice3_CS controls the power switch!
        self.slices = []
        for i in range(8):
            if i == 3:
                self.slices.append(None)
            else:
                self.slices.append(Slice(self.register_map, i))

    def set_power(self, value: bool):
        """when value is true, enables the power to the frontend
        this connects to the buck_en signal, which needs to be driven high
        to enable all power-supplies. To drive it high we need to set the
        chip-select signal low.
        """
        self.register_map.spi3_control.cs = not value
