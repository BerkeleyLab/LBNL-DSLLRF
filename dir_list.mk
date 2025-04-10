TOP_DIR           := $(dir $(lastword $(MAKEFILE_LIST)))
DESIGNS_DIR        = $(TOP_DIR)designs
BEDROCK_DIR        = $(TOP_DIR)bedrock
SCRIPT_DIR         = $(DESIGNS_DIR)/scripts
IP_DIR             = $(DESIGNS_DIR)/ip
RTL_DIR            = $(DESIGNS_DIR)/ip/rtl
BOARD_FILES_DIR    = $(DESIGNS_DIR)/board_files