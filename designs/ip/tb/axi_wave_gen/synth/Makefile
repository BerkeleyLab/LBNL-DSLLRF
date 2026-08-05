include ../../../../../dir_list.mk

VERILOG_WRAPPER = $(RTL_DIR)/axi_wave_gen.v
VERILOG_SOURCE  = $(RTL_DIR)/wave_gen.v

.PHONY: all clean

PART           ?= xczu48dr-fsvg1517-2-e
AXI_DATA_WIDTH ?= 256
OUT_DATA_WIDTH ?= 320
BANK_DEPTH     ?= 2048
GRANULE        ?= 64
READ_LATENCY   ?= 3
RAM_STYLE      ?= "ultra"

all: $(VERILOG_SOURCE) $(VERILOG_WRAPPER)
	vivado -mode batch -nojou -nolog -source synth.tcl -tclargs -part $(PART) \
	-axi_width $(AXI_DATA_WIDTH) -out_width $(OUT_DATA_WIDTH) \
	-granule $(GRANULE) -bank_depth $(BANK_DEPTH) \
	-read_latency $(READ_LATENCY) -ram_style $(RAM_STYLE) \
	-source_file $(VERILOG_SOURCE) -wrapper_file $(VERILOG_WRAPPER)

clean:
	rm -rf vivado_synth vivado*.log vivado*.jou