include ../../../../dir_list.mk

OVERLAY     = config_evr

PROJECT_NAME= $(OVERLAY)
JOBS?       = 4
VIVADO      = vivado -mode batch -verbose -nolog -nojou

SOURCES     = $(IP_DIR)/rtl/freq_count.v
SOURCES    += $(IP_DIR)/rtl/evr_gty_wrapper_axi.v
SOURCES    += $(IP_DIR)/rtl/evr_gty_wrapper.v
SOURCES    += $(IP_DIR)/rtl/clk_interval_counters.v
SOURCES    += $(IP_DIR)/rtl/timing_core.v
SOURCES    += $(IP_DIR)/rtl/evrgty.xci
SOURCES    += $(BEDROCK_DIR)/serial_io/EVG_EVR/tinyEVR.v $(BEDROCK_DIR)/serial_io/EVG_EVR/evr_ts_cdc.v
SOURCES    += $(BEDROCK_DIR)/dsp/data_xdomain.v $(BEDROCK_DIR)/dsp/flag_xdomain.v $(BEDROCK_DIR)/dsp/reg_tech_cdc.v
XDC         = config_evr.xdc

.PHONY: all
all: $(OVERLAY).bit $(OVERLAY).hwh check_timing
	echo "Built $(OVERLAY) successfully!";

$(PROJECT_NAME)/$(PROJECT_NAME).xpr:
	XILINX_IP_REPO_PATH="$(IP_DIR)" $(VIVADO) -source $(SCRIPT_DIR)/proj.tcl -tclargs zcu208 $(PROJECT_NAME) $(OVERLAY).tcl $(XDC) $(SOURCES)

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
	rm -rf _xilinx
	rm -f *.jou *.log .Xil *.xsa *.hwh *.bit *.dtbo
