import logging
from configparser import ConfigParser
from pathlib import Path
import struct
import xrfclk
import spidev  # not used by xrfclk, but needed for register readback
from pynq import GPIO
from .config_tics import LMKConfig, LMXConfig

logger = logging.getLogger(__name__)


class CLK104Config:
    def __init__(
        self,
        lmk_tcs="LMK04828_500M_CLKin0_DIST.tcs",
        lmxadc_tcs="LMX2594.tcs",
        lmxdac_tcs="LMX2594.tcs",
        write=True,
        verify=False,
        log_level=logging.INFO,
    ):
        """
        lmk_tcs, lmxadc_tcs, lmxdac_tcs: .tcs file-names with register-values for these chips
        write: if True, write register values to the 3 chips on init
        verify: if True, enables verify_regs() method. Not supported by all platforms yet.
            expects that the clk104 SPI readback mux is controlled by PYNQ gpio pin 0 and 1

        Note that these arguments are normally sourced from the configuration dict() in config.py
        """
        logger.setLevel(log_level)
        self.lmk_cfg = LMKConfig(lmk_tcs)
        self.lmxadc_cfg = LMXConfig(lmxadc_tcs)
        self.lmxdac_cfg = LMXConfig(lmxdac_tcs)
        if write:
            self.devinfo = self.find_devices()
            self.write_regs()

        self.verify = verify
        if verify:
            # Multiplexer for the SDO signal going from LM* chip to FPGA-IO
            self.mux_sel = [GPIO(GPIO.get_gpio_pin(i), "out") for i in range(2)]

            self.v_lmx_adc = Lmx2594Verifier(
                path=self.devinfo["lmxadc"]["spi_device"],
                config=self.lmxadc_cfg.config,
                mux_sel=self.mux_sel,
                mux_val=0,
                name="LMX2594_ADC",
            )
            self.v_lmx_dac = Lmx2594Verifier(
                path=self.devinfo["lmxdac"]["spi_device"],
                config=self.lmxdac_cfg.config,
                mux_sel=self.mux_sel,
                mux_val=1,
                name="LMX2594_DAC",
            )
            self.v_lmk = Lmk0482Verifier(
                path=self.devinfo["lmk"]["spi_device"],
                config=self.lmk_cfg.config,
                mux_sel=self.mux_sel,
                mux_val=2,
                name="LMK04828",
            )

    def __repr__(self):
        str = (
            f"< {self.__class__.__name__:12s} >:\n"
            f"  === LMK04828: ===\n{self.lmk_cfg}\n"
            f"  === LMX2594 ADC: ===\n{self.lmxadc_cfg}\n"
            f"  === LMX2594 DAC: ===\n{self.lmxdac_cfg}"
        )
        return str

    def find_devices(self):
        devinfo = {}
        for dev in Path("/sys/bus/spi/devices").glob("*"):
            node = dev / "of_node"
            compatible = (node / "compatible").read_text().rstrip("\x00")
            node_name = (node / "name").read_text().rstrip("\x00")

            if compatible == "ti,lmk04828" or compatible == "ti,lmx2594":
                # call spidev_bind to bind /dev/spidevB.C
                if (dev / "driver").exists():
                    (dev / "driver" / "unbind").write_text(dev.name)
                xrfclk._spidev_bind(dev)

                num_bytes = struct.unpack(">I", (node / "num_bytes").read_bytes())[0]
                devinfo[node_name] = {
                    "spi_device": xrfclk._get_spidev_path(dev),
                    "compatible": compatible,
                    "num_bytes": num_bytes,
                }
        if not {"lmk", "lmxadc", "lmxdac"}.issubset(devinfo):
            raise KeyError(
                "Missing required device configuration (lmk, lmxadc, or lmxdac)"
            )
        return devinfo

    def write_regs(self):
        """Write registers on all 3 chips with values from the loaded .tcs files"""
        xrfclk._write_LMK_regs(self.lmk_cfg.reg_vals, self.devinfo["lmk"])
        xrfclk._write_LMX_regs(self.lmxadc_cfg.reg_vals, self.devinfo["lmxadc"])
        xrfclk._write_LMX_regs(self.lmxdac_cfg.reg_vals, self.devinfo["lmxdac"])

    def verify_regs(self):
        """
        Readback and verify the registers of all 3 chips which were written before.
        Requires overlay support, only works after overlay is downloaded.
        Returns True on success (or if verification is disabled), False on verification error.
        """
        if not self.verify:
            return True

        is_pass = self.v_lmx_adc.verify_regs()
        is_pass &= self.v_lmx_dac.verify_regs()
        is_pass &= self.v_lmk.verify_regs()
        return is_pass

    def is_locked(self):
        """
        Read the PLL lock status of all 3 chips. Returns True if all 3 are locked.
        Also returns True if register verification has been disabled in __init__()
        """
        if not self.verify:
            return True

        is_pass = self.v_lmx_adc.is_locked()
        is_pass &= self.v_lmx_dac.is_locked()
        is_pass &= self.v_lmk.is_locked()
        return is_pass


