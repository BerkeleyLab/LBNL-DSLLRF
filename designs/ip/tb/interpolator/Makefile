include ../../../../dir_list.mk

DUT      = interpolator
TOPLEVEL = $(DUT)
MODULE   = test_$(DUT)
VERILOG_SOURCES += $(RTL_DIR)/$(DUT).v

# module parameters
export PARAM_SAMP_DW  := 16
export PARAM_SAMP_NUM := 8

include ../cocotb_inc.mk
