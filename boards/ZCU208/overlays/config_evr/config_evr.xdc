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

create_clock -period 6.4 [get_ports USER_MGT_SI570_CLK_P]
set_clock_groups -asynchronous -group [get_clocks USER_MGT_SI570_CLK_P] -group [get_clocks clk_pl_0]
set_clock_groups -asynchronous -group [get_clocks -of_objects [get_pins {config_evr_i/evr_gty_wrapper_axi_0/U0/evr_gty_wrapper/evrgty/inst/gen_gtwizard_gtye4_top.evrgty_gtwizard_gtye4_inst/gen_gtwizard_gtye4.gen_channel_container[2].gen_enabled_channel.gtye4_channel_wrapper_inst/channel_inst/gtye4_channel_gen.gen_gtye4_channel_inst[0].GTYE4_CHANNEL_PRIM_INST/RXOUTCLK}]] -group [get_clocks clk_pl_0]
