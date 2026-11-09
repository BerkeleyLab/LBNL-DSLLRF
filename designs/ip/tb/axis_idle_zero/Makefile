include ../../../../dir_list.mk

DUT      = axis_idle_zero
COCOTB_TOPLEVEL     = $(DUT)
COCOTB_TEST_MODULES = test_$(DUT)
VERILOG_SOURCES += $(RTL_DIR)/$(DUT).v

DATA_WIDTH ?= 160
export PARAM_DATA_WIDTH := $(DATA_WIDTH)

include ../cocotb_inc.mk
