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
