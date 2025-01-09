from mimo_mts import MimoMtsOverlay
import numpy as np


def test_mimo_mts_overlay():
    ol = MimoMtsOverlay("mts_8ch.bit", lmk_freq=499.63, lmx_freq=3997.11)
    assert ol.is_loaded(), "Overlay failed to load"

    # Program DAC with a sinewave
    Fc = 250e6
    n_samples = ol.dac_player.size
    t_axis = np.arange(n_samples) / 3997.11e6
    amp = (1 << 14) - 1
    DAC_sinewave = amp * np.sin(2 * np.pi * Fc * t_axis)
    ol.dac_player[:] = np.int16(DAC_sinewave)

    # Capture ADC data
    n_samples = 1024
    for i in range(3):
        darray_i, darray_q = ol.capture_adc_iq_buf()
        x = darray_q[0, :n_samples].astype(np.float32)
        y = darray_q[3, :n_samples].astype(np.float32)
        x_corr = np.correlate(x, y, mode='full')
        lags = np.arange(-n_samples+1, n_samples)
        delay = lags[np.argmax(x_corr)]
        print(f'Iteration {i} : Cross-correlation delay = {delay} samples')
        assert delay == 0, 'Cross-correlation delay is not zero'
