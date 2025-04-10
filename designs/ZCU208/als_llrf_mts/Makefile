include ../../../dir_list.mk

OVERLAY  = als_llrf_mts
BOARD    = zcu208

RTL_SRC  = $(RTL_DIR)/adc_capture.v
RTL_SRC	+= $(RTL_DIR)/dac_streamer.v
RTL_SRC	+= $(RTL_DIR)/axil_rf_control.v
RTL_SRC	+= $(RTL_DIR)/axil_csr.v
RTL_SRC	+= $(RTL_DIR)/axil_evr.v
RTL_SRC += $(RTL_DIR)/evr_gt_wrapper.v
RTL_SRC += $(RTL_DIR)/timing_core.v
RTL_SRC += $(BEDROCK_DIR)/dsp/freq_count.v $(BEDROCK_DIR)/dsp/freq_gcount.v
RTL_SRC += $(BEDROCK_DIR)/serial_io/EVG_EVR/tinyEVR.v $(BEDROCK_DIR)/serial_io/EVG_EVR/evr_ts_cdc.v
RTL_SRC += $(BEDROCK_DIR)/dsp/data_xdomain.v $(BEDROCK_DIR)/dsp/flag_xdomain.v $(BEDROCK_DIR)/dsp/reg_tech_cdc.v

TCL_SRC += $(IP_DIR)/tcl/evr_gty_als.tcl

include $(SCRIPT_DIR)/common.mk
