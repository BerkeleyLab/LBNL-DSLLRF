# PYNQ based LLRF

## Introduction

The goal of this project is to evaluate flicker ($1/f$) noise of the RFSoC devices by correlating two ADC channel waveforms receiving the same signal.
The platform under test is [ZCU208](https://www.xilinx.com/products/boards-and-kits/zcu208.html) evaluation board with `Zynq UltraScale+ RFSoC XCZU48DR-2FSVG1517E` silicon.

## Evaluation from [RFSoC-PYNQ](https://github.com/Xilinx/RFSoC-PYNQ/)

The firmware is built following [this](https://github.com/Xilinx/RFSoC-PYNQ/blob/0b88fcb232aa73709bf03940189368e016b7633d/build_zcu208.md).
A basic loopback test was performed at $1228.8 \pm 9.6$ MHz, using $4.951$ Gsps sampling frequency, see [result](doc/01_rf_dataconverter_introduction.ipynb).