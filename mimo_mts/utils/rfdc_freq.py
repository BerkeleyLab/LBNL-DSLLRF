"""
RF frequency <-> RFDC fine-mixer settings (NCO frequency and Nyquist zone), so that operators set the RF frequency
(e.g. 3000 MHz) and never the signed NCO frequency or the zone.

The RFDC Nyquist zone setting is odd/even (zones 1 and 2), so an RF frequency f must satisfy 0 <= f < Fs:
    zone = floor(f / (Fs/2)) + 1
In an even zone the spectrum is inverted, and the NCO sign flips accordingly. The DAC NCO moves baseband up to f, the
ADC NCO moves f down to baseband, so their signs are opposite:
    DAC: nco = +f (odd zone), -f (even zone)
    ADC: nco = -f (odd zone), +f (even zone)
These reproduce the settings used on hardware: the ALS carrier 3 GHz at Fs = 4 GSPS is DAC -3000 MHz, ADC +3000 MHz,
zone 2 (mimo_mts/config.py); a 125 MHz loopback at 4 GSPS is DAC +125 MHz, ADC -125 MHz, zone 1.
"""


def nyquist_zone(rf_mhz: float, fs_mhz: float) -> int:
    """Nyquist zone (1 or 2) of rf_mhz at the sampling rate fs_mhz; raises ValueError outside [0, fs_mhz)."""
    if not 0 <= rf_mhz < fs_mhz:
        raise ValueError(f"RF frequency {rf_mhz} MHz outside [0, {fs_mhz}) MHz (Nyquist zones 1 and 2)")
    return int(rf_mhz // (fs_mhz / 2)) + 1


def _sign(zone: int) -> int:
    return 1 if zone % 2 else -1


def rf_to_nco(rf_mhz: float, fs_mhz: float, converter: str) -> tuple[float, int]:
    """(NCO frequency in MHz, Nyquist zone) for an RF frequency; converter is "adc" or "dac"."""
    zone = nyquist_zone(rf_mhz, fs_mhz)
    sign = _sign(zone) if converter == "dac" else -_sign(zone)
    return sign * rf_mhz, zone


def nco_to_rf(nco_mhz: float, zone: int, converter: str) -> float:
    """RF frequency in MHz for an NCO setting (inverse of rf_to_nco; negative for a non-standard sign)."""
    sign = _sign(int(zone)) if converter == "dac" else -_sign(int(zone))
    return sign * nco_mhz


if __name__ == "__main__":
    # Self-check against the settings used on hardware
    assert rf_to_nco(3000, 4000, "dac") == (-3000, 2)
    assert rf_to_nco(3000, 4000, "adc") == (3000, 2)
    assert rf_to_nco(125, 4000, "dac") == (125, 1)
    assert rf_to_nco(125, 4000, "adc") == (-125, 1)
    assert rf_to_nco(0, 5000, "dac") == (0, 1)
    assert rf_to_nco(3000, 5000, "adc") == (3000, 2)
    for conv in ("adc", "dac"):
        for f in (0, 125, 2499.9, 2500, 2997.84, 4999):
            assert nco_to_rf(*rf_to_nco(f, 5000, conv), conv) == f
    print("rfdc_freq self-check passed")
