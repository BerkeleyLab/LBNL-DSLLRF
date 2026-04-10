from pathlib import Path
import struct
import xrfclk
from .config_tics import LMKConfig, LMXConfig
import spidev # not used by xrfclk, but needed for register _reads_


class CLK104Config:
    def __init__(self,
                 lmk_tcs='LMK04828_500M_CLKin0_DIST.tcs',
                 lmxadc_tcs='LMX2594.tcs',
                 lmxdac_tcs='LMX2594.tcs',
                 write=True):
        self.lmk_cfg = LMKConfig(lmk_tcs)
        self.lmxadc_cfg = LMXConfig(lmxadc_tcs)
        self.lmxdac_cfg = LMXConfig(lmxdac_tcs)
        if write:
            self.devinfo = self.find_devices()
            self.write_regs()

    def __repr__(self):
        str = (f"< {self.__class__.__name__:12s} >:\n"
               f"  === LMK04828: ===\n{self.lmk_cfg}\n"
               f"  === LMX2594 ADC: ===\n{self.lmxadc_cfg}\n"
               f"  === LMX2594 DAC: ===\n{self.lmxdac_cfg}")
        return str

    def find_devices(self):
        devinfo = {}
        for dev in Path('/sys/bus/spi/devices').glob('*'):
            node = dev / 'of_node'
            compatible = (node / 'compatible').read_text().rstrip('\x00')
            node_name = (node / 'name').read_text().rstrip('\x00')

            if compatible == 'ti,lmk04828' or compatible == 'ti,lmx2594':
                # call spidev_bind to bind /dev/spidevB.C
                if (dev / 'driver').exists():
                    (dev / 'driver' / 'unbind').write_text(dev.name)
                xrfclk._spidev_bind(dev)

                num_bytes = struct.unpack(
                    '>I', (node / 'num_bytes').read_bytes())[0]
                devinfo[node_name] = {
                    'spi_device': xrfclk._get_spidev_path(dev),
                    'compatible': compatible,
                    'num_bytes': num_bytes
                }
        assert 'lmk' in devinfo, "LMK not found"
        assert 'lmxadc' in devinfo, "LMXADC not found"
        assert 'lmxdac' in devinfo, "LMXDAC not found"
        return devinfo

    def write_regs(self):
        xrfclk._write_LMK_regs(
            self.lmk_cfg.reg_vals, self.devinfo['lmk'])
        xrfclk._write_LMX_regs(
            self.lmxadc_cfg.reg_vals, self.devinfo['lmxadc'])
        xrfclk._write_LMX_regs(
            self.lmxdac_cfg.reg_vals, self.devinfo['lmxdac'])

    def verify_regs(self, key='lmxadc'):
        spi = spidev.SpiDev()
        spi.open_path(self.devinfo[key]['spi_device'])
        read_regs = []
        for i in range(0x80):
            dat_o = bytes((0x8 | i, 0, 0))
            dat_i = spi.xfer(dat_o)
            read_regs.append(int.from_bytes(dat_i[1:], 'big'))
        return read_regs
