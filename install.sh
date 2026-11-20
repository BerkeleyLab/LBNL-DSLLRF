#!/bin/bash

sudo -E pip install -U pip
sudo -E pip install -U "setuptools<82" packaging  # pynq 3.0.1 imports pkg_resources (pyproject.toml)

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

# Install python package with its deployment dependencies (pyproject.toml: softioc, spidev, smbus2, ... pinned there;
# the development tools are in the "dev" extra and not installed here). Editable: edits take effect without reinstall.
sudo -E pip install -e .
# Front-panel GUI (LBL208, config "front_panel_gui"): py_ui_board is not public yet, install it by hand:
# sudo -E pip install git+ssh://git@gitlab-ssh.lbl.gov/llrf-projects/py_ui_board.git
echo "$BOARD Ready..."
