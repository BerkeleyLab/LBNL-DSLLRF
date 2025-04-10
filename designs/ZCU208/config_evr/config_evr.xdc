# SFPs - MGT 129 - zSFP 2
set_property PACKAGE_PIN N38        [get_ports SFP2_RX_P];  # Bank 129 - MGTYRXP0_129
set_property PACKAGE_PIN N39        [get_ports SFP2_RX_N];  # Bank 129 - MGTYRXN0_129
# set_property PACKAGE_PIN P35        [get_ports SFP2_TX_P];  # Bank 129 - MGTYTXP0_129
# set_property PACKAGE_PIN P36        [get_ports SFP2_TX_N];  # Bank 129 - MGTYTXN0_129

# GTY REF CLK from on board SI570, U48
set_property PACKAGE_PIN M32        [get_ports gty_refclk_n];  # Bank 131 - MGTREFCLK1N_131
set_property PACKAGE_PIN M31        [get_ports gty_refclk_p];  # Bank 131 - MGTREFCLK1P_131

# SYNC_IN on CLK 104 board
set_property -dict {PACKAGE_PIN AU2  IOSTANDARD  LVCMOS18} [get_ports EVR_EVENT1];

# EVR recovered clock output. To CLK104 board
# Bank 67
# set_property -dict {PACKAGE_PIN L21  IOSTANDARD LVDS} [get_ports SFP_REC_CLK_N];
# set_property -dict {PACKAGE_PIN M20  IOSTANDARD LVDS} [get_ports SFP_REC_CLK_P];

create_clock -period 6.4 -name gty_refclk [get_ports gty_refclk_p]
set_clock_groups -asynchronous -group [get_clocks -include_generated_clocks gty_refclk] \
    -group [get_clocks -of_objects [get_pins config_evr_i/zynq_ultra_ps_e_0/pl_clk0]]
