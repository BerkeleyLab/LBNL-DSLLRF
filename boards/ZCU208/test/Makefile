overlay := mts

all: block_design bitstream check_timing handoff
	@echo
	@tput setaf 2 ; echo "Built $(overlay) successfully!"; tput sgr0;
	@echo

block_design:
	vivado -mode batch -source $(overlay).tcl -notrace

bitstream:
	vivado -mode batch -source build_bitstream.tcl -notrace -tclargs $(overlay)

check_timing:
	vivado -mode batch -source check_timing.tcl -notrace -tclargs $(overlay)

handoff:
	vivado -mode batch -source handoff.tcl -notrace -tclargs $(overlay)

clean:
	rm -rf $(overlay) *.jou *.log NA .Xil *.xsa *.hwh *.bit