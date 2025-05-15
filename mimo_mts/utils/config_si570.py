import numpy as np
from smbus2 import SMBus
from time import sleep


class SI570:
    def __init__(self, **kwargs):
        """
        Provides a class to configure the SI570 clock generator, which is
        used in the MIMO MTS system as the GTY (EVR) reference clock input.

        The default frequency of the SI570 of the PYNQ devicetree is 148.5 MHz.
        Reconfigure to 1/16 of the GTY line rate (at 2.5 Gbps) which is
        156.25 MHz for the GTY reference clock input.
        The actual frequency is 156.1375 MHz for ALS application.

        On ZCU208 board, the SI570 is connected to the I2C bus 1, address 0x5D.
        Accessible through via U26 TCA9548A I2C multiplexer at address 0x74.
        The part number is Silicon Labs SI570BAB000544DG, U48.
        In Linux device tree, the chip is available at /dev/i2c-1,
        or /sys/bus/i2c/devices/9-005d.
        """
        self.dev = kwargs.get('dev', '/dev/i2c-1')
        self.i2c_mux_addr = kwargs.get('i2c_mux_addr', 0x74)
        self.i2c_mux_chan = kwargs.get('i2c_mux_chan', 3)
        self.i2c_addr = kwargs.get('i2c_addr', 0x5D)
        self.start_address = kwargs.get('start_address', 7)
        self.default_freq_mhz = kwargs.get('default_freq_mhz', 156.25)  # MHz

        self.bus = SMBus(self.dev, force=True)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.bus.close()

    def set_i2c_mux(self):
        """Write the control register of the TCA9548A I2C multiplexer
           to select the channel of the SI570.
        """
        self.bus.write_byte_data(
            self.i2c_mux_addr, 0, (1 << self.i2c_mux_chan))

    def get_xtal_freq(self):
        """Get the crystal frequency of the SI570
           Returns: fxtal (float): the crystal frequency in MHz
        """
        # reset si570 to read default registers, corresponds to default freq
        self.bus.write_block_data(self.i2c_addr, 135, [0x80])

        # it causes loss of I2C communication
        sleep(0.01)
        a = self.bus.read_i2c_block_data(self.i2c_addr, self.start_address, 6)
        hs_div = (a[0] >> 5) + 4
        n1 = (((a[0] & 0x1F) << 2) | (a[1] >> 6)) + 1
        rfreq = np.uint64(
            (((a[1] & 0x3F) << 32) | (a[2] << 24) |
             (a[3] << 16) | (a[4] << 8) | a[5])
        ) / (2**28)
        fdco = self.default_freq_mhz * n1 * hs_div
        fxtal = fdco / rfreq
        return fxtal

    def set_freq(self, freq_mhz=156.25):
        """Configure the SI570 to a new frequency
           Args:
               freq_mhz (float): the new frequency in MHz
        """
        self.set_i2c_mux()
        self.fxtal = self.get_xtal_freq()

        best = [0, 0, 6000.0]
        for i in range(0, 65):
            n1_i = i * 2
            if i == 0:
                n1_i = 1
            for hsdiv_i in [4, 5, 6, 7, 9, 11]:
                fdco_i = freq_mhz * n1_i * hsdiv_i
                if (fdco_i > 4850.0) and (fdco_i < 5670.0):
                    if fdco_i < best[2]:
                        best = [n1_i, hsdiv_i, fdco_i]

        rfreq = int(best[2] * float(2**28) / self.fxtal)
        n1 = best[0] - 1
        hs_div = best[1] - 4

        regs = []
        # build registers
        # reg 7: hs_div[2:0], n1[6:2]
        reg7 = (hs_div << 5) | ((n1 & 0x7C) >> 2)
        reg8 = ((n1 & 3) << 6) | (rfreq >> 32)  # reg 8: n1[1:0] rfreq[37:32]
        reg9 = (rfreq >> 24) & 0xFF  # reg 9: rfreq[31:24]
        reg10 = (rfreq >> 16) & 0xFF  # reg 10: rfreq[23:16]
        reg11 = (rfreq >> 8) & 0xFF  # reg 11: rfreq[15:8]
        reg12 = rfreq & 0xFF  # reg 12: rfreq[7:0]

        # freeze DCO
        self.bus.write_byte_data(self.i2c_addr, 0x89, 0x10)

        # write new registers
        regs = [reg7, reg8, reg9, reg10, reg11, reg12]
        self.bus.write_i2c_block_data(self.i2c_addr, 0x7, regs)

        # unfreeze DCO
        self.bus.write_byte_data(self.i2c_addr, 0x89, 0x0)
        # assert NewFreq bit
        self.bus.write_byte_data(self.i2c_addr, 0x87, 0x40)
        # needs at least 10 ms
        sleep(0.01)
