#!/usr/local/share/pynq-venv/bin/python
from mimo_mts.drivers.telemetry.max31785 import Max31785
from mimo_mts.drivers.telemetry.mcrps_device import McrpsDevice
from mimo_mts.ioc.base_ioc import MimoMtsIoc
from softioc import builder
from smbus2 import SMBus
import asyncio
import os


class AlsLlrfZCU208(MimoMtsIoc):
    def __init__(self, **kwargs):
        assert os.environ['BOARD'] == 'ZCU208', "This IOC is only for ZCU208 board."
        kwargs.setdefault('ol_name', 'ALS_LLRF_ZCU208')
        super().__init__(**kwargs)

    def init_rf_control(self):
        self.llrf_register_map.trig_sel = 0  # internal trigger
        self.llrf_register_map.pulse_length = 4096  # * 4ns
        self.llrf_register_map.trig_period = 250e6
        self.llrf_register_map.trig_delay = 0
        self.llrf_register_map.trig_divide = 1
        self.llrf_register_map.dac_enable = 1
        # Set 50% maximum RF amplitude
        self.llrf_register_map.amp_loop_setpoint = 32767 / self.ol.rf_control.tx_gain / 2
        self.llrf_register_map.dac_enable.pulse_enable = 1
        self.llrf_register_map.pulse_length = 100


class AlsLlrfLBL208(MimoMtsIoc):
    def __init__(
        self,
        ol_name="ALS_LLRF_LBL208",
        with_pmbus=True,
        n_fans=2,
        pulse_per_rev=2,
        pmbus_poll_delay=1.0,
        **kwargs
    ):
        '''
        when with_pmbus is True, the fan control and power supply status PVs will be added
        n_fans needs to be set to the number of chassis fans connected to the MAX31785
        pulse_per_rev is the number of tachometer pulses per revolution of the chassis fans
        pmbus_poll_delay is how long to sleep between reading the sensor values in [s]
        '''
        assert os.environ["BOARD"] == "ZCU208", "This IOC is only for LBL208 board."
        super().__init__(ol_name=ol_name, **kwargs)

        self.with_pmbus = with_pmbus
        self.n_fans = n_fans
        self.pulse_per_rev = pulse_per_rev
        self.pmbus_poll_delay = pmbus_poll_delay

    def init(self):
        super().init()

        # External fan control and power supply sensors
        if self.with_pmbus:
            self.smbus = SMBus("/dev/i2c-4")
            self.mcrps = McrpsDevice(self.smbus)
            self.max31785 = Max31785(self.smbus)

            for i in range(self.n_fans):
                self.max31785.enable_fan(
                    i, is_rpm_mode=True, pulse_per_rev=self.pulse_per_rev
                )

    def create_ioc(self):
        super().create_ioc()
        if self.with_pmbus:
            self.add_pmbus_pvs()

    def add_pmbus_pvs(self, prefix="pmbus:"):
        """
        Add all supported fan status and power-supply sensor PVs to the IOC.
        """
        # Fan speeds from MAX31785.
        # Use a 1-based index in the PV name for consistency with the psu_* PVs
        for i in range(self.n_fans):
            name = f"chassis_fan_speed_{i + 1}"
            self.pvs_in[name] = builder.aIn(
                prefix + name + ":RBV", initial_value=-1, EGU="RPM"
            )
            self.pvs_out[name] = builder.aOut(
                prefix + name,
                initial_value=-1,
                on_update_name=self.on_update_fan_speed,
                EGU="RPM",
            )

        # M-CRPS power supply sensors
        for k in self.mcrps.supported_sensors:
            self.pvs_in[k] = builder.aIn(
                f"{prefix}psu_{k.lower()}", initial_value=-1, EGU=McrpsDevice.UNITS[k]
            )

        # M-CRPS power supply status words (error flags)
        self.pvs_in["PSU_STATUS"] = builder.mbbIn(
            prefix + "psu_status",
            DESC="M-CRPS power supply status-word",
        )

    def start_ioc(self):
        super().start_ioc()
        # Telemetry is in a separate coroutine, so the update interval can be different
        if self.with_pmbus:
            asyncio.run_coroutine_threadsafe(self.pmbus_update(), self.dispatcher.loop)

    async def pmbus_update(self):
        while True:
            # Fan speeds
            for i in range(self.n_fans):
                val = self.max31785.read_fan_rpm(i)
                self.pvs_in[f"chassis_fan_speed_{i + 1}"].set(val)

            # M-CRPS sensors
            values = self.mcrps.read_all_sensors()
            for k, v in values.items():
                self.pvs_in[k].set(v)

            # M-CRPS status
            self.pvs_in["PSU_STATUS"].set(self.mcrps.read_status_word())

            await asyncio.sleep(self.pmbus_poll_delay)

    def on_update_fan_speed(self, value, pv_name):
        """called when the chassis fan-speed PV is written"""
        if value < 0 or value > 50000:
            print("Warning: Invalid fan speed.")
            return

        for i in range(self.n_fans):
            name = f"chassis_fan_speed_{i + 1}"
            if pv_name.endswith(name):
                self.max31785.set_fan_rpm(fan_id=i, value=value)

    def init_rf_control(self):
        self.llrf_register_map.trig_sel = 1  # EVR trigger
        self.llrf_register_map.pulse_length = 4096  # * 4ns
        self.llrf_register_map.trig_period = 250e6
        self.llrf_register_map.trig_delay = 0
        self.llrf_register_map.trig_divide = 1
        self.llrf_register_map.dac_enable = 1
        # Set 50% maximum RF amplitude
        self.llrf_register_map.amp_loop_setpoint = 32767 / self.ol.rf_control.tx_gain / 2
        self.llrf_register_map.dac_enable.pulse_enable = 1
        self.llrf_register_map.pulse_length = 100


class MimoZCU208(MimoMtsIoc):
    def __init__(self, **kwargs):
        assert os.environ['BOARD'] == 'ZCU208', "This IOC is only for ZCU208 board."
        kwargs.setdefault('ol_name', 'MIMO_ZCU208')
        super().__init__(**kwargs)

    def init_rf_control(self):
        super().init_rf_control()
        self.drive_ones_awg()
        # self.drive_test_awg()


class MimoLBL208(MimoMtsIoc):
    def __init__(self, **kwargs):
        assert os.environ['BOARD'] == 'ZCU208', "This IOC is only for LBL208 board."
        kwargs.setdefault('ol_name', 'MIMO_LBL208')
        super().__init__(**kwargs)


class MimoZCU216(MimoMtsIoc):
    def __init__(self, **kwargs):
        assert os.environ['BOARD'] == 'ZCU216', "This IOC is only for ZCU216 board."
        kwargs.setdefault('ol_name', 'MIMO_ZCU216')
        super().__init__(**kwargs)

    def init_rf_control(self):
        super().init_rf_control()
        self.drive_ones_awg()
        # self.drive_test_awg()


def llrf_zcu208_ioc():
    ioc = AlsLlrfZCU208()
    ioc.run_ioc()


def llrf_lbl208_ioc():
    ioc = AlsLlrfLBL208()
    ioc.run_ioc()


def mimo_zcu208_ioc():
    ioc = MimoZCU208()
    ioc.run_ioc()


def mimo_lbl208_ioc():
    ioc = MimoLBL208()
    ioc.run_ioc()


def mimo_zcu216_ioc():
    ioc = MimoZCU216()
    ioc.run_ioc()
