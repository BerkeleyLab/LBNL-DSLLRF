import configparser
import re
from pathlib import Path


class TICSConfig:
    """
    Utility class to parse TICS configuration file
    """
    def __init__(self, config_file='LMX2594.tcs'):
        self.config = config = configparser.ConfigParser(strict=False)
        config.read(config_file, encoding='utf-8-sig')
        self.part = config['SETUP']['PART']

        self.regmap = regmap = {}
        for k, v in config['MODES'].items():
            if 'name' in k:
                id = int(re.split(r'(\d+)', k)[1])
                regmap[id] = {'addr': v}
            elif 'value' in k:
                id = int(re.split(r'(\d+)', k)[1])
                regmap[id]['value'] = int(v)

        # list of register address and values to be written
        self.reg_vals = [d['value'] for id, d in regmap.items()]

    def __repr__(self):
        attr = 'part'
        return f'{attr:16s}: {getattr(self, attr):>12}\n'

    def export_regmap(self, filename):
        """export to TICS txt format"""
        with open(filename, 'w') as f:
            for id, d in self.regmap.items():
                f.write(f'{d["addr"]}\t0x{d["value"]:06X}\n')


class LMKConfig(TICSConfig):
    """
    Utility class to parse TICS configuration file for LMK04828
    """
    def __init__(self, config_file='LMK04828.tcs'):
        super().__init__(config_file)
        assert self.part == 'LMK04828B', "Invalid part number"
        attrs = ['SYSREF_FREQ', 'OSCout_FREQ']
        attrs += [f'CLKin{i}_FREQ' for i in range(3)]
        attrs += [f'CLKout{i}_FREQ' for i in range(14)]
        for attr in attrs:
            setattr(self, attr, float(self.config.get('FLEX', attr)))
        self.attrs = attrs

        # Table 38. LMK04828 Register Map
        self.clkin_sel_mode_desc = {
            0: 'CLKin0',
            1: 'CLKin1',
            2: 'CLKin2',
            3: 'Pin Sel',
            4: 'Auto',
            5: 'Reserved',
            6: 'Reserved',
            7: 'Reserved'
        }
        # Table 25. LMK04828 Register Map
        self.vco_mux_desc = {
            0: 'VCO0',
            1: 'VCO1',
            2: 'CLKin1 (ext)',
            3: 'Reserved'
        }
        for v in self.reg_vals:
            if v >> 8 == 0x147:
                field = (v & 0x70) >> 4
                self.CLKin_SEL_MODE = self.clkin_sel_mode_desc[field]
            elif v >> 8 == 0x138:
                field = (v & 0b0110_0000) >> 5
                self.VCO_MUX = self.vco_mux_desc[field]

    def __repr__(self):
        s = super().__repr__()
        s += '\n'.join(f'{attr:16s}: {getattr(self, attr):12.3f} MHz'
                       for attr in self.attrs)
        s += '\n'
        s += '\n'.join(
            f'{attr:16s}: {getattr(self, attr):>12}'
            for attr in ['CLKin_SEL_MODE', 'VCO_MUX'])
        return s


class LMXConfig(TICSConfig):
    """
    Utility class to parse TICS configuration file for LMX2594
    """
    def __init__(self, config_file='LMX2594.tcs'):
        super().__init__(config_file)
        assert self.part == 'LMX2594', "Invalid part number"
        attrs = ['Fosc_FREQ', 'FoutA_FREQ', 'FoutB_FREQ', 'Fpd_FREQ',
                 'Fvco_FREQ']
        for attr in attrs:
            setattr(self, attr, float(self.config.get('FLEX', attr)))
        self.attrs = attrs

    def __repr__(self):
        s = super().__repr__()
        s += '\n'.join(f'{attr:16s}: {getattr(self, attr):12.3f} MHz'
                       for attr in self.attrs)
        return s


if __name__ == '__main__':
    p = Path().cwd().parent.parent / 'designs' / 'CLK104'

    for file in p.glob('*.tcs'):
        print('*' * 80)
        print(file.name)
        if 'LMK' in file.name:
            lmk = LMKConfig(file)
            print('*' * 80)
            print(lmk)
        elif 'LMX' in file.name:
            lmx = LMXConfig(file)
            print('*' * 80)
            print(lmx)
