include ../../../../dir_list.mk

DUT      = axi_wave_gen
COCOTB_TOPLEVEL     = $(DUT)
COCOTB_TEST_MODULES = test_$(DUT)
VERILOG_SOURCES += $(RTL_DIR)/$(DUT).v
VERILOG_SOURCES += $(RTL_DIR)/wave_gen.v
# COCOTB_TEST_FILTER = test_basic_write_read
# TESTCASE = test_basic_write_read
# Parameters (can be overridden from command line)
AXI_DATA_WIDTH ?= 256
OUT_DATA_WIDTH ?= 320
BANK_DEPTH     ?= 4096
GRANULE        ?= 64
RAM_STYLE      ?= \"ultra\"

# module parameters
export PARAM_AXI_DATA_WIDTH := $(AXI_DATA_WIDTH)
export PARAM_OUT_DATA_WIDTH := $(OUT_DATA_WIDTH)
export PARAM_BANK_DEPTH     := $(BANK_DEPTH)
export PARAM_GRANULE        := $(GRANULE)
export PARAM_RAM_STYLE      := $(RAM_STYLE)
export PARAM_READ_LATENCY   := 3

include ../cocotb_inc.mk