#!/bin/bash

sudo -E pip install -U pip
sudo -E pip install -U setuptools packaging

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

# Compile device-tree overlays, which can be referred to in config.py
sudo apt-get update -y
sudo apt-get install -y device-tree-compiler
make -C designs/dts install

# Update pynqmetadata to allow custom overlay drivers
# see https://discuss.pynq.io/t/how-to-bind-driver-to-rtl-in-pynq3/4890/4
# Ensure we have the same version of pynqmetadata on all targets.
sudo -E pip uninstall -y pynqmetadata
# sudo -E pip cache purge
sudo -E pip install pynqmetadata

sudo -E pip install softioc

# Install python package and notebook
# The -e makes it in editable mode for development without reinstalling the module
sudo -E pip install -e . --no-deps
# pynq-get-notebooks RFSoC-MTS -p $PYNQ_JUPYTER_NOTEBOOKS
echo "$BOARD Ready..."
