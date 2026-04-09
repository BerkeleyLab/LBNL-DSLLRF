from enum import Enum, IntEnum, IntFlag
import struct

from smbus2 import SMBus


def BIT(x):
    return 1 << x


# Register and bit-definitions from
# https://github.com/torvalds/linux/blob/master/drivers/hwmon/pmbus/pmbus.h
class PMBUS_REGS(IntEnum):
    PAGE = 0x00
    OPERATION = 0x01
    ON_OFF_CONFIG = 0x02
    CLEAR_FAULTS = 0x03
    PHASE = 0x04
    PAGE_PLUS_WRITE = 0x05
    PAGE_PLUS_READ = 0x06
    ZONE_CONFIG = 0x07
    ZONE_ACTIVE = 0x08

    WRITE_PROTECT = 0x10

    CAPABILITY = 0x19
    QUERY = 0x1A
    SMBALERT_MASK = 0x1B
    VOUT_MODE = 0x20
    VOUT_COMMAND = 0x21
    VOUT_TRIM = 0x22
    VOUT_CAL_OFFSET = 0x23
    VOUT_MAX = 0x24
    VOUT_MARGIN_HIGH = 0x25
    VOUT_MARGIN_LOW = 0x26
    VOUT_TRANSITION_RATE = 0x27
    VOUT_DROOP = 0x28
    VOUT_SCALE_LOOP = 0x29
    VOUT_SCALE_MONITOR = 0x2A

    COEFFICIENTS = 0x30
    POUT_MAX = 0x31

    FAN_CONFIG_12 = 0x3A
    FAN_COMMAND_1 = 0x3B
    FAN_COMMAND_2 = 0x3C
    FAN_CONFIG_34 = 0x3D
    FAN_COMMAND_3 = 0x3E
    FAN_COMMAND_4 = 0x3F

    VOUT_OV_FAULT_LIMIT = 0x40
    VOUT_OV_FAULT_RESPONSE = 0x41
    VOUT_OV_WARN_LIMIT = 0x42
    VOUT_UV_WARN_LIMIT = 0x43
    VOUT_UV_FAULT_LIMIT = 0x44
    VOUT_UV_FAULT_RESPONSE = 0x45
    IOUT_OC_FAULT_LIMIT = 0x46
    IOUT_OC_FAULT_RESPONSE = 0x47
    IOUT_OC_LV_FAULT_LIMIT = 0x48
    IOUT_OC_LV_FAULT_RESPONSE = 0x49
    IOUT_OC_WARN_LIMIT = 0x4A
    IOUT_UC_FAULT_LIMIT = 0x4B
    IOUT_UC_FAULT_RESPONSE = 0x4C

    OT_FAULT_LIMIT = 0x4F
    OT_FAULT_RESPONSE = 0x50
    OT_WARN_LIMIT = 0x51
    UT_WARN_LIMIT = 0x52
    UT_FAULT_LIMIT = 0x53
    UT_FAULT_RESPONSE = 0x54
    VIN_OV_FAULT_LIMIT = 0x55
    VIN_OV_FAULT_RESPONSE = 0x56
    VIN_OV_WARN_LIMIT = 0x57
    VIN_UV_WARN_LIMIT = 0x58
    VIN_UV_FAULT_LIMIT = 0x59

    IIN_OC_FAULT_LIMIT = 0x5B
    IIN_OC_WARN_LIMIT = 0x5D

    POUT_OP_FAULT_LIMIT = 0x68
    POUT_OP_WARN_LIMIT = 0x6A
    PIN_OP_WARN_LIMIT = 0x6B

    STATUS_BYTE = 0x78
    STATUS_WORD = 0x79
    STATUS_VOUT = 0x7A
    STATUS_IOUT = 0x7B
    STATUS_INPUT = 0x7C
    STATUS_TEMPERATURE = 0x7D
    STATUS_CML = 0x7E
    STATUS_OTHER = 0x7F
    STATUS_MFR_SPECIFIC = 0x80
    STATUS_FAN_12 = 0x81
    STATUS_FAN_34 = 0x82

    READ_VIN = 0x88
    READ_IIN = 0x89
    READ_VCAP = 0x8A
    READ_VOUT = 0x8B
    READ_IOUT = 0x8C  # Output Current in [A], averaged over 2 s
    READ_TEMPERATURE_1 = 0x8D  # Temperature in [degC]
    READ_TEMPERATURE_2 = 0x8E
    READ_TEMPERATURE_3 = 0x8F
    READ_FAN_SPEED_1 = 0x90
    READ_FAN_SPEED_2 = 0x91
    READ_FAN_SPEED_3 = 0x92
    READ_FAN_SPEED_4 = 0x93
    READ_DUTY_CYCLE = 0x94
    READ_FREQUENCY = 0x95
    READ_POUT = 0x96
    READ_PIN = 0x97  # Input Power in [W], averaged over 2 s

    REVISION = 0x98
    MFR_ID = 0x99
    MFR_MODEL = 0x9A
    MFR_REVISION = 0x9B
    MFR_LOCATION = 0x9C
    MFR_DATE = 0x9D
    MFR_SERIAL = 0x9E

    MFR_VIN_MIN = 0xA0
    MFR_VIN_MAX = 0xA1
    MFR_IIN_MAX = 0xA2
    MFR_PIN_MAX = 0xA3
    MFR_VOUT_MIN = 0xA4
    MFR_VOUT_MAX = 0xA5
    MFR_IOUT_MAX = 0xA6
    MFR_POUT_MAX = 0xA7

    IC_DEVICE_ID = 0xAD
    IC_DEVICE_REV = 0xAE

    MFR_MAX_TEMP_1 = 0xC0
    MFR_MAX_TEMP_2 = 0xC1
    MFR_MAX_TEMP_3 = 0xC2


