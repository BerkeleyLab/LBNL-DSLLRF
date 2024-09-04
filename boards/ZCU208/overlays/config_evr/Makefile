OVERLAY?=config_evr
PROJECT_NAME= $(OVERLAY)
JOBS?       = 4
VIVADO      = vivado -mode batch -verbose

TOP_DIR     = .
SCRIPT_DIR  = ..
IP_DIR      = ../../../ip
BEDROCK_DIR = ../../../../bedrock
IP_REPOS    = $(IP_DIR)
SOURCES     = $(IP_DIR)/rtl/freq_count.v
SOURCES    += $(IP_DIR)/rtl/evr_gty_wrapper_axi.v $(IP_DIR)/rtl/evr_gty_wrapper.v
SOURCES    += $(IP_DIR)/rtl/evrgty.xci $(IP_DIR)/rtl/clk_interval_counters.v
SOURCES    += $(IP_DIR)/rtl/timing_core.v
SOURCES    += $(BEDROCK_DIR)/serial_io/EVG_EVR/tinyEVR.v $(BEDROCK_DIR)/serial_io/EVG_EVR/evr_ts_cdc.v
SOURCES    += $(BEDROCK_DIR)/dsp/data_xdomain.v $(BEDROCK_DIR)/dsp/flag_xdomain.v $(BEDROCK_DIR)/dsp/reg_tech_cdc.v
XDC         = $(TOP_DIR)/config_evr.xdc

.PHONY: all
all: $(OVERLAY).bit $(OVERLAY).hwh check_timing 
	echo "Built $(OVERLAY) successfully!";

$(PROJECT_NAME)/$(PROJECT_NAME).xpr:
	export XILINX_IP_REPO_PATH="$(IP_REPOS)" && $(VIVADO) -source $(SCRIPT_DIR)/proj.tcl -tclargs $(TOP_DIR)/$(OVERLAY).tcl $(PROJECT_NAME) $(SOURCES) $(XDC)

$(OVERLAY).bit: $(PROJECT_NAME)/$(PROJECT_NAME).xpr
	$(VIVADO) -source $(SCRIPT_DIR)/build_bitstream.tcl -tclargs $(OVERLAY) $(PROJECT_NAME) $(JOBS)

$(OVERLAY).hwh:
	$(VIVADO) -source $(SCRIPT_DIR)/handoff.tcl -tclargs $(OVERLAY) $(PROJECT_NAME)

$(OVERLAY).dtbo:
	dtc -I dts -O dtb -o $(OVERLAY).dtbo $(OVERLAY).dts -q

.PHONY: check_timing
check_timing:
	$(VIVADO) -source $(SCRIPT_DIR)/check_timing.tcl -tclargs $(OVERLAY) $(PROJECT_NAME)

.PHONY: block_design
block_design: $(PROJECT_NAME)/$(PROJECT_NAME).xpr

.PHONY: bitstream
bitstream: $(OVERLAY).bit

.PHONY: handoff
handoff: $(OVERLAY).hwh

.PHONY: clean
clean:
	rm -rf $(PROJECT_NAME) *.jou *.log .Xil *.xsa *.hwh *.bit *.dtbo
