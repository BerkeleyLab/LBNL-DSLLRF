# Compiler and flags
IVERILOG = iverilog
IVERILOG_FLAGS = -g2012 -I. -Wall
RTL_DIR = ../../rtl
# VVP runtime
VVP = vvp

MODULE = dac_streamer
MODULE_TB = dac_streamer_tb

# Source files
SRC  = $(RTL_DIR)/$(MODULE).v $(MODULE_TB).sv
SRC += $(RTL_DIR)/adc_capture.v $(RTL_DIR)/dp_uram.v

# Output files
VVP_FILE = $(MODULE_TB).vvp
VCD_FILE = $(MODULE_TB).vcd

# Default target
all: compile run

# Compile the design and testbench
compile: $(SRC)
	$(IVERILOG) $(IVERILOG_FLAGS) -o $(VVP_FILE) $(SRC)

# Run the simulation
run: $(VVP_FILE)
	$(VVP) -N $(VVP_FILE)

# View the waveform (assumes GTKWave is installed)
view: $(VCD_FILE)
	gtkwave $(VCD_FILE)

# Clean up generated files
clean:
	rm -f $(VVP_FILE) $(VCD_FILE)

# Phony targets
.PHONY: all compile run view clean