class LmVerifier:
    def __init__(
        self,
        path: str,
        config: ConfigParser,
        data_width: int,
        mux_sel: list[GPIO],
        mux_val: int,
        name: str | None = None,
        exclude_regs: set[int] | None = None,
    ):
        """Helper class to read back and verify registers from LMX2594 or LMK04828 devices
        path: is the linux device path (/dev/spidev*)
        config: is a ConfigParser instance with a loaded .tcs file. The regmap will be parsed
            and used for verification as the _expected_ chip configuration.
        data_width: is the width of a register-value in [bytes].
            only 1 (LMK0482x) and 2 (LMX2594) are supported.
        mux_sel: is a list with two PYNQ GPIO instances, which are used to control the SPI readback
            multiplexer on the CLK104 board
        mux_val: is the value to write to the mux to select this chip
        name: is used for logging to identify this chip
        exclude_regs: is a set of register addresses which will be ignored during verification
        """
        self.path = path
        self.reg_map = parse_tcs(config, data_width)
        self.data_width = data_width
        self.mux_sel = mux_sel
        self.mux_val = mux_val
        if name is None:
            name = path
        self.name = name
        self.exclude_regs = {}
        if exclude_regs is not None:
            self.exclude_regs = exclude_regs

        self.spi = spidev.SpiDev()
        self.spi.open_path(path)

    def mux_select(self):
        """set the SPI readback mux to select this chip"""
        self.mux_sel[0].write(self.mux_val & 1)
        self.mux_sel[1].write((self.mux_val >> 1) & 1)

    def enable_sdo(self):
        """make sure SPI readback and lock detect is enabled in the chip configuration"""
        raise NotImplementedError()

    def is_locked(self):
        raise NotImplementedError()

    def write_reg(self, reg_addr: int, val: int):
        b_reg_addr = reg_addr.to_bytes(3 - self.data_width, "big")
        b_val = val.to_bytes(self.data_width, "big")
        self.spi.xfer(b_reg_addr + b_val)

    def read_reg(self, reg_addr: int):
        reg_addr |= 0x8000 if self.data_width == 1 else 0x80  # set the read bit
        b_reg_addr = reg_addr.to_bytes(3 - self.data_width, "big")
        b_rx = self.spi.xfer(b_reg_addr + bytes(self.data_width))
        return int.from_bytes(b_rx[-self.data_width:], "big")

    def verify_regs(self):
        """
        Read register values and compare against the ones from the .tcs file.
        Returns false if they don't agree.
        """
        self.mux_select()
        verify_ok = True
        n = 0
        for addr, tcs_value in self.reg_map.items():
            read_value = self.read_reg(addr)
            if addr in self.exclude_regs:
                logger.debug(f"{self.name}: Register 0x{addr:04x} excluded")
                continue
            logger.debug(
                f"{self.name}: Register 0x{addr:04x} value 0x{read_value:04x}, expect: 0x{tcs_value:04x}"
            )
            if read_value != tcs_value:
                logger.error(
                    f"{self.name}: Register 0x{addr:04x} value 0x{read_value:04x} doesn't match .tcs: 0x{tcs_value:04x}"
                )
                verify_ok = False
            n += 1
        if verify_ok:
            logger.info(f"{self.name}: Registers verified OK")
        else:
            logger.error(f"{self.name}: Register verification failed")
        return verify_ok

    def change_config(self, reg_addr, por_value, value, mask=0xFFFF):
        """
        Sometimes certain register values are needed to enable verification / lock detect features
        This function checks if the registers are set to the right value in the .tcs
        If not, the value is written to the chip and a Warning is logged.
        """
        # Check if the regs are in the reg_map. If not add the POR value.
        if reg_addr not in self.reg_map:
            self.reg_map[reg_addr] = por_value

        # Check if the reg_map value corresponds to the wanted value. If not, change it.
        old_val = self.reg_map[reg_addr]
        if old_val & mask != value & mask:
            self.mux_select()
            new_val = (old_val & ~mask) | value
            logger.warning(
                f"{self.name}: Changing Reg 0x{reg_addr:x} from 0x{old_val:02x} to 0x{new_val:02x}. Fix the .tcs!"
            )
            self.write_reg(reg_addr, new_val)
            self.reg_map[reg_addr] = new_val


