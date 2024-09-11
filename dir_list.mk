TOP_DIR           := $(dir $(lastword $(MAKEFILE_LIST)))
DESIGNS_DIR        = $(TOP_DIR)boards
BEDROCK_DIR        = $(TOP_DIR)bedrock
SCRIPT_DIR         = $(DESIGNS_DIR)/scripts
IP_DIR             = $(DESIGNS_DIR)/ip