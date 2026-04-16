# -------------- -------------- -------------- -------------- -------------- -------------- -------
# Pin Assignments -- all other pins handled by board BSP
# -------------- -------------- -------------- -------------- -------------- -------------- -------
set_property -dict {PACKAGE_PIN B10 IOSTANDARD LVDS_25}     [get_ports PL_SYSREF_clk_p];
set_property -dict {PACKAGE_PIN B8  IOSTANDARD LVDS_25}     [get_ports PL_CLK_clk_p];

# SYNC_IN on CLK 104 board (J42)
set_property -dict {PACKAGE_PIN AU2  IOSTANDARD  LVCMOS18} [get_ports TRIG_IN];

# SFPs - MGT 129 - zSFP 2
set_property PACKAGE_PIN N38        [get_ports sfp2_1x_grx_p];  # Bank 129 - MGTYRXP0_129
set_property PACKAGE_PIN N39        [get_ports sfp2_1x_grx_n];  # Bank 129 - MGTYRXN0_129

# GTY REF CLK from on board SI570, U48
set_property PACKAGE_PIN M32        [get_ports user_mgt_si570_clock_clk_n];  # Bank 131 - MGTREFCLK1N_131
set_property PACKAGE_PIN M31        [get_ports user_mgt_si570_clock_clk_p];  # Bank 131 - MGTREFCLK1P_131

# GPIO User LED
set_property -dict {PACKAGE_PIN AR19  IOSTANDARD  LVCMOS12} [get_ports GPIO_LED_0_LS];  # Bank 66, DS61

