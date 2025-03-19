include ../../../../dir_list.mk

DUT      = axil_csr
TOPLEVEL = $(DUT)
MODULE   = test_$(DUT)
VERILOG_SOURCES += $(RTL_DIR)/$(DUT).v

# module parameters
export PARAM_DATA_WIDTH := 32
export PARAM_ADDR_WIDTH := 6
export PARAM_N_REGS_OUT := 7
export PARAM_N_REGS_INP := 3

include ../cocotb_inc.mk