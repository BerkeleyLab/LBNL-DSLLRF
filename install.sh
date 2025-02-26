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

# Install python package and notebook
# python3 -m pip install . --no-build-isolation
# pynq-get-notebooks RFSoC-MTS -p $PYNQ_JUPYTER_NOTEBOOKS
echo "$BOARD Ready..."
