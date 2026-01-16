include ../../../dir_list.mk

OVERLAY     = config_evr
BOARD	    = zcu208

RTL_SRC += $(RTL_DIR)/axil_evr.v
RTL_SRC += $(RTL_DIR)/axil_csr.v
RTL_SRC += $(RTL_DIR)/pulse_gen.v
RTL_SRC += $(BEDROCK_DIR)/serial_io/EVG_EVR/evr_gt_wrapper.v
RTL_SRC += $(BEDROCK_DIR)/serial_io/EVG_EVR/timing_core.v
RTL_SRC += $(BEDROCK_DIR)/serial_io/EVG_EVR/evrSROC.v
RTL_SRC += $(BEDROCK_DIR)/dsp/freq_count.v $(BEDROCK_DIR)/dsp/freq_gcount.v
RTL_SRC += $(BEDROCK_DIR)/serial_io/EVG_EVR/tinyEVR.v $(BEDROCK_DIR)/serial_io/EVG_EVR/evr_ts_cdc.v
RTL_SRC += $(BEDROCK_DIR)/dsp/data_xdomain.v $(BEDROCK_DIR)/dsp/flag_xdomain.v $(BEDROCK_DIR)/dsp/reg_tech_cdc.v

GT_SRC = $(BEDROCK_DIR)/serial_io/EVG_EVR/gt_tcl/evr_gty.tcl
REFCLK_FREQ = 156.1375

include $(SCRIPT_DIR)/common.mk
