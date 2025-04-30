# SFPs - MGT 129 - zSFP 2
set_property PACKAGE_PIN N38        [get_ports sfp2_1x_grx_p];  # Bank 129 - MGTYRXP0_129
set_property PACKAGE_PIN N39        [get_ports sfp2_1x_grx_n];  # Bank 129 - MGTYRXN0_129

# GTY REF CLK from on board SI570, U48
set_property PACKAGE_PIN M32        [get_ports user_mgt_si570_clock_clk_n];  # Bank 131 - MGTREFCLK1N_131
set_property PACKAGE_PIN M31        [get_ports user_mgt_si570_clock_clk_p];  # Bank 131 - MGTREFCLK1P_131
set_property -dict {PACKAGE_PIN AR19  IOSTANDARD  LVCMOS12} [get_ports GPIO_LED_0_LS];  # Bank 66, DS61
set_property -dict {PACKAGE_PIN AT17  IOSTANDARD  LVCMOS12} [get_ports GPIO_LED_1_LS];  # Bank 66, DS60

# SYNC_IN on CLK 104 board
set_property -dict {PACKAGE_PIN AU2  IOSTANDARD  LVCMOS18} [get_ports EVR_EVENT1];

# EVR recovered clock output. To CLK104 board
# Bank 67
# set_property -dict {PACKAGE_PIN L21  IOSTANDARD LVDS} [get_ports SFP_REC_CLK_N];
# set_property -dict {PACKAGE_PIN M20  IOSTANDARD LVDS} [get_ports SFP_REC_CLK_P];

create_clock -period 6.4 -name gt_refclk [get_ports user_mgt_si570_clock_clk_p]
set_clock_groups -asynchronous -group [get_clocks -include_generated_clocks gt_refclk] \
    -group [get_clocks -of_objects [get_pins config_evr_i/zynq_ultra_ps_e_0/pl_clk0]]
