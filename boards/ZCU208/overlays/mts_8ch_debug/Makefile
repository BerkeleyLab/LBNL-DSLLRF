include ../../../../dir_list.mk

OVERLAY     = mts_8ch_debug
PROJECT_NAME= $(OVERLAY)
JOBS        = 4
VIVADO      = vivado -mode batch -verbose -nolog -nojou

SOURCES     = $(IP_DIR)/rtl/ADCRAMcapture.v $(IP_DIR)/rtl/DACRAMstreamer.v $(IP_DIR)/rtl/diag_readback.v
XDC			= mts_8ch.xdc

.PHONY: all
all: $(OVERLAY).bit $(OVERLAY).hwh check_timing
	echo "Built $(OVERLAY) successfully!";

$(PROJECT_NAME)/$(PROJECT_NAME).xpr:
	XILINX_IP_REPO_PATH="$(IP_DIR)" $(VIVADO) -source $(SCRIPT_DIR)/proj.tcl -tclargs zcu208 $(PROJECT_NAME) $(OVERLAY).tcl $(XDC) $(SOURCES)

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
	rm -rf _xilinx
	rm -f *.jou *.log .Xil *.xsa *.hwh *.bit
