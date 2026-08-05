include ../../../../dir_list.mk

DUT      = axil_wave_gen
COCOTB_TOPLEVEL     = $(DUT)
COCOTB_TEST_MODULES = test_$(DUT)
VERILOG_SOURCES += $(RTL_DIR)/$(DUT).v
VERILOG_SOURCES += $(RTL_DIR)/wave_gen.v
# COCOTB_TEST_FILTER = test_basic_write_read
# TESTCASE = test_basic_write_read
# Parameters (can be overridden from command line)
# Note: C_S_AXI_DATA_WIDTH must be a multiple of GRANULE for wave_gen compatibility
# Address width must be large enough for control registers (0x00-0x08) + waveform memory
# Waveform memory size = BANK_DEPTH * (C_S_AXI_DATA_WIDTH/8) bytes
# For BANK_DEPTH=4096 and C_S_AXI_DATA_WIDTH=64: 4096*8 = 32KB, needs 15 bits
C_S_AXI_DATA_WIDTH ?= 64
C_S_AXI_ADDR_WIDTH ?= 18
OUT_DATA_WIDTH ?= 320
BANK_DEPTH     ?= 4096
GRANULE        ?= 64
RAM_STYLE      ?= \"ultra\"

# module parameters
export PARAM_C_S_AXI_DATA_WIDTH := $(C_S_AXI_DATA_WIDTH)
export PARAM_C_S_AXI_ADDR_WIDTH := $(C_S_AXI_ADDR_WIDTH)
export PARAM_OUT_DATA_WIDTH := $(OUT_DATA_WIDTH)
export PARAM_BANK_DEPTH     := $(BANK_DEPTH)
export PARAM_GRANULE        := $(GRANULE)
export PARAM_RAM_STYLE      := $(RAM_STYLE)
export PARAM_READ_LATENCY   := 3

include ../cocotb_inc.mk
