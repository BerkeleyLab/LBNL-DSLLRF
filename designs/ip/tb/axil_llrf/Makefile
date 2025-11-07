include ../../../../dir_list.mk

DUT      = axil_llrf
TOPLEVEL = $(DUT)
MODULE   = test_$(DUT)
VERILOG_SOURCES += $(RTL_DIR)/$(DUT).v
VERILOG_SOURCES += $(RTL_DIR)/axil_csr.v
VERILOG_SOURCES += $(RTL_DIR)/axil_rf_control.v
VERILOG_SOURCES += $(RTL_DIR)/llrf_dsp.v $(RTL_DIR)/pi_scalar.v $(RTL_DIR)/dsp_core.v $(RTL_DIR)/pulse_gen.v
VERILOG_SOURCES += $(RTL_DIR)/interpolator.v $(RTL_DIR)/averager.v
VERILOG_SOURCES += cordicg_b22.v
VERILOG_SOURCES += $(BEDROCK_DIR)/cordic/addsubg.v $(BEDROCK_DIR)/cordic/cstageg.v
VERILOG_SOURCES += $(BEDROCK_DIR)/dsp/trigger.v
export COCOTB_RESOLVE_X = RANDOM

# module parameters
export PARAM_SAMP_DW         := 16
export PARAM_S_AXIS_SAMP_NUM := 16
export PARAM_M_AXIS_SAMP_NUM := 16

include ../cocotb_inc.mk

cordicg_b22.v: $(BEDROCK_DIR)/cordic/cordicgx.py
	python3 $< 22 $@

clean::
	rm -f cordicg_b22.v