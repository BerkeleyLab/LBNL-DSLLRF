# -------------- -------------- -------------- -------------- -------------- -------------- -------
# Pin Assignments -- all other pins handled by board BSP
# -------------- -------------- -------------- -------------- -------------- -------------- -------
set_property -dict {PACKAGE_PIN B10 IOSTANDARD LVDS_25}     [get_ports PL_SYSREF_clk_p];
set_property -dict {PACKAGE_PIN B8  IOSTANDARD LVDS_25}     [get_ports PL_CLK_clk_p];

set_property IOSTANDARD LVDS_25     [get_ports PL_CLK_clk_n];
set_property IOSTANDARD LVDS_25     [get_ports PL_SYSREF_clk_n];

# SYNC_IN on CLK 104 board (J42)
set_property -dict {PACKAGE_PIN AU2  IOSTANDARD  LVCMOS18} [get_ports TRIG_IN];

# CLK104 SPI multiplexer for readback
set_property PACKAGE_PIN C11      [get_ports "CLK104_CLK_SPI_MUX_SEL[0]"]; # Bank  68 VCCO - VCC1V2   - IO_T3U_N12_68
set_property IOSTANDARD  LVCMOS12 [get_ports "CLK104_CLK_SPI_MUX_SEL[0]"]; # Bank  68 VCCO - VCC1V2   - IO_T3U_N12_68
set_property PACKAGE_PIN B12      [get_ports "CLK104_CLK_SPI_MUX_SEL[1]"]; # Bank  68 VCCO - VCC1V2   - IO_L19N_T3L_N1_DBC_AD9N_68
set_property IOSTANDARD  LVCMOS12 [get_ports "CLK104_CLK_SPI_MUX_SEL[1]"]; # Bank  68 VCCO - VCC1V2   - IO_L19N_T3L_N1_DBC_AD9N_68

# -------------- -------------- -------------- -------------- -------------- -------------- -------
# Synthesis Guidance
# -------------- -------------- -------------- -------------- -------------- -------------- -------
set_property BLOCK_SYNTH.RETIMING 1 [get_cells mimo_mts_i/rfdc/*]
set_property BLOCK_SYNTH.STRATEGY {PERFORMANCE_OPTIMIZED} [get_cells mimo_mts_i/rfdc/*]
set_property BLOCK_SYNTH.RETIMING 1 [get_cells mimo_mts_i/receiver/m*/axis_dwidth_converter_0/*]
set_property BLOCK_SYNTH.STRATEGY {PERFORMANCE_OPTIMIZED} [get_cells mimo_mts_i/receiver/m*/axis_dwidth_converter_0/*]
set_property BLOCK_SYNTH.RETIMING 1 [get_cells mimo_mts_i/transmitter/hier_dac_play/axis_dwidth_converter_0/*]
set_property BLOCK_SYNTH.STRATEGY {PERFORMANCE_OPTIMIZED} [get_cells mimo_mts_i/transmitter/hier_dac_play/axis_dwidth_converter_0/*]

# -------------- -------------- -------------- -------------- -------------- -------------- -------
# Timing Constraints
# -------------- -------------- -------------- -------------- -------------- -------------- -------
create_clock -period 2.000 -name PL_CLK_clk -waveform {0.000 1.000} [get_ports {PL_CLK_clk_p}]

set_clock_groups -asynchronous \
        -group [get_clocks -of_objects [get_pins mimo_mts_i/zynq_ultra_ps_e_0/pl_clk0]] \
        -group [get_clocks -include_generated_clocks PL_CLK_clk]
set_false_path -from [get_ports TRIG_IN]

# Input Delay for PL_SYSREF to ensure MTS requirements via PG269
set_input_delay -clock [get_clocks PL_CLK_clk] -min -add_delay 1.332 [get_ports PL_SYSREF_clk_p]
set_input_delay -clock [get_clocks PL_CLK_clk] -max -add_delay 0.982 [get_ports PL_SYSREF_clk_p]

set_property CLOCK_DEDICATED_ROUTE FALSE [get_nets mimo_mts_i/clocktreeMTS/IBUFDS_PL_CLK/U0/USE_IBUFDS.GEN_IBUFDS[0].IBUFDS_I/O]
set_property CLOCK_DEDICATED_ROUTE ANY_CMT_COLUMN [get_nets mimo_mts_i/clocktreeMTS/BUFG_PL_CLK/U0/BUFG_O[0]]

set_false_path -from [get_pins {mimo_mts_i/clocktreeMTS/RFegressReset/U0/ACTIVE_LOW_PR_OUT_DFF[*].*/C}]

# -------------- -------------- -------------- -------------- -------------- -------------- -------
# Bitstream Generation
# -------------- -------------- -------------- -------------- -------------- -------------- -------
set_property BITSTREAM.GENERAL.COMPRESS TRUE [current_design]
set_property BITSTREAM.CONFIG.UNUSEDPIN PULLNONE [current_design]
set_property BITSTREAM.CONFIG.OVERTEMPSHUTDOWN ENABLE [current_design]
set_property BITSTREAM.CONFIG.USR_ACCESS TIMESTAMP [current_design]
