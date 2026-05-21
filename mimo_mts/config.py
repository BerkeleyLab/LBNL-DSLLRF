from mimo_mts.utils.boards import zcu208, zcu216, lbl208
import mimo_mts.utils.clk104 as clk104
import mimo_mts.overlays as overlays
from importlib.resources import files


ol_configs = {
    'MIMO_ZCU208': {
        'bitfile_name': files(overlays).joinpath('mimo_mts.bit'),
        'board': zcu208,
        'clk104_tcs': {
            'lmk_tcs': files(clk104).joinpath('LMK04828_500M_CLKin0.tcs'),
            'lmxadc_tcs': files(clk104).joinpath('LMX2594_4G.tcs'),
            'lmxdac_tcs': files(clk104).joinpath('LMX2594_4G.tcs'),
        },
        'rfdc': {
            'adc_decimation_factor': 1,
            'dac_interplation_factor': 2,
            'mixer': {
                'adc_mixer_nco_freq_mhz': 0,
                'adc_mixer_nco_nyquist': 1,
                'adc_mixer_nco_phase': 0,
                'dac_mixer_nco_freq_mhz': 0,
                'dac_mixer_nco_nyquist': 1,
                'dac_mixer_nco_phase': 0,
            },
            'mts': {
                'mts_adc_target_latency': 96,
                'mts_dac_target_latency': 128,
            }
        },
        'ioc': {
            'decimation': 16
        }
    },
    'MIMO_LBL208': {
        'bitfile_name': files(overlays).joinpath('mimo_mts.bit'),
        'board': lbl208,
        'clk104_tcs': {
            'lmk_tcs': files(clk104).joinpath('LMK04828_500M_CLKin0_DIST.tcs'),
            'lmxadc_tcs': files(clk104).joinpath('LMX2594_4G.tcs'),
            'lmxdac_tcs': files(clk104).joinpath('LMX2594_4G.tcs'),
        },
        'rfdc': {
            'adc_decimation_factor': 1,
            'dac_interplation_factor': 2,
            'mixer': {
                'adc_mixer_nco_freq_mhz': 0,
                'adc_mixer_nco_nyquist': 1,
                'adc_mixer_nco_phase': 0,
                'dac_mixer_nco_freq_mhz': 0,
                'dac_mixer_nco_nyquist': 1,
                'dac_mixer_nco_phase': 0,
            },
            'mts': {
                'mts_adc_target_latency': 96,
                'mts_dac_target_latency': 128,
            }
        },
        'ioc': {
            'decimation': 16
        }
    },
    'MIMO_ZCU216': {
        'bitfile_name': files(overlays).joinpath('mimo_mts.bit'),
        'board': zcu216,
        'clk104_tcs': {
            'lmk_tcs': files(clk104).joinpath('LMK04828_500M_CLKin0.tcs'),
            'lmxadc_tcs': files(clk104).joinpath('LMX2594_2G.tcs'),
            'lmxdac_tcs': files(clk104).joinpath('LMX2594_4G.tcs'),
        },
        'rfdc': {
            'adc_decimation_factor': 1,
            'dac_interplation_factor': 2,
            'mixer': {
                'adc_mixer_nco_freq_mhz': 0,
                'adc_mixer_nco_nyquist': 1,
                'adc_mixer_nco_phase': 0,
                'dac_mixer_nco_freq_mhz': 0,
                'dac_mixer_nco_nyquist': 1,
                'dac_mixer_nco_phase': 0,
            },
            'mts': {
                'mts_adc_target_latency': 104,
                'mts_dac_target_latency': 136,
            }
        },
        'ioc': {
            'decimation': 16
        }
    },
    'ALS_LLRF_LBL208': {
        'bitfile_name': files(overlays).joinpath('als_llrf_mts.bit'),
        'board': lbl208,
        'clk104_tcs': {
            'lmk_tcs': files(clk104).joinpath('LMK04828_500M_CLKin0_DIST.tcs'),
            'lmxadc_tcs': files(clk104).joinpath('LMX2594_4G.tcs'),
            'lmxdac_tcs': files(clk104).joinpath('LMX2594_4G.tcs'),
        },
        # Enable CLK104A:
        'device_tree_segments': [files(overlays).joinpath('lmxadc.dtbo')],
        'si570_freq_mhz': 156.1375,
        'rfdc': {
            'adc_decimation_factor': 8,
            'dac_interplation_factor': 8,
            'mixer': {
                'adc_mixer_nco_freq_mhz': 3000,
                'adc_mixer_nco_nyquist': 2,
                'adc_mixer_nco_phase': 0,
                'dac_mixer_nco_freq_mhz': -3000,
                'dac_mixer_nco_nyquist': 2,
                'dac_mixer_nco_phase': 0,
            },
            'mts': {
                'mts_adc_target_latency': 96,
                'mts_dac_target_latency': 256,
            }
        },
        'ioc': {
            'decimation': 2
        }
    },
    'ALS_LLRF_ZCU208': {
        'bitfile_name': files(overlays).joinpath('als_llrf_mts.bit'),
        'board': zcu208,
        'clk104_tcs': {
            'lmk_tcs': files(clk104).joinpath('LMK04828_500M_CLKin0_DIST.tcs'),
            'lmxadc_tcs': files(clk104).joinpath('LMX2594_4G.tcs'),
            'lmxdac_tcs': files(clk104).joinpath('LMX2594_4G.tcs'),
        },
        # Enable CLK104A:
        'device_tree_segments': [files(overlays).joinpath('lmxadc.dtbo')],
        'si570_freq_mhz': 156.1375,
        'rfdc': {
            'adc_decimation_factor': 8,
            'dac_interplation_factor': 8,
            'mixer': {
                'adc_mixer_nco_freq_mhz': 3000,
                'adc_mixer_nco_phase': 0,
                'adc_mixer_nco_nyquist': 2,
                'dac_mixer_nco_freq_mhz': -3000,
                'dac_mixer_nco_nyquist': 2,
                'dac_mixer_nco_phase': 0,
            },
            'mts': {
                'mts_adc_target_latency': 96,
                'mts_dac_target_latency': 256,
            }
        },
        'ioc': {
            'decimation': 2
        }
    },
    'CONFIG_EVR_LBL208': {
        'bitfile_name': files(overlays).joinpath('config_evr.bit'),
        'board': lbl208,
        'clk104_tcs': {
            'lmk_tcs': files(clk104).joinpath('LMK04828_500M_CLKin0_DIST.tcs'),
            'lmxadc_tcs': files(clk104).joinpath('LMX2594_4G.tcs'),
            'lmxdac_tcs': files(clk104).joinpath('LMX2594_4G.tcs'),
        },
        'si570_freq_mhz': 156.1375,
    },
    'CONFIG_EVR_ZCU208': {
        'bitfile_name': files(overlays).joinpath('config_evr.bit'),
        'board': zcu208,
        'clk104_tcs': {
            'lmk_tcs': files(clk104).joinpath('LMK04828_500M_CLKin0.tcs'),
            'lmxadc_tcs': files(clk104).joinpath('LMX2594_4G.tcs'),
            'lmxdac_tcs': files(clk104).joinpath('LMX2594_4G.tcs'),
        },
        'si570_freq_mhz': 156.25,
    },
}
