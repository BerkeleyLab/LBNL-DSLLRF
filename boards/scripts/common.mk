VIVADO 	= vivado -mode batch -verbose -nolog -nojou

OVERLAY ?= base
JOBS    ?= 4
BOARD	?= zcu208

TCL_SRC += $(OVERLAY).tcl
PROJECT  = _xilinx/$(OVERLAY)/$(OVERLAY).xpr

.PHONY: help
help:
	@echo "Available targets:"
	@echo "  all           - Build the bitstream, HWH file, and check timing"
	@echo "  block_design  - Create the block design"
	@echo "  bitstream     - Build the bitstream"
	@echo "  handoff       - Generate the HWH file"
	@echo "  check_timing  - Check the timing of the design"
	@echo "  clean         - Remove generated files"
	@echo "  help          - Display this help message"

.PHONY: all
all: $(OVERLAY).bit $(OVERLAY).hwh check_timing
	echo "Built $(OVERLAY) successfully!";

$(PROJECT): $(OVERLAY).xdc
	XILINX_IP_REPO_PATH="$(IP_DIR)" XILINX_BOARD_REPO_PATH="$(BOARD_FILES_DIR)" $(VIVADO) -source $(SCRIPT_DIR)/proj.tcl -tclargs \
	$(BOARD) $(OVERLAY) $(TCL_SRC) $(OVERLAY).xdc $(RTL_SRC)

$(OVERLAY).bit: $(PROJECT)
	$(VIVADO) -source $(SCRIPT_DIR)/build_bitstream.tcl -tclargs $(OVERLAY) $(OVERLAY) $(JOBS)

$(OVERLAY).hwh: $(PROJECT)
	$(VIVADO) -source $(SCRIPT_DIR)/handoff.tcl -tclargs $(OVERLAY) $(OVERLAY)

.PHONY: check_timing
check_timing:
	$(VIVADO) -source $(SCRIPT_DIR)/check_timing.tcl -tclargs $(OVERLAY) $(OVERLAY)

.PHONY: block_design
block_design: $(PROJECT)

.PHONY: bitstream
bitstream: $(OVERLAY).bit

.PHONY: handoff
handoff: $(OVERLAY).hwh

.PHONY: clean
clean:
	rm -rf _xilinx .Xil
	rm -f $(OVERLAY).xsa $(OVERLAY).hwh $(OVERLAY).bit
