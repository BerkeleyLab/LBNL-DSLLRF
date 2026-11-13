#!/usr/bin/env python3
"""Chassis user interface for the linac / SHB LLRF project.
Depends on py_ui_board for doing the drawing and layout.
There are 2 ways to run this

  1. On the real chassis: build_gui() is imported and gets executed when the IOC starts up
  2. On a host PC: The GUI can be simulated with fake PVs by running
     `python fp_gui.py ioc_dump.csv`
     Where the definition of the mock-PVs is taken from ioc_dump.csv.

ioc_dump.csv can be generated from a running IOC, capturing the current live values,
with the following commands typed in its interactive REPL:

    >>> from py_ui_board.epics_db import dump_csv
    >>> dump_csv("ioc_dump.csv")
"""

import argparse
import datetime
import logging
import socket

from py_ui_board import LogView, Menu, Permit, Status
from py_ui_board.gui import Gui
from py_ui_board.items import Check, ColumnBreak, Edit, Separator, Text, Value
from py_ui_board.pv import load_fake_records
from py_ui_board.sim import UiBoard

from mimo_mts.drivers.evr import EVR

log = logging.getLogger("fp_gui")

PF = "ALS_LLRF_LBL208:"


def get_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "---"


def ts_to_str(x):
    return datetime.datetime.fromtimestamp(x, datetime.timezone.utc).isoformat().replace("+00:00", "Z")


# Mockup for simulation only, because the EVR doesn't have PVs yet. Should be deleted once PVs exist
class FakeEvr:
    @property
    def evr_status(self):
        return 1

    @property
    def gt_ref_freq_mhz(self):
        return 125000000 - 100

    @property
    def gt_rx_freq_mhz(self):
        return 125000000 + 8

    @property
    def event_count(self):
        return 42

    @property
    def timestamp_valid(self):
        return False

    @property
    def rx_aligned(self):
        return True

    @property
    def timestamp(self):
        return 0x1234567887654321


