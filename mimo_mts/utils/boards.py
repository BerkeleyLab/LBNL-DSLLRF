from dataclasses import dataclass


@dataclass
class Board:
    name: str = 'ZCU208'
    active_adc_tiles: int = 0b1111
    active_dac_tiles: int = 0b1111
    adc_sampling_rate: float = 4.0e9
    dac_sampling_rate: float = 4.0e9
    converters_per_tile: int = 2
    adc_ref_tile: int = 225
    dac_ref_tile: int = 230
    adc_decimation_fator: int = 1
    dac_interpolation_fator: int = 2  # due to C2R mixer, and sampling rate
    mts_adc_target_latency: int = 0
    mts_dac_target_latency: int = 0

    def __post_init__(self):
        self.adc_ref_index = self.adc_ref_tile - 224
        self.dac_ref_index = self.dac_ref_tile - 228
        self.num_adc_tiles = bin(self.active_adc_tiles).count('1')
        self.num_dac_tiles = bin(self.active_dac_tiles).count('1')
        self.n_adcs = self.num_adc_tiles * self.converters_per_tile
        self.n_dacs = self.num_dac_tiles * self.converters_per_tile
        self.adc_iq_interleave = self.converters_per_tile == 4  # Quad ADCs


zcu208 = Board(name='ZCU208',
               active_adc_tiles=0b1111,
               active_dac_tiles=0b1111,
               adc_sampling_rate=4.0e9,
               dac_sampling_rate=4.0e9,
               converters_per_tile=2,
               adc_ref_tile=225,
               dac_ref_tile=230,
               mts_adc_target_latency=96,
               mts_dac_target_latency=128)

zcu216 = Board(name='ZCU216',
               active_adc_tiles=0b1111,
               active_dac_tiles=0b1111,
               adc_sampling_rate=2.0e9,
               dac_sampling_rate=4.0e9,
               converters_per_tile=4,
               adc_ref_tile=225,
               dac_ref_tile=229,
               mts_adc_target_latency=104,
               mts_dac_target_latency=136)

lbl208_dac2x = Board(
               name='LBL208_DAC2X',
               active_adc_tiles=0b1111,
               active_dac_tiles=0b1111,
               adc_sampling_rate=3.5e9,
               dac_sampling_rate=7.0e9,
               converters_per_tile=2,
               adc_ref_tile=225,
               dac_ref_tile=230,
               dac_interpolation_fator=4,
               mts_adc_target_latency=96,
               mts_dac_target_latency=544)

board_info = {
    'ZCU208': zcu208,
    'ZCU216': zcu216,
    'LBL208': zcu208,
    'LBL208_DAC2X': lbl208_dac2x
}


if __name__ == '__main__':
    print(zcu208.n_adcs)
