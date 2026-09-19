#! /usr/bin/env python3
from pynq import DeviceTreeSegment

# LBNL specific
device_tree_segments = [
    '/boot/lmxadc.dtbo',  # CLK104A
]

for dtsb_file in device_tree_segments:
    dts = DeviceTreeSegment(str(dtsb_file))
    if dts.is_dtbo_applied():
        print(f"device-tree segment: {dts.sysfs_dir} already applied")
    else:
        print(f"Inserting device-tree segment: {dts.sysfs_dir}")
        dts.insert()
