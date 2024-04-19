# A quick and dirty Makefile for testing

# A bunch of stuff copied from bedrock/build_tools/top_rules.mk
PYTHON=python3
VERILOG = iverilog$(ICARUS_SUFFIX) -Wall -Wno-macro-redefinition
VG_ALL = -DSIMULATE
V_TB = -Wno-timescale
AUTOGEN_DIR=_auto
VFLAGS = ${VFLAGS_$@} -I$(AUTOGEN_DIR)
VVP_FLAGS = ${VVP_FLAGS_$@}
VVP = vvp$(ICARUS_SUFFIX) -N

VERILOG_TB = $(VERILOG) $(VG_ALL) $(V_TB) ${VFLAGS} -o $@ $(filter %v, $^)
VERILOG_SIM = cd `dirname $@` && $(VVP) `basename $<` $(VVP_FLAGS)

%_tb: %_tb.v
	$(VERILOG_TB)

%.vcd: %_tb
	$(VERILOG_SIM) +vcd $(VCD_ARGS)

EXTRAS=../../rtl/ADCRAMcapture.v
SRC_DIR=../src

AM_SOURCES=$(SRC_DIR)/pulser_am.v \
					 $(SRC_DIR)/pulser_am_axis.v \
					 $(SRC_DIR)/cordicg_b22.v \
					 $(SRC_DIR)/cstageg.v \
					 $(SRC_DIR)/addsubg.v \
					 $(SRC_DIR)/ph_acc.v \
					 dds_config.vh \
					 cordic_ops.vh

F_CLK=5.0e8
F_DDS=2.0e6
.PHONY: dds_config.vh
dds_config.vh:
	$(PYTHON) dds.py $(F_CLK) $(F_DDS) > $@

pulser_axis_tb: pulser_axis_tb.v $(SRC_DIR)/pulser_xdomain.v $(SRC_DIR)/pulser_envelope.v $(SRC_DIR)/pulser_sq_axis.v $(AM_SOURCES) $(EXTRAS)
