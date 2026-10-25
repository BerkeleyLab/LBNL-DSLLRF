# EPICS Process Variables
Once the IOC is running, the PVs below are available to read or write.

## RF control PVs
TODO

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