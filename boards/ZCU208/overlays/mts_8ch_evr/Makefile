include ../../../../dir_list.mk

OVERLAY     = mts_8ch_evr
PROJECT_NAME= $(OVERLAY)
JOBS        = 4
VIVADO      = vivado -mode batch -verbose -nolog -nojou

SOURCES     = $(IP_DIR)/rtl/ADCRAMcapture.v $(IP_DIR)/rtl/DACRAMstreamer.v
SOURCES    += $(IP_DIR)/rtl/freq_count.v
SOURCES    += $(IP_DIR)/rtl/evr_gty_wrapper_axi.v
SOURCES    += $(IP_DIR)/rtl/evr_gty_wrapper.v
SOURCES    += $(IP_DIR)/rtl/clk_interval_counters.v
SOURCES    += $(IP_DIR)/rtl/timing_core.v
SOURCES    += $(BEDROCK_DIR)/serial_io/EVG_EVR/tinyEVR.v $(BEDROCK_DIR)/serial_io/EVG_EVR/evr_ts_cdc.v
SOURCES    += $(BEDROCK_DIR)/dsp/data_xdomain.v $(BEDROCK_DIR)/dsp/flag_xdomain.v $(BEDROCK_DIR)/dsp/reg_tech_cdc.v

XDC			= $(OVERLAY).xdc
EVR_TCL     = $(IP_DIR)/rtl/evrgty.tcl

.PHONY: all
all: $(OVERLAY).bit $(OVERLAY).hwh check_timing
	echo "Built $(OVERLAY) successfully!";

$(PROJECT_NAME)/$(PROJECT_NAME).xpr: $(OVERLAY).xdc
	XILINX_IP_REPO_PATH="$(IP_DIR)" $(VIVADO) -source $(SCRIPT_DIR)/proj.tcl -tclargs zcu208 $(PROJECT_NAME) $(OVERLAY).tcl $(EVR_TCL) $(XDC) $(SOURCES)

$(OVERLAY).bit: $(PROJECT_NAME)/$(PROJECT_NAME).xpr
	$(VIVADO) -source $(SCRIPT_DIR)/build_bitstream.tcl -tclargs $(OVERLAY) $(PROJECT_NAME) $(JOBS)

$(OVERLAY).hwh:
	$(VIVADO) -source $(SCRIPT_DIR)/handoff.tcl -tclargs $(OVERLAY) $(PROJECT_NAME)

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
	rm -rf _xilinx .Xil
	rm -f *.jou *.log *.xsa *.hwh *.bit

.PHONY: help
help:
	@echo "Available targets:"
	@echo "  all           - Build the bitstream, HWH file, and check timing"
	@echo "  block_design  - Create the block design"
	@echo "  bitstream     - Build the bitstream"
	@echo "  handoff       - Generate the HWH file"
	@echo "  check_timing  - Check the timing of the design"
	@echo "  clean         - Remove generated files"
	@echo "  clean_project - Remove generated files and the Vivado project directory"
	@echo "  help          - Display this help message"