# USER I/O  (flexible frontend SPI bus)
set_property PACKAGE_PIN A9       [get_ports "DACIO_00"]; # Bank  87 VCCO - VCC1V8   - IO_L12N_AD8N_87
set_property IOSTANDARD  LVCMOS18 [get_ports "DACIO_00"]; # Bank  87 VCCO - VCC1V8   - IO_L12N_AD8N_87
set_property PACKAGE_PIN A10      [get_ports "DACIO_01"]; # Bank  87 VCCO - VCC1V8   - IO_L12P_AD8P_87
set_property IOSTANDARD  LVCMOS18 [get_ports "DACIO_01"]; # Bank  87 VCCO - VCC1V8   - IO_L12P_AD8P_87
set_property PACKAGE_PIN A6       [get_ports "DACIO_02"]; # Bank  87 VCCO - VCC1V8   - IO_L11N_AD9N_87
set_property IOSTANDARD  LVCMOS18 [get_ports "DACIO_02"]; # Bank  87 VCCO - VCC1V8   - IO_L11N_AD9N_87
set_property PACKAGE_PIN A7       [get_ports "DACIO_03"]; # Bank  87 VCCO - VCC1V8   - IO_L11P_AD9P_87
set_property IOSTANDARD  LVCMOS18 [get_ports "DACIO_03"]; # Bank  87 VCCO - VCC1V8   - IO_L11P_AD9P_87
set_property PACKAGE_PIN A5       [get_ports "DACIO_04"]; # Bank  87 VCCO - VCC1V8   - IO_L10N_AD10N_87
set_property IOSTANDARD  LVCMOS18 [get_ports "DACIO_04"]; # Bank  87 VCCO - VCC1V8   - IO_L10N_AD10N_87
set_property PACKAGE_PIN B5       [get_ports "DACIO_05"]; # Bank  87 VCCO - VCC1V8   - IO_L10P_AD10P_87
set_property IOSTANDARD  LVCMOS18 [get_ports "DACIO_05"]; # Bank  87 VCCO - VCC1V8   - IO_L10P_AD10P_87
set_property PACKAGE_PIN C5       [get_ports "DACIO_06"]; # Bank  87 VCCO - VCC1V8   - IO_L9N_AD11N_87
set_property IOSTANDARD  LVCMOS18 [get_ports "DACIO_06"]; # Bank  87 VCCO - VCC1V8   - IO_L9N_AD11N_87
set_property PACKAGE_PIN C6       [get_ports "DACIO_07"]; # Bank  87 VCCO - VCC1V8   - IO_L9P_AD11P_87
set_property IOSTANDARD  LVCMOS18 [get_ports "DACIO_07"]; # Bank  87 VCCO - VCC1V8   - IO_L9P_AD11P_87
set_property PACKAGE_PIN C10      [get_ports "DACIO_08"]; # Bank  87 VCCO - VCC1V8   - IO_L4N_AD12N_87
set_property IOSTANDARD  LVCMOS18 [get_ports "DACIO_08"]; # Bank  87 VCCO - VCC1V8   - IO_L4N_AD12N_87
set_property PACKAGE_PIN D10      [get_ports "DACIO_09"]; # Bank  87 VCCO - VCC1V8   - IO_L4P_AD12P_87
set_property IOSTANDARD  LVCMOS18 [get_ports "DACIO_09"]; # Bank  87 VCCO - VCC1V8   - IO_L4P_AD12P_87
set_property PACKAGE_PIN D6       [get_ports "DACIO_10"]; # Bank  87 VCCO - VCC1V8   - IO_L3N_AD13N_87
set_property IOSTANDARD  LVCMOS18 [get_ports "DACIO_10"]; # Bank  87 VCCO - VCC1V8   - IO_L3N_AD13N_87
set_property PACKAGE_PIN E7       [get_ports "DACIO_11"]; # Bank  87 VCCO - VCC1V8   - IO_L3P_AD13P_87
set_property IOSTANDARD  LVCMOS18 [get_ports "DACIO_11"]; # Bank  87 VCCO - VCC1V8   - IO_L3P_AD13P_87
set_property PACKAGE_PIN E8       [get_ports "DACIO_12"]; # Bank  87 VCCO - VCC1V8   - IO_L2N_AD14N_87
set_property IOSTANDARD  LVCMOS18 [get_ports "DACIO_12"]; # Bank  87 VCCO - VCC1V8   - IO_L2N_AD14N_87
set_property PACKAGE_PIN E9       [get_ports "DACIO_13"]; # Bank  87 VCCO - VCC1V8   - IO_L2P_AD14P_87
set_property IOSTANDARD  LVCMOS18 [get_ports "DACIO_13"]; # Bank  87 VCCO - VCC1V8   - IO_L2P_AD14P_87
set_property PACKAGE_PIN E6       [get_ports "DACIO_14"]; # Bank  87 VCCO - VCC1V8   - IO_L1N_AD15N_87
set_property IOSTANDARD  LVCMOS18 [get_ports "DACIO_14"]; # Bank  87 VCCO - VCC1V8   - IO_L1N_AD15N_87
set_property PACKAGE_PIN F6       [get_ports "DACIO_15"]; # Bank  87 VCCO - VCC1V8   - IO_L1P_AD15P_87
set_property IOSTANDARD  LVCMOS18 [get_ports "DACIO_15"]; # Bank  87 VCCO - VCC1V8   - IO_L1P_AD15P_87
set_property PACKAGE_PIN AP5      [get_ports "ADCIO_00"]; # Bank  84 VCCO - VCC1V8   - IO_L12N_AD0N_84
set_property IOSTANDARD  LVCMOS18 [get_ports "ADCIO_00"]; # Bank  84 VCCO - VCC1V8   - IO_L12N_AD0N_84
set_property PACKAGE_PIN AP6      [get_ports "ADCIO_01"]; # Bank  84 VCCO - VCC1V8   - IO_L12P_AD0P_84
set_property IOSTANDARD  LVCMOS18 [get_ports "ADCIO_01"]; # Bank  84 VCCO - VCC1V8   - IO_L12P_AD0P_84
set_property PACKAGE_PIN AR6      [get_ports "ADCIO_02"]; # Bank  84 VCCO - VCC1V8   - IO_L11N_AD1N_84
set_property IOSTANDARD  LVCMOS18 [get_ports "ADCIO_02"]; # Bank  84 VCCO - VCC1V8   - IO_L11N_AD1N_84
set_property PACKAGE_PIN AR7      [get_ports "ADCIO_03"]; # Bank  84 VCCO - VCC1V8   - IO_L11P_AD1P_84
set_property IOSTANDARD  LVCMOS18 [get_ports "ADCIO_03"]; # Bank  84 VCCO - VCC1V8   - IO_L11P_AD1P_84
set_property PACKAGE_PIN AV7      [get_ports "ADCIO_04"]; # Bank  84 VCCO - VCC1V8   - IO_L10N_AD2N_84
set_property IOSTANDARD  LVCMOS18 [get_ports "ADCIO_04"]; # Bank  84 VCCO - VCC1V8   - IO_L10N_AD2N_84
set_property PACKAGE_PIN AU7      [get_ports "ADCIO_05"]; # Bank  84 VCCO - VCC1V8   - IO_L10P_AD2P_84
set_property IOSTANDARD  LVCMOS18 [get_ports "ADCIO_05"]; # Bank  84 VCCO - VCC1V8   - IO_L10P_AD2P_84
set_property PACKAGE_PIN AV8      [get_ports "ADCIO_06"]; # Bank  84 VCCO - VCC1V8   - IO_L9N_AD3N_84
set_property IOSTANDARD  LVCMOS18 [get_ports "ADCIO_06"]; # Bank  84 VCCO - VCC1V8   - IO_L9N_AD3N_84
set_property PACKAGE_PIN AU8      [get_ports "ADCIO_07"]; # Bank  84 VCCO - VCC1V8   - IO_L9P_AD3P_84
set_property IOSTANDARD  LVCMOS18 [get_ports "ADCIO_07"]; # Bank  84 VCCO - VCC1V8   - IO_L9P_AD3P_84
set_property PACKAGE_PIN AT6      [get_ports "ADCIO_08"]; # Bank  84 VCCO - VCC1V8   - IO_L8N_HDGC_AD4N_84
set_property IOSTANDARD  LVCMOS18 [get_ports "ADCIO_08"]; # Bank  84 VCCO - VCC1V8   - IO_L8N_HDGC_AD4N_84
set_property PACKAGE_PIN AT7      [get_ports "ADCIO_09"]; # Bank  84 VCCO - VCC1V8   - IO_L8P_HDGC_AD4P_84
set_property IOSTANDARD  LVCMOS18 [get_ports "ADCIO_09"]; # Bank  84 VCCO - VCC1V8   - IO_L8P_HDGC_AD4P_84
set_property PACKAGE_PIN AU5      [get_ports "ADCIO_10"]; # Bank  84 VCCO - VCC1V8   - IO_L7N_HDGC_AD5N_84
set_property IOSTANDARD  LVCMOS18 [get_ports "ADCIO_10"]; # Bank  84 VCCO - VCC1V8   - IO_L7N_HDGC_AD5N_84
set_property PACKAGE_PIN AT5      [get_ports "ADCIO_11"]; # Bank  84 VCCO - VCC1V8   - IO_L7P_HDGC_AD5P_84
set_property IOSTANDARD  LVCMOS18 [get_ports "ADCIO_11"]; # Bank  84 VCCO - VCC1V8   - IO_L7P_HDGC_AD5P_84
set_property PACKAGE_PIN AW3      [get_ports "ADCIO_12"]; # Bank  84 VCCO - VCC1V8   - IO_L2N_AD10N_84
set_property IOSTANDARD  LVCMOS18 [get_ports "ADCIO_12"]; # Bank  84 VCCO - VCC1V8   - IO_L2N_AD10N_84
set_property PACKAGE_PIN AW4      [get_ports "ADCIO_13"]; # Bank  84 VCCO - VCC1V8   - IO_L2P_AD10P_84
set_property IOSTANDARD  LVCMOS18 [get_ports "ADCIO_13"]; # Bank  84 VCCO - VCC1V8   - IO_L2P_AD10P_84
set_property PACKAGE_PIN AV2      [get_ports "ADCIO_14"]; # Bank  84 VCCO - VCC1V8   - IO_L3N_AD9N_84
set_property IOSTANDARD  LVCMOS18 [get_ports "ADCIO_14"]; # Bank  84 VCCO - VCC1V8   - IO_L3N_AD9N_84
set_property PACKAGE_PIN AV3      [get_ports "ADCIO_15"]; # Bank  84 VCCO - VCC1V8   - IO_L3P_AD9P_84
set_property IOSTANDARD  LVCMOS18 [get_ports "ADCIO_15"]; # Bank  84 VCCO - VCC1V8   - IO_L3P_AD9P_84

