include ../../../../dir_list.mk

DUT      = axil_evr
TOPLEVEL = $(DUT)
MODULE   = test_$(DUT)
VERILOG_SOURCES += $(RTL_DIR)/$(DUT).v
VERILOG_SOURCES += $(RTL_DIR)/axil_csr.v
VERILOG_SOURCES += $(BEDROCK_DIR)/serial_io/EVG_EVR/evr_gt_wrapper.v
VERILOG_SOURCES += $(BEDROCK_DIR)/serial_io/EVG_EVR/timing_core.v
VERILOG_SOURCES += $(BEDROCK_DIR)/serial_io/EVG_EVR/evrSROC.v
VERILOG_SOURCES += $(BEDROCK_DIR)/dsp/freq_count.v $(BEDROCK_DIR)/dsp/freq_gcount.v
VERILOG_SOURCES += $(BEDROCK_DIR)/serial_io/EVG_EVR/tinyEVR.v $(BEDROCK_DIR)/serial_io/EVG_EVR/evr_ts_cdc.v
VERILOG_SOURCES += $(BEDROCK_DIR)/dsp/data_xdomain.v $(BEDROCK_DIR)/dsp/flag_xdomain.v $(BEDROCK_DIR)/dsp/reg_tech_cdc.v

# module parameters
export PARAM_DATA_WIDTH := 32
export PARAM_ADDR_WIDTH := 8
export PARAM_FCNT_WIDTH := 8
export PARAM_GT_TYPE    := \"GT_SIM\"

include ../cocotb_inc.mk
