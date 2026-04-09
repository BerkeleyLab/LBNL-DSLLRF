"""A helper class to read sensor values and state from CRPS compatible power supplies"""
from smbus2 import SMBus
import argparse
from mimo_mts.drivers.telemetry.pmbus import (
    STATUS_CML,
    STATUS_FAN,
    STATUS_INPUT,
    STATUS_IOUT,
    STATUS_OTHER,
    STATUS_TEMPERATURE,
    STATUS_VOUT,
    STATUS_WORD,
    VoutDecoder,
    linear11_to_float,
    PMBUS_REGS,
)


class McrpsDevice:
    # List of all interesting sensors and their units. Not necessarily all are supported.
    UNITS = {
        "VOUT": "V",
        "VIN": "V",
        "VCAP": "V",
        "IOUT": "A",
        "IIN": "A",
        "POUT": "W",
        "PIN": "W",
        "FREQUENCY": "Hz",
        "DUTY_CYCLE": "%",
        "TEMPERATURE_1": "°C",
        "TEMPERATURE_2": "°C",
        "TEMPERATURE_3": "°C",
        "FAN_SPEED_1": "rpm",
        "FAN_SPEED_2": "rpm",
        "FAN_SPEED_3": "rpm",
        "FAN_SPEED_4": "rpm",
    }

    def __init__(self, smbus: SMBus, address=0x58):
        """Helper to query the sensors of Common Redundant Power Supplies over PMbus"""
        self.smbus = smbus
        self.address = address
        self.vout_decoder = VoutDecoder(self.smbus, address)

        # Create a list of supported sensors
        self.supported_sensors = tuple(
            filter(
                lambda n: self.query_read(PMBUS_REGS[f"READ_{n}"]),
                McrpsDevice.UNITS.keys(),
            )
        )

    def read_byte(self, command: int):
        # SMBus read 1 byte
        return self.smbus.read_byte_data(self.address, command)

    def read_word(self, command: int):
        raw = self.smbus.read_word_data(self.address, command)
        return raw

    def read_linear11(self, command: int) -> float:
        """can be used to read most sensor values
        use read_linear11(PMBUS_REGS.READ_*),
        doesn't work for VOUT, use read_vout() for that one
        """
        word = self.read_word(command)
        return linear11_to_float(word)

    def read_vout(self):
        """returns Output Voltage in [V]"""
        return self.vout_decoder.decode(self.read_word(PMBUS_REGS.READ_VOUT))

    def query_read(self, command: int) -> bool:
        """check if command is supported for reading"""
        val = self.smbus.block_process_call(self.address, PMBUS_REGS.QUERY, [command])[0]
        return (val & (1 << 5)) > 0

    def read_all_sensors(self, names: tuple[str, ...] | None = None):
        """Reads all supported sensor values and returns them as a dict.
        If not all sensor values are required, specify a list of suffixes in `names`
        """
        if names is None:
            names = self.supported_sensors
        results = {}

        for n in names:
            reg = PMBUS_REGS[f"READ_{n}"]
            word = self.read_word(reg)

            if n == "VOUT":
                val = self.vout_decoder.decode(word)
            else:
                val = linear11_to_float(word)

            results[n] = val

        return results

    def set_page(self, val: int):
        self.smbus.write_byte_data(self.address, PMBUS_REGS.PAGE, val)

    def clear_fault(self):
        """clear all fault and warning bits in all PAGEs with the CLEAR_FAULT command."""
        # Use the PAGE_PLUS_WRITE Command to do everything in one transaction without permanently changing PAGE
        # TODO doesn't, seem to work, gives INVALID_DATA_FAULT
        # self.smbus.write_block_data(
        #     self.address, PMBUS_REGS.PAGE_PLUS_WRITE, [0xFF, PMBUS_REGS.CLEAR_FAULTS]
        # )

        current_page = self.smbus.read_byte_data(self.address, PMBUS_REGS.PAGE)
        self.set_page(0xFF)
        self.smbus.write_byte(self.address, PMBUS_REGS.CLEAR_FAULTS)
        self.set_page(current_page)

    def read_status_word(self):
        """returns STATUS_WORD as python enum flags"""
        return STATUS_WORD(self.read_word(PMBUS_REGS.STATUS_WORD))

    def read_status_asserted(self):
        """returns list of all _asserted_ alerts. First element is always the STATUS_WORD"""
        all_alerts = []
        sw = self.read_status_word()
        all_alerts.append(sw)

        if STATUS_WORD.CML in sw:
            all_alerts.append(STATUS_CML(self.read_byte(PMBUS_REGS.STATUS_CML)))

        if STATUS_WORD.IOUT_OC in sw or STATUS_WORD.IOUT_POUT in sw:
            all_alerts.append(STATUS_IOUT(self.read_byte(PMBUS_REGS.STATUS_IOUT)))

        if STATUS_WORD.TEMPERATURE in sw:
            all_alerts.append(
                STATUS_TEMPERATURE(self.read_byte(PMBUS_REGS.STATUS_TEMPERATURE))
            )

        if STATUS_WORD.INPUT in sw or STATUS_WORD.VIN_UV in sw:
            all_alerts.append(STATUS_INPUT(self.read_byte(PMBUS_REGS.STATUS_INPUT)))

        if STATUS_WORD.VOUT in sw:
            all_alerts.append(STATUS_VOUT(self.read_byte(PMBUS_REGS.STATUS_VOUT)))

        if STATUS_WORD.FANS in sw:
            all_alerts.append(STATUS_FAN(self.read_byte(PMBUS_REGS.STATUS_FAN_12)))
            all_alerts.append(STATUS_FAN(self.read_byte(PMBUS_REGS.STATUS_FAN_34)))

        if STATUS_WORD.OTHER in sw:
            all_alerts.append(STATUS_OTHER(self.read_byte(PMBUS_REGS.STATUS_OTHER)))

        return all_alerts

    def __str__(self):
        s = f"# PSU @ 0x{self.address:02X}\n"
        s += "# Status\n    "
        s += "\n    ".join(repr(x) for x in self.read_status_asserted())

        vals = self.read_all_sensors()

        s += "\n# Sensors\n"
        for k, v in vals.items():
            s += f"    {k:>14s}: {v:9.3f} {McrpsDevice.UNITS[k]}\n"

        return s


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bus", default="/dev/i2c-4", help="I2C bus address (/dev/i2c-4)"
    )
    parser.add_argument(
        "--address",
        default=0x58,
        type=lambda x: int(x, 0),
        help="SMBus device address of PSU (0x58)",
    )
    parser.add_argument(
        "--pec", action="store_true", help="Enable Packet Error Checking"
    )
    parser.add_argument(
        "--clear", action="store_true", help="Clear all faults after reading them"
    )
    args = parser.parse_args()

    with SMBus(args.bus) as smbus:
        if args.pec:
            smbus.pec = 1

        psu = McrpsDevice(smbus, args.address)
        print(psu)

        if args.clear:
            print("Clearing faults")
            psu.clear_fault()


if __name__ == "__main__":
    main()