# A bit set here means a fault or an alarm is active.
# These bits are sticky and need to be reset with clea_all()
# Bit fields are from PMBus Specification, Part II, Section 17
class STATUS_WORD(IntFlag):
    # NONE OF THE ABOVE: A fault or warning not listed in
    # bits [7:1] of STATUS_BYTE has occurred.
    NONE_ABOVE = BIT(0)
    # A communications, memory or logic fault has occurred.
    CML = BIT(1)
    # A temperature fault or warning has occurred. Refer to STATUS_TEMPERATURE
    TEMPERATURE = BIT(2)
    # An input undervoltage fault has occurred. Refer to STATUS_INPUT
    VIN_UV = BIT(3)
    # An output overcurrent fault has occurred. Refer to STATUS_IOUT
    IOUT_OC = BIT(4)
    # An output overvoltage fault has occurred
    VOUT_OV = BIT(5)
    # This bit is asserted if the unit is not providing power to the output, regardless
    # of the reason, including simply not being enabled
    OFF = BIT(6)
    # A fault was declared because the device was busy and unable to respond
    BUSY = BIT(7)
    # A fault type not given in bits [15:1] of the SATUS_WORD has been detected
    UNKNOWN = BIT(8)
    # A bit in STATUS_OTHER is set
    OTHER = BIT(9)
    # A fan or airflow fault or warning has occurred. Refer to STATUS_FANS
    FANS = BIT(10)
    # The POWER_GOOD signal, if present, is negated¹. When bit is asserted: Power is not good
    POWER_GOOD_N = BIT(11)
    # A manufacturer specific fault or warning has occurred.
    WORD_MFR = BIT(12)
    # An input voltage, input current, or input power fault or warning has occurred. Refer to STATUS_INPUT
    INPUT = BIT(13)
    # An output current or output power fault or warning has occurred. Refer to STATUS_IOUT
    IOUT_POUT = BIT(14)
    # An output voltage fault or warning has occurred. Refer to STATUS_VOUT
    VOUT = BIT(15)


class STATUS_VOUT(IntFlag):  # Also valid for STATUS_INPUT?
    VOUT_TRACKING_ERROR = BIT(0)
    TOFF_MAX_WARNING = BIT(1)
    TON_MAX_FAULT = BIT(2)
    VOUT_MAX_MIN = BIT(
        3
    )  # attempted to set output voltage above VOUT_MAX or below VOUT_MIN
    VOUT_UV_FAULT = BIT(4)
    VOUT_UV_WARNING = BIT(5)
    VOUT_OV_WARNING = BIT(6)
    VOUT_OV_FAULT = BIT(7)


class STATUS_IOUT(IntFlag):
    POUT_OP_WARNING = BIT(0)
    POUT_OP_FAULT = BIT(1)
    POWER_LIMITING = BIT(2)
    CURRENT_SHARE_FAULT = BIT(3)
    IOUT_UC_FAULT = BIT(4)
    IOUT_OC_WARNING = BIT(5)
    IOUT_OC_LV_FAULT = BIT(6)
    IOUT_OC_FAULT = BIT(7)


class STATUS_INPUT(IntFlag):
    PIN_OP_WARNING = BIT(0)
    IIN_OC_WARNING = BIT(1)
    IIN_OC_FAULT = BIT(2)
    UNIT_OFF = BIT(3)  # ... or insufficient input voltage
    VIN_UV_FAULT = BIT(4)
    VIN_UV_WARNING = BIT(5)
    VIN_OV_WARNING = BIT(6)
    VIN_OV_FAULT = BIT(7)


class STATUS_TEMPERATURE(IntFlag):
    UT_FAULT = BIT(4)
    UT_WARNING = BIT(5)
    OT_WARNING = BIT(6)
    OT_FAULT = BIT(7)


class STATUS_FAN(IntFlag):
    AIRFLOW_WARNING = BIT(0)
    AIRFLOW_FAULT = BIT(1)
    FAN2_SPEED_OVERRIDE = BIT(2)
    FAN1_SPEED_OVERRIDE = BIT(3)
    FAN2_WARNING = BIT(4)
    FAN1_WARNING = BIT(5)
    FAN2_FAULT = BIT(6)
    FAN1_FAULT = BIT(7)


