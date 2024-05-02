#set_property PACKAGE_PIN B10 [get_ports PL_SYSREF_clk_p]

set_property PACKAGE_PIN B7       [get_ports "CLK104_PL_CLK_N"] ;# Bank  87 VCCO - VCC1V8   - IO_L7N_HDGC_87
set_property IOSTANDARD  LVDS     [get_ports "CLK104_PL_CLK_N"] ;# Bank  87 VCCO - VCC1V8   - IO_L7N_HDGC_87
set_property PACKAGE_PIN B8       [get_ports "CLK104_PL_CLK_P"] ;# Bank  87 VCCO - VCC1V8   - IO_L7P_HDGC_87
set_property IOSTANDARD  LVDS     [get_ports "CLK104_PL_CLK_P"] ;# Bank  87 VCCO - VCC1V8   - IO_L7P_HDGC_87

set_property IOSTANDARD LVDS_25 [get_ports "CLK104_PL_CLK_P"]
set_property IOSTANDARD LVDS_25 [get_ports "CLK104_PL_CLK_N"]
#set_property IOSTANDARD LVDS_25 [get_ports PL_SYSREF_clk_p]
#set_property IOSTANDARD LVDS_25 [get_ports PL_SYSREF_clk_n]

set_property PACKAGE_PIN B12      [get_ports {clk104_clk_spi_mux_sel_tri_o[1]}] ;# Bank  68 VCCO - VCC1V2   - IO_L19N_T3L_N1_DBC_AD9N_68
set_property IOSTANDARD  LVCMOS12 [get_ports {clk104_clk_spi_mux_sel_tri_o[1]}] ;# Bank  68 VCCO - VCC1V2   - IO_L19N_T3L_N1_DBC_AD9N_68
set_property PACKAGE_PIN C11      [get_ports {clk104_clk_spi_mux_sel_tri_o[0]}] ;# Bank  68 VCCO - VCC1V2   - IO_T3U_N12_68
set_property IOSTANDARD  LVCMOS12 [get_ports {clk104_clk_spi_mux_sel_tri_o[0]}] ;# Bank  68 VCCO - VCC1V2   - IO_T3U_N12_68


set_property PACKAGE_PIN AR19     [get_ports "GPIO_LED0_LS"] ;# Bank  66 VCCO - VCC1V2   - IO_L9P_T1L_N4_AD12P_66
set_property IOSTANDARD  LVCMOS12 [get_ports "GPIO_LED0_LS"] ;# Bank  66 VCCO - VCC1V2   - IO_L9P_T1L_N4_AD12P_66
#set_property PACKAGE_PIN AT17     [get_ports "GPIO_LED1_LS"] ;# Bank  66 VCCO - VCC1V2   - IO_L7N_T1L_N1_QBC_AD13N_66
#set_property IOSTANDARD  LVCMOS12 [get_ports "GPIO_LED1_LS"] ;# Bank  66 VCCO - VCC1V2   - IO_L7N_T1L_N1_QBC_AD13N_66
set_property PACKAGE_PIN AV17     [get_ports "GPIO_LED7_LS"] ;# Bank  66 VCCO - VCC1V2   - IO_L3N_T0L_N5_AD15N_66
set_property IOSTANDARD  LVCMOS12 [get_ports "GPIO_LED7_LS"] ;# Bank  66 VCCO - VCC1V2   - IO_L3N_T0L_N5_AD15N_66