def build_gui(PF="ALS_LLRF_LBL208:", evr_ip: EVR | FakeEvr | None = None):
    """Defines the Menu Items of the GUI.
    Currently the EVR class is needed because there are no EVR PVs yet."""

    if evr_ip is None:
        evr_ip = FakeEvr()

    system = Menu(
        "System",
        [
            Separator("Network"),
            Text("IP", get_ip),
            Text("Host", socket.gethostname),
            ColumnBreak(),
            Separator("IOC"),
            Value(PF + "ioc:UPTIME", "Uptime"),
            Value(PF + "ioc:STARTTOD", ""),
            Value(PF + "ioc:HEARTBEAT", "Heartbeat"),
            ColumnBreak(),
            Separator("CPU"),
            Value(PF + "ioc:IOC_CPU_LOAD", "IOC load"),
            Value(PF + "ioc:SYS_CPU_LOAD", "Sys load"),
            ColumnBreak(),
            Separator("Memory"),
            Value(PF + "ioc:MEM_FREE", "Free", fmt=lambda x: f"{x / 1024 / 1024:.0f} MB"),
            Value(PF + "ioc:MEM_USED", "Used", fmt=lambda x: f"{x / 1024 / 1024:.0f} MB"),
            Value(PF + "ioc:MEM_MAX", "Max.", fmt=lambda x: f"{x / 1024 / 1024:.0f} MB"),
            ColumnBreak(),
            Separator("Version"),
            Value(PF + "ioc:EPICS_VERS"),
        ],
        columns=2,
    )

    pmbus = Menu(
        "PMBUS",
        [
            Separator("Chassis Fans"),
            Edit(PF + "pmbus:chassis_fan_speed_1:RBV", "A", output_pv=PF + "pmbus:chassis_fan_speed_1", step=10),
            Edit(PF + "pmbus:chassis_fan_speed_2:RBV", "B", output_pv=PF + "pmbus:chassis_fan_speed_2", step=10),
            ColumnBreak(),
            Separator("12 V PSU"),
            # TODO add support for sticky bits. Use python status function?
            Status(PF + "pmbus:psu_status", "Status", ok=lambda v: v == 0),  # why can't I show the value :(
            Value(PF + "pmbus:psu_fan_speed_1", "Fan"),
            Value(PF + "pmbus:psu_iin", "I_in", prec=3),
            Value(PF + "pmbus:psu_iout", "I_out", prec=3),
            Value(PF + "pmbus:psu_pin", "P_in", prec=1),
            Value(PF + "pmbus:psu_pout", "P_out", prec=1),
            Value(PF + "pmbus:psu_temperature_1", "T_1", prec=1),
            Value(PF + "pmbus:psu_temperature_2", "T_2", prec=1),
            Value(PF + "pmbus:psu_vin", "V_in", prec=1),
            Value(PF + "pmbus:psu_vout", "V_out", prec=3),
        ],
        columns=3,
    )

    rf_control = Menu(
        "RF control",
        [
            Separator("Amplitude loop"),
            Edit(PF + "rf_control:amp_loop_setpoint", "SP", step=100),
            Value(PF + "rf_control:amp_loop_setpoint:RBV", "RBV"),
            Check(PF + "rf_control:amp_loop_enable:RBV", "Feedback", output_pv=PF + "rf_control:amp_loop_enable"),
            ColumnBreak(),
            Separator("Phase loop"),
            Edit(PF + "rf_control:phs_loop_setpoint", "SP", step=100),
            Value(PF + "rf_control:phs_loop_setpoint:RBV", "RBV"),
            Check(PF + "rf_control:phs_loop_enable:RBV", "Feedback", output_pv=PF + "rf_control:phs_loop_enable"),
            Check(PF + "rf_control:dac_enable:RBV", "DAC enable", output_pv=PF + "rf_control:dac_enable"),
            Value(PF + "rf_control:amp_loop_err:RBV", "A_ERR"),
            Value(PF + "rf_control:amp_loop_err:RBV", "P_ERR"),
            Value(PF + "rf_control:rf_status:RBV", "RF Status"),
            ColumnBreak(),
            Separator("Amp. settings"),
            Edit(PF + "rf_control:amp_loop_kp:RBV", "K_P", output_pv=PF + "rf_control:amp_loop_kp"),
            Edit(PF + "rf_control:amp_loop_ki:RBV", "K_I", output_pv=PF + "rf_control:amp_loop_ki"),
            Check(PF + "rf_control:amp_loop_reset:RBV", "Reset", output_pv=PF + "rf_control:amp_loop_reset"),
            Separator("Phase settings"),
            Edit(PF + "rf_control:phs_loop_kp:RBV", "K_P", output_pv=PF + "rf_control:phs_loop_kp"),
            Edit(PF + "rf_control:phs_loop_ki:RBV", "K_I", output_pv=PF + "rf_control:phs_loop_ki"),
            Check(PF + "rf_control:phs_loop_reset:RBV", "Reset", output_pv=PF + "rf_control:phs_loop_reset"),
        ],
        columns=3,
    )

    trigger = Menu(
        "Trigger",
        [
            Edit(
                PF + "rf_control:trig_sel:RBV",
                "Source select",
                output_pv=PF + "rf_control:trig_sel",
                enums=["Internal", "EVR", "External"],
            ),
            Edit(PF + "rf_control:trig_delay:RBV", "Delay", output_pv=PF + "rf_control:trig_delay"),
            Edit(PF + "rf_control:trig_period:RBV", "Period", output_pv=PF + "rf_control:trig_period"),
        ],
        columns=2,
    )

    evr = Menu(
        "EVR",
        [
            Value(lambda: evr_ip.event_count, "Event count"),
            Value(lambda: evr_ip.gt_ref_freq_mhz, "F_REF", egu="Hz"),
            Value(lambda: evr_ip.gt_rx_freq_mhz, "F_RX", egu="Hz"),
            Permit(lambda: evr_ip.timestamp_valid, "Timestamp valid"),
            Value(lambda: f"{evr_ip.timestamp >> 32:08x}", "Timestamp HI"),
            Value(lambda: f"{evr_ip.timestamp & 0xFFFFFFFF:08x}", "Timestamp LO"),
            Permit(lambda: evr_ip.evr_status, "GTY status"),
            Permit(lambda: evr_ip.rx_aligned, "RX aligned"),
        ],
        columns=2,
    )

    home = Menu(
        "ALS SHB LLRF",
        [
            Status(lambda: True, "System", goto=system),
            Status(lambda: True, "PMBUS", goto=pmbus),
            Status(lambda: True, "RF Control", goto=rf_control),
            Status(lambda: True, "Trigger", goto=trigger),
            Status(lambda: evr_ip.timestamp_valid, "EVR", goto=evr),
            LogView("Log Viewer"),
        ],
        columns=2,
        back=False,
        cursor_timeout=5,
    )
    return home


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument(
        "IOC_DUMP_CSV",
        help=".csv file with fake records to mock. Format: name,type,field,value",
        default="ioc_dump_CSV.csv",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    f_recs = load_fake_records(args.IOC_DUMP_CSV)
    log.info("Created %d fake records from {args.IOC_DUMP_CSV}", len(f_recs))

    home = build_gui()
    ui = UiBoard(is_legacy=True)
    Gui(ui, home, idle_timeout=60, invert_timeout=3600).run()


if __name__ == "__main__":
    main()
