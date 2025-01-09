# -------------- -------------- -------------- -------------- -------------- -------------- -------
# Pin Assignments -- all other pins handled by board BSP
# -------------- -------------- -------------- -------------- -------------- -------------- -------
set_property PACKAGE_PIN B10 [get_ports PL_SYSREF_clk_p]
set_property PACKAGE_PIN B8  [get_ports PL_CLK_clk_p]
set_property PACKAGE_PIN C11 [get_ports {clk104_clk_spi_mux_sel_tri_o[0]}]
set_property PACKAGE_PIN B12 [get_ports {clk104_clk_spi_mux_sel_tri_o[1]}]

set_property IOSTANDARD LVDS_25 [get_ports PL_CLK_clk_p]
set_property IOSTANDARD LVDS_25 [get_ports PL_CLK_clk_n]
set_property IOSTANDARD LVDS_25 [get_ports PL_SYSREF_clk_p]
set_property IOSTANDARD LVDS_25 [get_ports PL_SYSREF_clk_n]
set_property IOSTANDARD LVCMOS12 [get_ports {clk104_clk_spi_mux_sel_tri_o[1]}]
set_property IOSTANDARD LVCMOS12 [get_ports {clk104_clk_spi_mux_sel_tri_o[0]}]

# SFPs - MGT 129 - zSFP 2
set_property PACKAGE_PIN N38        [get_ports SFP2_RX_P]
set_property PACKAGE_PIN N39        [get_ports SFP2_RX_N]
set_property PACKAGE_PIN P35        [get_ports SFP2_TX_P]
set_property PACKAGE_PIN P36        [get_ports SFP2_TX_N]

# USER_MGT_SI570, U48
set_property PACKAGE_PIN M32        [get_ports USER_MGT_SI570_CLK_N]
set_property PACKAGE_PIN M31        [get_ports USER_MGT_SI570_CLK_P]

set_property PACKAGE_PIN AU2        [get_ports EVR_RX_CLK]
set_property IOSTANDARD  LVCMOS18   [get_ports EVR_RX_CLK]

# EVR recovered clock output. To CLK104 board
# Bank 67
set_property PACKAGE_PIN L21  [get_ports SFP_REC_CLK_N]
set_property PACKAGE_PIN M20  [get_ports SFP_REC_CLK_P]
set_property IOSTANDARD  LVDS [get_ports SFP_REC_CLK_N]
set_property IOSTANDARD  LVDS [get_ports SFP_REC_CLK_P]

# GPIO User LED
# Bank 66
# DS61
set_property PACKAGE_PIN AR19     [get_ports GTY_RX_ALIGNED]
set_property IOSTANDARD  LVCMOS12 [get_ports GTY_RX_ALIGNED]
# DS60
set_property PACKAGE_PIN AT17     [get_ports EVR_EVENT1]
set_property IOSTANDARD  LVCMOS12 [get_ports EVR_EVENT1]

# -------------- -------------- -------------- -------------- -------------- -------------- -------
# Synthesis Guidance
# -------------- -------------- -------------- -------------- -------------- -------------- -------
set_property BLOCK_SYNTH.RETIMING 1 [get_cells mts_8ch_evr_i/ddr4_0]
set_property BLOCK_SYNTH.STRATEGY {PERFORMANCE_OPTIMIZED} [get_cells mts_8ch_evr_i/ddr4_0]
set_property MAX_FANOUT 32 [get_cells {mts_8ch_evr_i/ddr4_0/inst/u_ddr4_mem_intfc/u_ddr_mc/bgr[1].u_ddr_mc_group/txn_fifo_output_reg[*]}]
set_property MAX_FANOUT 32 [get_cells {mts_8ch_evr_i/ddr4_0/inst/u_ddr4_mem_intfc/u_ddr_mc/bgr[1].u_ddr_mc_group/cas_fifo_wptr[*]*}]
set_property LOC MMCM_X0Y2 [get_cells -hier -filter {NAME =~ */u_ddr4_infrastructure/gen_mmcme*.u_mmcme_adv_inst}]

