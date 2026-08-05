include ../../../../dir_list.mk

DUT      = axil_rf_control
COCOTB_TOPLEVEL       = $(DUT)
COCOTB_TEST_MODULES   = test_$(DUT)
VERILOG_SOURCES += $(RTL_DIR)/$(DUT).v
VERILOG_SOURCES += $(RTL_DIR)/axil_csr.v
VERILOG_SOURCES += $(BEDROCK_DIR)/dsp/trigger.v

include ../cocotb_inc.mk