#! /usr/bin/env python3
from pynq import DeviceTreeSegment
import mimo_mts.overlays as overlays
from importlib.resources import files

# LBNL specific
device_tree_segments = [
    files(overlays).joinpath('lmxadc.dtbo'),  # CLK104A
]

for dtsb_file in device_tree_segments:
    dts = DeviceTreeSegment(str(dtsb_file))
    if dts.is_dtbo_applied():
        print("Found device-tree segment:", dts.sysfs_dir)
    else:
        print("Inserting device-tree segment:", dts.sysfs_dir)
        dts.insert()
