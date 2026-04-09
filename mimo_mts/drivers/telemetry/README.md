# Continued development (M. Betz)
Ongoing work to convert the bash scripts in `util/` to a Python package with good integration into `pynq_llrf`.

Goals for the MVP

  - [x] Read power supply sensor values (voltages, powers, currents, temperatures)
  - [x] Read redundant power supply status (present, operational, error-code)
  - [x] Configure the MAX31785
  - [x] Read fan-speeds
  - [x] Set fan-speeds
  - [x] Test on hardware
  - [ ] Nice to have: set fan speed to roughly stabilize temperature?

## I2C access without root
Add the following udev rule to give the xilinx user access to /dev/i2c-4

```bash
sudo vim /etc/udev/rules.d/99-i2c-permissions.rules

  # Power supply and external fan control diagnostics
  KERNEL=="i2c-4", GROUP="xilinx", MODE="0660"
```

Activate the new rule with

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Test that the I2C devices are present at 0x50, 0x53 and 0x58

```bash
i2cdetect -r -y 4

       0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
  00:                         -- -- -- -- 0c -- -- --
  10: -- -- -- -- -- -- -- -- -- -- 1a -- -- -- -- --
  20: UU -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
  30: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
  40: 40 -- -- 43 UU UU -- -- -- -- -- 4b 4c -- -- --
  50: 50 -- -- 53 -- -- -- -- 58 -- -- -- -- -- -- --
  60: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
  70: -- -- -- -- -- UU -- --
```

## Usage from the command-line
The `max31785` and `mcrps_device` CLI tools get automatically installed when the `pynq_llrf` gets installed with pip.

**MAX31785 Fan controller**

```bash
# init channel 0 and 1 in PWM mode
max31785 --init 0
max31785 --init 1

# set fan speed of both channels to 50 %
max31785 --speed 50 50

# read fan speed
max31785

    fan0 pwm_mode: 5274 rpm
    fan1 pwm_mode: 5108 rpm
    fan2 pwm_mode:    0 rpm
    fan3 pwm_mode:    0 rpm
    fan4 pwm_mode:    0 rpm
    fan5 pwm_mode:    0 rpm
```

**M-CRPS power supply**

```bash
mcrps_device

    # PSU @ 0x58
    # Status
        <STATUS_WORD.0: 0>
    # Sensors
                  VOUT:    12.166 V
                   VIN:   122.000 V
                  IOUT:     2.359 A
                   IIN:     0.348 A
                  POUT:    28.625 W
                   PIN:    35.500 W
         TEMPERATURE_1:    24.000 °C
         TEMPERATURE_2:    23.000 °C
           FAN_SPEED_1:  4480.000 rpm
```


# Power Supply and Fan Control via i2ctools (K. Penney)

## Power Supply Readback
The power supply module is M-CRPS (Modular Common Redundant Power Supply) compliant and thus PMBus compliant.
PMBus specifies the `READ_VOUT` register format as L16 (`Value = Y*2^N` where `N` is fixed on a per-device basis)
and the value of `N` is determined from the `VOUT_MODE` register.  So the conversion of this value is supposedly
device-agnostic, but it has only been tested on one module.

_Example_: read Vout
```sh
$ sudo ./ps_get_vout.sh
12.166 V
```

## Fan Control

### Configuring Fans
The AL-1826-1879 power supply adapter board has two fan connectors, labeled `J4` and `J5`.
Both connectors are 4-pin style, providing `Vcc` (12V) and `Gnd` as well as a `PWM` output and `TACH` input.

A given fan will output a particular number of tachometer (`TACH`) pulses per revolution.  The onboard
MAX31785 fan controller supports 1-4 pulses per revolution.

The fan will also probably have a preference on PWM frequency (check the datasheet).  The output
frequencies supported by the MAX31785 are: `30Hz`, `50Hz`, `100Hz`, `150Hz`, and `25kHz`.

_Example_: configure a fan connected to e.g. `J4` for `2` pulses per revolution and `25kHz` PWM frequency
```sh
$ sudo ./fan_config.sh j4 -p 2 -f 4
```

_Example_: configure a fan connected to e.g. `J5` for `4` pulses per revolution and `150Hz` PWM frequency
```sh
$ sudo ./fan_config.sh j5 -p 4 -f 3
```

### Setting Fan Speed
The above configuration step sets the fans to open-loop (PWM) control mode.  The alternative is to use
closed-loop RPM control where the `TACH` input from the fan is used as feedback to control the fan speed.

__NOTE__: This of course only works for 4-pin fans (with PWM input). 3-pin fans will run at constant full speed.

_Example_: set the speed of the fan connected to `J4` to 50%
```sh
$ sudo ./fan_set_speed.sh j4 -s 50
```

_Example_: set the speed of the fan connected to `J5` to 10%
```sh
$ sudo ./fan_set_speed.sh j5 -s 10
```

### Reading Fan Speed (RPM)
Fan speed is read in revolutions per minute (RPM) and comes from the `TACH` tachometer output from the fan itself
so make sure the fan is properly configured (see [Setting Fan Speed](#Setting Fan Speed) above).

_Example_: read the speed of the fan connected to `J5`
```sh
$ sudo ./fan_get_rpm.sh j5
2688 RPM
```
