include ../../../dir_list.mk

OVERLAY     = als_llrf_mts
BOARD       = zcu208
RTL_SRC     = $(IP_DIR)/rtl/adc_capture.v
RTL_SRC	   += $(IP_DIR)/rtl/dac_streamer.v
RTL_SRC	   += $(IP_DIR)/rtl/freq_count.v
RTL_SRC	   += $(IP_DIR)/rtl/axil_rf_control.v
RTL_SRC	   += $(IP_DIR)/rtl/axil_csr.v

RTL_SRC    += $(IP_DIR)/rtl/axil_evr_gty_wrapper.v
RTL_SRC    += $(IP_DIR)/rtl/evr_gty_wrapper.v
RTL_SRC    += $(IP_DIR)/rtl/timing_core.v
RTL_SRC    += $(BEDROCK_DIR)/serial_io/EVG_EVR/tinyEVR.v $(BEDROCK_DIR)/serial_io/EVG_EVR/evr_ts_cdc.v
RTL_SRC    += $(BEDROCK_DIR)/dsp/data_xdomain.v $(BEDROCK_DIR)/dsp/flag_xdomain.v $(BEDROCK_DIR)/dsp/reg_tech_cdc.v

TCL_SRC    += $(IP_DIR)/rtl/evrgty.tcl

include $(SCRIPT_DIR)/common.mk
