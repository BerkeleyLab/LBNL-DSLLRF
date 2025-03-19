# -------------------------------------------------------------------------------------------------
# Copyright (C) 2023 Advanced Micro Devices, Inc
# SPDX-License-Identifier: MIT
# ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- --
#!/bin/bash

# Build MTS necessary patch to xrfdc package
echo "Cloning the PYNQ repository"
git clone https://github.com/BerkeleyLab/PYNQ.git
cd PYNQ

pushd sdbuild/packages/xrfclk
. pre.sh
sudo bash qemu.sh
popd

pushd sdbuild/packages/xrfdc
. pre.sh
sudo bash qemu.sh
popd
cd ..

# Create a device-tree overlay to access PL-DRAM
sudo apt-get update -y
sudo apt-get install -y device-tree-compiler
make -C boards/dts ddr4.dtbo
cp boards/dts/ddr4.dtbo mimo_mts/

# Update pynqmetadata to allow custom overlay drivers
# This might be included in the 3.0.1 sd card build process instead
# see https://discuss.pynq.io/t/how-to-bind-driver-to-rtl-in-pynq3/4890/4
python3 -m pip uninstall -y pynqmetadata
python3 -m pip cache purge
python3 -m pip install pynqmetadata

# Install python package and notebook
# python3 -m pip install . --no-build-isolation
# pynq-get-notebooks RFSoC-MTS -p $PYNQ_JUPYTER_NOTEBOOKS
echo "$BOARD Ready..."