# Communications, Logic, And Memory
class STATUS_CML(IntFlag):
    OTHER_MEM_LOGIC_FAULT = BIT(0)
    OTHER_COMM_FAULT = BIT(1)
    PROCESSOR_FAULT = BIT(3)
    MEMORY_FAULT = BIT(4)
    PACKET_ERROR_FAULT = BIT(5)
    INVALID_DATA_FAULT = BIT(6)
    INVALID_COMMAND_FAULT = BIT(7)


class STATUS_OTHER(IntFlag):
    FIRST_SMBALERT = BIT(0)
    OUTPUT_OR_DEV_FAULT = BIT(1)
    INPUT_B_OR_DEV_FAULT = BIT(2)
    INPUT_A_OR_DEV_FAULT = BIT(3)
    INPUT_B_FUSE_FAULT = BIT(4)
    INPUT_A_FUSE_FAULT = BIT(5)


class VOUT_MODES(Enum):
    ULINEAR16 = 0
    VID = 1
    DIRECT = 2
    FLOAT16 = 3


def linear11_to_float(word: int):
    """decode a LINEAR11 value"""
    # Extract exponent (signed 5-bit)
    exponent = (word >> 11) & 0x1F
    if exponent > 0x0F:
        exponent -= 0x20

    # Extract mantissa (signed 11-bit)
    mantissa = word & 0x7FF
    if mantissa > 0x3FF:
        mantissa -= 0x800

    return float(mantissa * (2**exponent))


def direct_to_float(word: int, m: int, b: int, R: int):
    """decode a DIRECT value"""
    return float((word * 10 ** (-R) - b) / m)


def float_to_direct(value: float, m: int, b: int, R: int):
    """encode a DIRECT value"""
    return round((m * value + b) * 10**R)


def read_coefficients(smbus, address, target_cmd, is_for_reading=1):
    """Use COEFFICIENT command to get m, b, R for decoding a DIRECT value"""
    coeff_data = smbus.block_process_call(
        address, PMBUS_REGS.COEFFICIENTS, [target_cmd, is_for_reading]
    )
    m = (coeff_data[1] << 16) | coeff_data[0]
    b = (coeff_data[3] << 16) | coeff_data[2]
    R = coeff_data[4]
    return m, b, R


def half_float_to_float(word: int):
    """decode a half-precision float value"""
    return float(struct.unpack(">e", struct.pack(">H", word))[0])


def sign_extend(value: int, bits: int):
    sign_bit = 1 << (bits - 1)
    return (value & (sign_bit - 1)) - (value & sign_bit)


class VoutDecoder:
    def __init__(self, smbus: SMBus, address: int):
        """Decode VOUT values depending on the vout_mode_value of the 0x20 register
        See Figure 7 in
        https://pmbus.org/wp-content/uploads/2022/01/PMBus-Specification-Rev-1-3-1-Part-II-20150313.pdf
        """
        self.address = address
        self.smbus = smbus
        self.coefficients: tuple[
            int, int, int
        ] | None = None  # m, b and R coefficients for DIRECT mode
        self.ulin16_factor = 1.0

        # Get the VOUT_MODE first
        vout_mode_value = smbus.read_byte_data(address, PMBUS_REGS.VOUT_MODE)
        self.mode = VOUT_MODES((vout_mode_value >> 5) & 3)
        self.is_relative = (vout_mode_value >> 7) & 1
        self.parameter = vout_mode_value & 0x1F

        # For ULINEAR16 mode we need to calculate the scaling factor
        if self.mode == VOUT_MODES.ULINEAR16:
            # in this case, parameter is a 5 bit signed integer
            self.ulin16_factor = 2 ** sign_extend(self.parameter, 5)

        # For DIRECT mode, we need to get the coefficients
        if self.mode == VOUT_MODES.DIRECT:
            self.coefficients = read_coefficients(smbus, address, PMBUS_REGS.READ_VOUT)

    def __str__(self) -> str:
        return f"{self.mode.name}, parameter: {self.parameter}, is_relative: {self.is_relative}"

    def decode(self, word) -> float:
        """decode a raw PMBUS value according to the VOUT_MODE
        returns the value as float or int
        """
        if self.mode == VOUT_MODES.ULINEAR16:
            # parameter --> N (Exponent),  value --> V (Mantissa)
            # value must be uint16
            return float(word * self.ulin16_factor)
        elif self.mode == VOUT_MODES.DIRECT:
            # value --> Y (raw ADC value)
            # Need to use COEFFICIENTS command to read m, b and R coefficients
            # value must be int16
            if self.coefficients is None:
                raise RuntimeError("m, b and R coefficients are not available")
            return direct_to_float(word, *self.coefficients)
        elif self.mode == VOUT_MODES.FLOAT16:
            # decode IEEE-754 half precision float
            return half_float_to_float(word)
        else:
            # There's also VID mode. No idea how to decode it :p
            raise NotImplementedError()
