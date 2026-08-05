include ../../../../dir_list.mk

DUT      = axis_adder
COCOTB_TOPLEVEL       = $(DUT)
COCOTB_TEST_MODULES   = test_$(DUT)
VERILOG_SOURCES      += $(RTL_DIR)/$(DUT).v

export PARAM_SAMP_DW := 16
export PARAM_SAMP_NUM := 16

include ../cocotb_inc.mk