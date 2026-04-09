"""
Control and monitor fans via MAX31785.
If no arguments are given, read the speed from tachometer.
See arguments below on how to set the speed and re-initialize a fan-channel.
"""
from smbus2 import SMBus
from mimo_mts.drivers.telemetry.pmbus import PMBUS_REGS, direct_to_float, float_to_direct
import argparse


class Max31785:
    C_VOLTAGE = (1, 0, 0)
    C_TEMPERATURE = (1, 0, 2)
    C_FAN_SPEED_RPM = (1, 0, 0)
    C_FAN_SPEED_PERCENT = (1, 0, 2)
    MFR_FAN_CONFIG = 0xF1

    def __init__(self, smbus: SMBus, address: int = 0x53):
        self.address = address
        self.smbus = smbus

    def set_page(self, val: int):
        self.smbus.write_byte_data(self.address, PMBUS_REGS.PAGE, val)

    def read_fan_rpm(self, fan_id=0):
        """Read the current speed of a fan in [rpm], fan_id = 0 .. 5"""
        self.set_page(fan_id)
        word = self.smbus.read_word_data(self.address, PMBUS_REGS.READ_FAN_SPEED_1)
        return direct_to_float(word, *Max31785.C_FAN_SPEED_RPM)

    def is_rpm_mode(self, fan_id=0):
        """returns true if the channel is configured in closed-loop [rpm] mode"""
        self.set_page(fan_id)
        word = self.smbus.read_byte_data(self.address, PMBUS_REGS.FAN_CONFIG_12)
        return (word & (1 << 6)) > 0

    def disable_fan(self, fan_id=0):
        """Disables the fan-channel and sets PWM output to 0 %"""
        self.set_page(fan_id)
        self.smbus.write_byte_data(self.address, PMBUS_REGS.FAN_CONFIG_12, 0)

    def enable_fan(
        self,
        fan_id=0,
        pulse_per_rev=2,
        is_rpm_mode=False,
        ramp=3,
        tacho=True,
        tsfo=True,
        freq=3,
    ):
        """Configure a fan output channel
        fan_id: which channel, 0 - 5
        pulse_per_rev: how many tachometer pulses per revolution, 1 - 4
        is_rpm_mode: enables closed loop regulation based on tachometer pulses
            True: do closed loop regulation of RPM, use set_fan_rpm() command to set speed
            False: set speed as open-loop PWM value with set_fan_percent()
        ramp: ramping speed of PWM value, 40 % to 100 % change in x seconds:
            0: 60 s,  1: 30 s,  2: 20 s,  3: 12 s,  4: 6 s,  5: 4 s,  6: 3 s,  7: 2 s
        tacho: what to do on tacho fault,
            false: ramp to 100 %, true: don't ramp to 100 %
        tsfo: what to do if no new set_fan() value was received within 10 s or temp. sensor fault,
            false: ramp to 100 %, true: don't ramp to 100 %
        freq: PWM frequency
            0:  30 Hz,  1:  50 Hz,  2: 100 Hz,  3: 150 Hz,  7:  25 kHz
        """
        self.set_page(fan_id)

        # Write FAN_CONFIG_12
        if pulse_per_rev > 4 or pulse_per_rev < 1:
            raise ValueError("pulse_per_rev out of range")
        pulse_per_rev -= 1
        word = (1 << 7) | (is_rpm_mode << 6) | (pulse_per_rev << 4)
        self.smbus.write_byte_data(self.address, PMBUS_REGS.FAN_CONFIG_12, word)

        # Write FAN_CONFIG_MFG
        if ramp < 0 or ramp > 7:
            raise ValueError("ramp out of range")
        if freq not in (0, 1, 2, 3, 7):
            raise ValueError("freq out of range")
        word = (freq << 13) | (tsfo << 9) | (tacho << 8) | (ramp << 5)
        self.smbus.write_word_data(self.address, Max31785.MFR_FAN_CONFIG, word)

    def set_fan_percent(self, fan_id=0, value=30.0):
        """Set fan-speed in open-loop mode to `value` in [%] (0 % - 100 %)
        the channel must have been initialized with is_rpm_mode = False"""
        self.set_page(fan_id)
        word = float_to_direct(value, *Max31785.C_FAN_SPEED_PERCENT)
        self.smbus.write_word_data(self.address, PMBUS_REGS.FAN_COMMAND_1, word)

    def set_fan_rpm(self, fan_id=0, value=1000.0):
        """Set fan-speed in closed-loop mode to `value` in [rpm] (0 rpm - 32767 rpm)
        the channel must have been initialized with is_rpm_mode = True"""
        self.set_page(fan_id)
        word = float_to_direct(value, *Max31785.C_FAN_SPEED_RPM)
        self.smbus.write_word_data(self.address, PMBUS_REGS.FAN_COMMAND_1, word)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bus", default="/dev/i2c-4", help="I2C bus address (/dev/i2c-4)"
    )
    parser.add_argument(
        "--address",
        default=0x53,
        type=lambda x: int(x, 0),
        help="SMBus device address of the MAX31785 (0x53)",
    )
    parser.add_argument(
        "--speed",
        type=float,
        nargs="+",
        default=[],
        help="Space separated list of fan speeds. "
        "One for each channel. In [%%] or [rpm], depending on how the channel was initialized",
    )
    parser.add_argument(
        "--init",
        type=int,
        nargs="+",
        default=[],
        help="List of channel-ids to (re-) initialize. Everything below is ignored if not given.",
    )
    parser.add_argument(
        "--rpm-mode",
        action="store_true",
        help="Enable closed loop mode. If given, speed is defined in [rpm]",
    )
    parser.add_argument(
        "--frequency",
        type=int,
        choices=(0, 1, 2, 3, 7),
        default=3,
        help="PWM frequency: 30 Hz, 50 Hz, 100 Hz, 150 Hz, 25 kHz (100 Hz)",
    )
    parser.add_argument(
        "--ramp",
        type=int,
        choices=(0, 1, 2, 3, 4, 5, 6, 7),
        default=3,
        help="PWM Ramp speed (4)",
    )
    parser.add_argument(
        "--pulse",
        type=int,
        choices=(1, 2, 3, 4),
        default=2,
        help="Pulses per revolution (2)",
    )
    args = parser.parse_args()

    with SMBus(args.bus) as smbus:
        max31785 = Max31785(smbus, args.address)

        # Re-initialize channels
        for fan_id in args.init:
            max31785.enable_fan(
                fan_id,
                args.pulse,
                args.rpm_mode,
                args.ramp,
                False,
                True,
                args.frequency,
            )

        # Set fan speeds
        for fan_id, speed in enumerate(args.speed):
            if max31785.is_rpm_mode(fan_id):
                max31785.set_fan_rpm(fan_id, speed)
            else:
                max31785.set_fan_percent(fan_id, speed)

        # Print current RPM values
        for fan_id in range(6):
            rpm = max31785.read_fan_rpm(fan_id)
            m = "rpm_mode" if max31785.is_rpm_mode(fan_id) else "pwm_mode"
            print(f"fan{fan_id} {m}: {rpm:4.0f} rpm")


if __name__ == "__main__":
    main()
