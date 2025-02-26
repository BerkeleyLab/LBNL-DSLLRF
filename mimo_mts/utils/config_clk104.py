from pathlib import Path
import struct
import xrfclk
from .config_tics import LMKConfig, LMXConfig


class CLK104Config:
    def __init__(self,
                 lmk_tcs='LMK04828.tcs',
                 lmxadc_tcs='LMX2594.tcs',
                 lmxdac_tcs='LMX2594.tcs'):
        self.lmk_cfg = LMKConfig(lmk_tcs)
        self.lmxadc_cfg = LMXConfig(lmxadc_tcs)
        self.lmxdac_cfg = LMXConfig(lmxdac_tcs)
        self.devinfo = self.find_devices()

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
        xrfclk._write_LMK_regs(self.lmk_cfg.reg_vals, self.devinfo['lmk'])
        xrfclk._write_LMX_regs(
            self.lmxadc_cfg.reg_vals, self.devinfo['lmxadc'])
        xrfclk._write_LMX_regs(
            self.lmxdac_cfg.reg_vals, self.devinfo['lmxdac'])
