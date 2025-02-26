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
        self.dac_iq_interleave = self.converters_per_tile == 4  # Quad DACs


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

lbl208 = Board(name='LBL208',
               active_adc_tiles=0b1111,
               active_dac_tiles=0b1111,
               adc_sampling_rate=4.0e9,
               dac_sampling_rate=4.0e9,
               converters_per_tile=2,
               adc_ref_tile=225,
               dac_ref_tile=230,
               mts_adc_target_latency=96,
               mts_dac_target_latency=128)

board_info = {
    'ZCU208': zcu208,
    'ZCU216': zcu216,
    'LBL208': lbl208
}


if __name__ == '__main__':
    print(zcu208.n_adcs)