# USER I/O  (CLK104 SPI multiplexer for readback)
set_property PACKAGE_PIN C11      [get_ports "CLK104_CLK_SPI_MUX_SEL[0]"] ;# Bank  68 VCCO - VCC1V2   - IO_T3U_N12_68
set_property IOSTANDARD  LVCMOS12 [get_ports "CLK104_CLK_SPI_MUX_SEL[0]"] ;# Bank  68 VCCO - VCC1V2   - IO_T3U_N12_68
set_property PACKAGE_PIN B12      [get_ports "CLK104_CLK_SPI_MUX_SEL[1]"] ;# Bank  68 VCCO - VCC1V2   - IO_L19N_T3L_N1_DBC_AD9N_68
set_property IOSTANDARD  POD12_DCI [get_ports "CLK104_CLK_SPI_MUX_SEL[1]"] ;# Bank  68 VCCO - VCC1V2   - IO_L19N_T3L_N1_DBC_AD9N_68


# -------------- -------------- -------------- -------------- -------------- -------------- -------
# Synthesis Guidance
# -------------- -------------- -------------- -------------- -------------- -------------- -------
set_property BLOCK_SYNTH.RETIMING 1 [get_cells als_llrf_mts_i/rfdc/*]
set_property BLOCK_SYNTH.STRATEGY {PERFORMANCE_OPTIMIZED} [get_cells als_llrf_mts_i/rfdc/*]
set_property BLOCK_SYNTH.RETIMING 1 [get_cells als_llrf_mts_i/receiver*/m*/axis_dwidth_converter_0/*]
set_property BLOCK_SYNTH.STRATEGY {PERFORMANCE_OPTIMIZED} [get_cells als_llrf_mts_i/receiver*/m*/axis_dwidth_converter_0/*]

# -------------- -------------- -------------- -------------- -------------- -------------- -------
# Timing Constraints
# -------------- -------------- -------------- -------------- -------------- -------------- -------
create_clock -period 2.000 -name PL_CLK_clk -waveform {0.000 1.000} [get_ports {PL_CLK_clk_p}]
create_clock -period 6.4 -name gt_refclk [get_ports user_mgt_si570_clock_clk_p]

set_clock_groups -asynchronous \
        -group [get_clocks -include_generated_clocks gt_refclk] \
        -group [get_clocks -of_objects [get_pins als_llrf_mts_i/zynq_ultra_ps_e_0/pl_clk0]] \
        -group [get_clocks -include_generated_clocks PL_CLK_clk]

# Input Delay for PL_SYSREF to ensure MTS requirements via PG269
set_input_delay -clock [get_clocks PL_CLK_clk] -min -add_delay 1.332 [get_ports PL_SYSREF_clk_p]
set_input_delay -clock [get_clocks PL_CLK_clk] -max -add_delay 0.782 [get_ports PL_SYSREF_clk_p]
set_property CLOCK_DEDICATED_ROUTE FALSE [get_nets als_llrf_mts_i/clocktreeMTS/IBUFDS_PL_CLK/U0/USE_IBUFDS.GEN_IBUFDS[0].IBUFDS_I/O]
set_property CLOCK_DEDICATED_ROUTE ANY_CMT_COLUMN [get_nets als_llrf_mts_i/clocktreeMTS/BUFG_PL_CLK/U0/BUFG_O[0]]

set_false_path -from [get_pins {als_llrf_mts_i/clocktreeMTS/RFegressReset/U0/ACTIVE_LOW_PR_OUT_DFF[*].*/C}]
set_false_path -from [get_ports TRIG_IN]

# -------------- -------------- -------------- -------------- -------------- -------------- -------
# Bitstream Generation
# -------------- -------------- -------------- -------------- -------------- -------------- -------
set_property BITSTREAM.GENERAL.COMPRESS TRUE [current_design]
set_property BITSTREAM.CONFIG.UNUSEDPIN PULLNONE [current_design]
set_property BITSTREAM.CONFIG.OVERTEMPSHUTDOWN ENABLE [current_design]
set_property BITSTREAM.CONFIG.USR_ACCESS TIMESTAMP [current_design]
