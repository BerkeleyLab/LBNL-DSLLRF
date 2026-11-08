include ../../../../dir_list.mk

DUT      = axi_wave_cap
COCOTB_TOPLEVEL     = $(DUT)
COCOTB_TEST_MODULES = test_$(DUT)
VERILOG_SOURCES += $(RTL_DIR)/$(DUT).v
VERILOG_SOURCES += $(RTL_DIR)/wave_cap.v
VERILOG_SOURCES += $(RTL_DIR)/banked_mem.v
VERILOG_SOURCES += $(RTL_DIR)/axi4_mem_port.v

AXI_DATA_WIDTH ?= 256
ROW_WIDTH      ?= 320
DEPTH          ?= 2048
GRANULE        ?= 64
RAM_STYLE      ?= \"block\"

export PARAM_AXI_DATA_WIDTH := $(AXI_DATA_WIDTH)
export PARAM_ROW_WIDTH      := $(ROW_WIDTH)
export PARAM_DEPTH          := $(DEPTH)
export PARAM_GRANULE        := $(GRANULE)
export PARAM_RAM_STYLE      := $(RAM_STYLE)

include ../cocotb_inc.mk
