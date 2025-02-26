# -------------- -------------- -------------- -------------- -------------- -------------- -------
# Pin Assignments -- all other pins handled by board BSP
# -------------- -------------- -------------- -------------- -------------- -------------- -------
set_property -dict {PACKAGE_PIN B10 IOSTANDARD LVDS_25}     [get_ports PL_SYSREF_clk_p];
set_property -dict {PACKAGE_PIN B8  IOSTANDARD LVDS_25}     [get_ports PL_CLK_clk_p];
set_property -dict {PACKAGE_PIN C11 IOSTANDARD LVCMOS12}    [get_ports {clk104_clk_spi_mux_sel_tri_o[0]}];
set_property -dict {PACKAGE_PIN B12 IOSTANDARD LVCMOS12}    [get_ports {clk104_clk_spi_mux_sel_tri_o[1]}];

set_property IOSTANDARD LVDS_25     [get_ports PL_CLK_clk_n];
set_property IOSTANDARD LVDS_25     [get_ports PL_SYSREF_clk_n];

# SFPs - MGT 129 - zSFP 2
set_property PACKAGE_PIN N38        [get_ports SFP2_RX_P];  # Bank 129 - MGTYRXP0_129
set_property PACKAGE_PIN N39        [get_ports SFP2_RX_N];  # Bank 129 - MGTYRXN0_129
set_property PACKAGE_PIN P35        [get_ports SFP2_TX_P];  # Bank 129 - MGTYTXP0_129
set_property PACKAGE_PIN P36        [get_ports SFP2_TX_N];  # Bank 129 - MGTYTXN0_129

# GTY REF CLK from on board SI570, U48
set_property PACKAGE_PIN M32        [get_ports gty_refclk_n];  # Bank 131 - MGTREFCLK1N_131
set_property PACKAGE_PIN M31        [get_ports gty_refclk_p];  # Bank 131 - MGTREFCLK1P_131

# SYNC_IN on CLK 104 board
set_property -dict {PACKAGE_PIN AU2  IOSTANDARD  LVCMOS18} [get_ports EVR_EVENT1];

# EVR recovered clock output. To CLK104 board
# Bank 67
set_property -dict {PACKAGE_PIN L21  IOSTANDARD LVDS} [get_ports SFP_REC_CLK_N];
set_property -dict {PACKAGE_PIN M20  IOSTANDARD LVDS} [get_ports SFP_REC_CLK_P];

# GPIO User LED
set_property -dict {PACKAGE_PIN AR19  IOSTANDARD  LVCMOS12} [get_ports GTY_RX_ALIGNED];  # Bank 66, DS61
set_property -dict {PACKAGE_PIN AT17  IOSTANDARD  LVCMOS12} [get_ports EVR_EVENT1];      # Bank66, DS60

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
create_clock -period 2.000 -name PL_CLK_clk -waveform {0.000 1.000} [get_ports PL_CLK_clk_p]
create_clock -period 6.4 -name gty_refclk [get_ports gty_refclk_p]
set_clock_groups -asynchronous \
        -group [get_clocks -include_generated_clocks gty_refclk] \
        -group [get_clocks -of_objects [get_pins mts_8ch_evr_i/zynq_ultra_ps_e_0/pl_clk0]] \
        -group [get_clocks -include_generated_clocks PL_CLK_clk]

# Input Delay for PL_SYSREF to ensure MTS requirements via PG269
set_input_delay -clock [get_clocks PL_CLK_clk] -min -add_delay 2.000 [get_ports PL_SYSREF_clk_p]
set_input_delay -clock [get_clocks PL_CLK_clk] -max -add_delay 2.031 [get_ports PL_SYSREF_clk_p]
set_property CLOCK_DEDICATED_ROUTE FALSE [get_nets mts_8ch_evr_i/clocktreeMTS/IBUFDS_PL_CLK/U0/USE_IBUFDS.GEN_IBUFDS[0].IBUFDS_I/O]
set_property CLOCK_DEDICATED_ROUTE ANY_CMT_COLUMN [get_nets mts_8ch_evr_i/clocktreeMTS/BUFG_PL_CLK/U0/BUFG_O[0]]

set_false_path -from [get_ports reset]
set_false_path -from [get_pins {mts_8ch_evr_i/gpio_control/axi_gpio_dac/U0/gpio_core_1/Not_Dual.gpio_Data_Out_reg[*]/C}]
set_false_path -from [get_pins {mts_8ch_evr_i/clocktreeMTS/RFegressReset/U0/ACTIVE_LOW_PR_OUT_DFF[*].*/C}]

# -------------- -------------- -------------- -------------- -------------- -------------- -------
# Bitstream Generation
# -------------- -------------- -------------- -------------- -------------- -------------- -------
set_property BITSTREAM.GENERAL.COMPRESS TRUE [current_design]
set_property BITSTREAM.CONFIG.UNUSEDPIN PULLNONE [current_design]
set_property BITSTREAM.CONFIG.OVERTEMPSHUTDOWN ENABLE [current_design]
set_property BITSTREAM.CONFIG.USR_ACCESS TIMESTAMP [current_design]
