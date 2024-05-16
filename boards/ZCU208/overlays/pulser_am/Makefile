OVERLAY?=pulser_am

TOP_DIR=.
SCRIPT_DIR=..
IP_DIR=../../../ip
RTL_DIR=$(IP_DIR)/rtl
IP_REPOS=$(IP_DIR)
SOURCES=$(RTL_DIR)/ADCRAMcapture.v $(RTL_DIR)/diag_readback.v $(RTL_DIR)/freq_count.v $(RTL_DIR)/freq_count_axi.v
XDC=$(TOP_DIR)/pulser_am.xdc
PROJECT_NAME=$(OVERLAY)
JOBS?=8
VIVADO=vivado -mode batch -nojou -nolog -notrace

.PHONY: all
all: $(OVERLAY).bit $(OVERLAY).hwh check_timing 
	@echo
	@tput setaf 2 ; echo "Built $(OVERLAY) successfully!"; tput sgr0;
	@echo

$(PROJECT_NAME)/$(PROJECT_NAME).xpr:
	export XILINX_IP_REPO_PATH="$(IP_REPOS)" && $(VIVADO) -source $(SCRIPT_DIR)/proj.tcl -tclargs $(TOP_DIR)/$(OVERLAY).tcl $(PROJECT_NAME) $(SOURCES) $(XDC)

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
	rm -rf $(PROJECT_NAME) *.jou *.log .Xil *.xsa *.hwh *.bit
