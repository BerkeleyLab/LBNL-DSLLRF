include ../../../../dir_list.mk

DUT      = axis_cdc
TOPLEVEL = $(DUT)
MODULE   = test_$(DUT)
VERILOG_SOURCES += $(RTL_DIR)/$(DUT).v
VERILOG_SOURCES += $(RTL_DIR)/axis_async_fifo.v

include ../cocotb_inc.mk