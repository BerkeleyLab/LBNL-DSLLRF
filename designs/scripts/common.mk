VIVADO 	= vivado -mode batch -verbose -nolog -nojou

OVERLAY ?= base
JOBS    ?= 4
BOARD	?= zcu208

BD_SRC     = $(OVERLAY).tcl
OUTPUT_DIR = _xilinx
PROJECT    = $(OUTPUT_DIR)/$(OVERLAY)/$(OVERLAY).xpr

.PHONY: help
help:
	@echo "Available targets:"
	@echo "  all           - Build the overlay, and check timing"
	@echo "  block_design  - Create the block design"
	@echo "  overlay.      - Build the overlay"
	@echo "  check_timing  - Check the timing of the design"
	@echo "  clean         - Remove generated files"
	@echo "  help          - Display this help message"

.PHONY: all
all: $(OUTPUT_DIR)/$(OVERLAY).bit check_timing
	echo "Built $(OVERLAY) successfully!";

#------------------------------------------------------------------------------
# Convert space-separated list to comma-separated
# Usage: $(call to_comma_list,$(VAR))
#------------------------------------------------------------------------------
null  :=
space := $(null) $(null)
comma := ,

to_comma_list = $(subst $(space),$(comma),$(strip $(1)))

# Handle optional IP_SCRIPTS (only add argument if not empty)
ifneq ($(strip $(IP_SCRIPTS)),)
    IP_SCRIPTS_ARG := -ip_scripts "$(call to_comma_list,$(IP_SCRIPTS))"
else
    IP_SCRIPTS_ARG :=
endif

#------------------------------------------------------------------------------
# Build comma-separated argument strings
#------------------------------------------------------------------------------
RTL_FILES_ARG := $(call to_comma_list,$(RTL_SRC))
# Handle optional IP_SCRIPTS (only add argument if not empty)
ifneq ($(strip $(IP_SCRIPTS)),)
    IP_SCRIPTS_ARG := -ip_scripts "$(call to_comma_list,$(IP_SCRIPTS))"
else
    IP_SCRIPTS_ARG :=
endif

$(PROJECT): $(OVERLAY).xdc $(RTL_SRC) $(IP_SCRIPTS)
	XILINX_IP_REPO_PATH="$(IP_DIR)" XILINX_BOARD_REPO_PATH="$(BOARD_FILES_DIR)" \
	$(VIVADO) -source $(SCRIPT_DIR)/proj.tcl -tclargs \
		-board_id $(BOARD) \
		-proj_name $(OVERLAY) \
		-bd_script $(BD_SRC) \
		-proj_xdc $(OVERLAY).xdc \
		-rtl_files $(RTL_FILES_ARG) \
		$(IP_SCRIPTS_ARG) \
		-output_dir $(OUTPUT_DIR) \
		-num_jobs $(JOBS)

$(OUTPUT_DIR)/$(OVERLAY).bit: $(PROJECT)
	$(VIVADO) -source $(SCRIPT_DIR)/build_overlay.tcl -tclargs \
		-proj_name $(OVERLAY) \
		-output_dir $(OUTPUT_DIR) \
		-num_jobs $(JOBS) \
		-handoff

.PHONY: check_timing
check_timing:
	$(VIVADO) -source $(SCRIPT_DIR)/check_timing.tcl -tclargs $(OVERLAY) $(OVERLAY)

.PHONY: block_design
block_design: $(PROJECT)

.PHONY: overlay
overlay: $(OUTPUT_DIR)/$(OVERLAY).bit

.PHONY: clean
clean::
	rm -rf $(OUTPUT_DIR) .Xil