include ../../../../dir_list.mk

DUT      = axil_gpio
COCOTB_TOPLEVEL       = $(DUT)
COCOTB_TEST_MODULES   = test_$(DUT)
VERILOG_SOURCES += $(RTL_DIR)/$(DUT).v
VERILOG_SOURCES += $(RTL_DIR)/axil_csr.v

include ../cocotb_inc.mk