set_property BLOCK_SYNTH.RETIMING 1 [get_cells mts_8ch_evr_i/rfdc/*]
set_property BLOCK_SYNTH.STRATEGY {PERFORMANCE_OPTIMIZED} [get_cells mts_8ch_evr_i/rfdc/*]
set_property BLOCK_SYNTH.RETIMING 1 [get_cells mts_8ch_evr_i/receiver*/chan*/axis_dwidth_converter_0/*]
set_property BLOCK_SYNTH.STRATEGY {PERFORMANCE_OPTIMIZED} [get_cells mts_8ch_evr_i/receiver*/chan*/axis_dwidth_converter_0/*]

# -------------- -------------- -------------- -------------- -------------- -------------- -------
# Timing Constraints
# -------------- -------------- -------------- -------------- -------------- -------------- -------
create_clock -period 2.000 -name PL_CLK_clk -waveform {0.000 1.000} [get_ports {PL_CLK_clk_p}]
create_clock -period 6.4 [get_ports USER_MGT_SI570_CLK_P]

set_clock_groups -asynchronous -group [get_clocks USER_MGT_SI570_CLK_P] -group [get_clocks clk_pl_0]
set_clock_groups -asynchronous -group [get_clocks -of_objects [get_pins {mts_8ch_evr_i/evr_gty_wrapper_axi_0/U0/evr_gty_wrapper/evrgty/inst/gen_gtwizard_gtye4_top.evrgty_gtwizard_gtye4_inst/gen_gtwizard_gtye4.gen_channel_container[2].gen_enabled_channel.gtye4_channel_wrapper_inst/channel_inst/gtye4_channel_gen.gen_gtye4_channel_inst[0].GTYE4_CHANNEL_PRIM_INST/RXOUTCLK}]] -group [get_clocks clk_pl_0]

# Input Delay for PL_SYSREF to ensure MTS requirements via PG269
set_input_delay -clock [get_clocks PL_CLK_clk] -min -add_delay 2.000 [get_ports PL_SYSREF_clk_p]
set_input_delay -clock [get_clocks PL_CLK_clk] -max -add_delay 2.031 [get_ports PL_SYSREF_clk_p]
set_property CLOCK_DEDICATED_ROUTE FALSE [get_nets mts_8ch_evr_i/clocktreeMTS/IBUFDS_PL_CLK/U0/USE_IBUFDS.GEN_IBUFDS[0].IBUFDS_I/O]
set_property CLOCK_DEDICATED_ROUTE ANY_CMT_COLUMN [get_nets mts_8ch_evr_i/clocktreeMTS/BUFG_PL_CLK/U0/BUFG_O[0]]

set_false_path -from [get_ports reset]
set_false_path -from [get_pins {mts_8ch_evr_i/gpio_control/axi_gpio_dac/U0/gpio_core_1/Not_Dual.gpio_Data_Out_reg[*]/C}]
set_false_path -from [get_pins {mts_8ch_evr_i/clocktreeMTS/RFegressReset/U0/ACTIVE_LOW_PR_OUT_DFF[*].*/C}]

# -------------- -------------- -------------- -------------- -------------- -------------- -------
# Debug / Chipscope
# -------------- -------------- -------------- -------------- -------------- -------------- -------
#set_property C_CLK_INPUT_FREQ_HZ 300000000 [get_debug_cores dbg_hub]
#set_property C_ENABLE_CLK_DIVIDER false [get_debug_cores dbg_hub]
#set_property C_USER_SCAN_CHAIN 1 [get_debug_cores dbg_hub]
#connect_debug_port dbg_hub/clk [get_nets clk]

# -------------- -------------- -------------- -------------- -------------- -------------- -------
# Bitstream Generation
# -------------- -------------- -------------- -------------- -------------- -------------- -------
set_property BITSTREAM.GENERAL.COMPRESS TRUE [current_design]
set_property BITSTREAM.CONFIG.UNUSEDPIN PULLNONE [current_design]
set_property BITSTREAM.CONFIG.OVERTEMPSHUTDOWN ENABLE [current_design]
set_property BITSTREAM.CONFIG.USR_ACCESS TIMESTAMP [current_design]
