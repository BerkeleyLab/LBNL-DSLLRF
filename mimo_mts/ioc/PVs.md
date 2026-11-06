# EPICS Process Variables
Once the IOC is running, the PVs below are available to read or write.

## RF control PVs
TODO

## RF-ADC calibration PVs
Available on every IOC whose overlay contains the RF Data Converter. Replace `$P` with the IOC prefix, e.g. `ALS_LLRF_LBL208`.
See `mimo_mts/drivers/adc_calibration.py` for the PG269 background.

  * `$P:adc_cal:freeze`: write 1 to freeze, 0 to resume GCB/TSCB background calibration on all ADCs.
  * `$P:adc_cal:ADC{ch}:freeze`: the same for one ADC channel.
  * `$P:adc_cal:ADC{ch}:frozen:RBV`: freeze status reported by the RFDC.
  * `$P:adc_cal:save`: write 1 to save the coefficients of all ADCs to `$P:adc_cal:file`.
  * `$P:adc_cal:restore`: write 1 to restore GCB/TSCB from `$P:adc_cal:file` and freeze them.
  * `$P:adc_cal:release_override`: write 1 to hand all calibration blocks back to the calibration engine.
  * `$P:adc_cal:file`: calibration file on the board, one per board (default `/etc/mimo_mts/adc_cal.json`, set `MIMO_MTS_ADC_CAL_FILE` to change).
  * `$P:adc_cal:status`: result of the last action.

At start, `AlsLlrfLBL208` restores and freezes the saved coefficients if the file exists; the other IOCs leave background calibration tracking.
To train: apply a CW signal at the operating frequency (above -40 dBFS, ideally near -10 dBFS) to the ADCs, unfreeze, wait for convergence, then freeze and save.

## Telemetry PVs
Telemetry PVs are only available for the AlsLlrfLBL208 platform.

Please replace the prefix `$P` with `ALS_LLRF_LBL208:pmbus`.

The PVs below are read-only and return sensor readings from the M-CRPS enabled power supply. They are listed here with their nominal values:

  * `$P:psu_vout`: power-supply DC output voltage: 12.1 V
  * `$P:psu_vin`: power-supply AC input voltage: 122.0 V
  * `$P:psu_iout`: power-supply DC output current: 2.3 A
  * `$P:psu_iin`: power-supply AC input current: 0.3 A
  * `$P:psu_pout`: power-supply output power: 28.6 W
  * `$P:psu_pin`: power-supply input power: 35.5 W
  * `$P:psu_temperature_{1,2}`: temperature within the power-supply: 24.0 °C
  * `$P:psu_fan_speed_1`: speed of the fan inside the power-supply: 4480 rpm
  * `$P:psu_status`: The 16 bit status word of the power-supply. [Bit definitions](../drivers/telemetry/pmbus.py?#L141).

There are 2 chassis fans which can be speed-controlled with the following PVs:

  * `$P:chassis_fan_speed_{1,2}:RBV`: measured speed of the 2 chassis fans in [rpm]
  * `$P:chassis_fan_speed_{1,2}`: set-point of the 2 chassis fans in [rpm]