class Lmx2594Verifier(LmVerifier):
    def __init__(
        self,
        path: str,
        config: ConfigParser,
        mux_sel: list[GPIO],
        mux_val: int,
        name: str | None = None,
    ):
        """Helper class to read back and verify registers from LMX2594 devices
        path: shall point to the linux spidev device (/dev/spidev*.*)
        config: is a ConfigParser instance with a loaded .tcs file. The regmap will be parsed
            and used for verification as the _expected_ chip configuration.
        mux_sel: is a list with two PYNQ GPIO instances, which are used to control the SPI readback
            multiplexer on the CLK104 board
        mux_val: is the value to write to the mux to select this chip
        name: is an optional string which will be used in print messages to identify the chip
        """
        exclude = {107, 108, 109, 110, 111, 112}
        super().__init__(path, config, 2, mux_sel, mux_val, name, exclude)
        self.enable_sdo()

    def enable_sdo(self):
        """Make sure that MUX_OUT_LD_SEL is 0. To enable the SPI SDO pin"""
        self.change_config(0, 0b0010010000010000, 0, 1 << 2)

    def is_locked(self):
        """return true if the chip is locked. False if there is an error."""
        self.mux_select()
        reg110 = self.read_reg(110)
        rb_LD_VTUNE = (reg110 >> 9) & 3
        rb_VCO_SEL = (reg110 >> 5) & 7

        if rb_LD_VTUNE != 2:
            logger.error(f"{self.name}: PLL not locked, rb_LD_VTUNE = {rb_LD_VTUNE}")
            return False

        logger.info(
            f"{self.name}: PLL locked, rb_LD_VTUNE = {rb_LD_VTUNE}, rb_VCO_SEL = {rb_VCO_SEL}"
        )
        return True

    def trigger_fcal(self):
        """triggers the VCO frequency calibration"""
        r0 = self.read_reg(0) & ~(1 << 3)
        self.write_reg(0, r0)  # reset FCAL_EN
        self.write_reg(0, r0 | (1 << 3))  # set FCAL_EN


class Lmk0482Verifier(LmVerifier):
    def __init__(
        self,
        path: str,
        config: ConfigParser,
        mux_sel: list[GPIO],
        mux_val: int,
        name: str | None = None,
    ):
        """Helper class to read back and verify registers from LMK0482 devices
        path: shall point to the linux spidev device (/dev/spidev*.*)
        config: is a ConfigParser instance with a loaded .tcs file. The regmap will be parsed
            and used for verification as the _expected_ chip configuration.
        mux_sel: is a list with two PYNQ GPIO instances, which are used to control the SPI readback
            multiplexer on the CLK104 board
        mux_val: is the value to write to the mux to select this chip
        name: is an optional string which will be used in print messages to identify the chip
        """
        exclude = {
            0x6,
            0x182,
            0x183,
            0x184,
            0x185,
            0x186,
            0x187,
            0x188,
            0x189,
            0x1FFF,
            0x015F,
            0x018B,
        }
        super().__init__(path, config, 1, mux_sel, mux_val, name, exclude)
        self.enable_sdo()

    def enable_sdo(self):
        """
        change the chip configuration to enable the SPI SDO pin and PLL lock detect
        PLL1_LD_MUX = 7 (SPI readback)
        PLL2_LD_MUX = 3 (PLL1 and PLL2 DLD)
        """
        # PLL1_LD_MUX --> SPI readback
        self.change_config(0x15F, (1 << 3) | 6, (7 << 3) | 3)
        # PLL2_LD_MUX --> PLL1 and PLL2 DLD
        self.change_config(0x16E, (2 << 3) | 6, (3 << 3) | 3)

    def is_locked(self):
        """Return True if PLLs are locked or powered down."""
        self.mux_select()
        is_okay = True

        reg140 = self.read_reg(0x140)
        reg173 = self.read_reg(0x173)
        if ((reg140 >> 7) & 1) or ((reg173 >> 5) & 1):
            logger.info(
                f"{self.name}: At least one PLL is powered down. Can't read lock status."
            )
            return is_okay

        reg183 = self.read_reg(0x183)
        if (reg183 & 2) == 0:
            logger.error(
                f"{self.name}: At least one PLL is unlocked, reg183 = {reg183:08b}"
            )
            is_okay = False
        else:
            logger.info(f"{self.name}: Both PLLs are locked, reg183 = {reg183:08b}")

        return is_okay


def parse_tcs(config: ConfigParser, data_width=2):
    """returns a dictionary with address (int), register-value (int)
    data_width is the width of the register-value in [bytes].
        only 1 (LMK0482x) and 2 (LMX2594) are supported.
    """
    data_width *= 8  # convert [bytes] to [bits]
    temp_dict = {k: v for k, v in config.items("MODES")}
    out_dict = {}
    for k, v in temp_dict.items():
        if k.startswith("name"):
            # k = "name00"
            # v = "R112"
            reg_val24 = int(temp_dict[k.replace("name", "value")])
            # reg_val24 = 7340032
            reg_addr = int(v.split(" ")[0][1:])
            # reg_addr = 112
            if reg_addr != (reg_val24 >> data_width):
                raise RuntimeError("Value not consistent with register address")
            # reg_val24 contains the address in its MSBs. Strip it.
            out_dict[reg_addr] = reg_val24 & ((1 << data_width) - 1)
    return out_dict
