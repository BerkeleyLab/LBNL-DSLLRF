# CLK104 SPI multiplexer for readback
set_property PACKAGE_PIN C11      [get_ports "CLK104_CLK_SPI_MUX_SEL[0]"]; # Bank  68 VCCO - VCC1V2   - IO_T3U_N12_68
set_property IOSTANDARD  LVCMOS12 [get_ports "CLK104_CLK_SPI_MUX_SEL[0]"]; # Bank  68 VCCO - VCC1V2   - IO_T3U_N12_68
set_property PACKAGE_PIN B12      [get_ports "CLK104_CLK_SPI_MUX_SEL[1]"]; # Bank  68 VCCO - VCC1V2   - IO_L19N_T3L_N1_DBC_AD9N_68
set_property IOSTANDARD  LVCMOS12 [get_ports "CLK104_CLK_SPI_MUX_SEL[1]"]; # Bank  68 VCCO - VCC1V2   - IO_L19N_T3L_N1_DBC_AD9N_68

# ui_board on PMOD 4 (J6) of FMC to PMOD adapter board. Swapped PMOD columns.
set_property PACKAGE_PIN AN15     [get_ports "ui_board_cs_n[0]"] ;# Bank  64 VCCO - VADJ_FMC - IO_L11N_T1U_N9_GC_64 - FMCP_HSPC_LA28_N
set_property IOSTANDARD  LVCMOS18 [get_ports "ui_board_cs_n[0]"] ;# Bank  64 VCCO - VADJ_FMC - IO_L11N_T1U_N9_GC_64 - FMCP_HSPC_LA28_N
set_property PACKAGE_PIN AM15     [get_ports "ui_board_int_io"] ;# Bank  64 VCCO - VADJ_FMC - IO_L11P_T1U_N8_GC_64 - FMCP_HSPC_LA28_P
set_property IOSTANDARD  LVCMOS18 [get_ports "ui_board_int_io"] ;# Bank  64 VCCO - VADJ_FMC - IO_L11P_T1U_N8_GC_64 - FMCP_HSPC_LA28_P
set_property PACKAGE_PIN AH17     [get_ports "ui_board_miso"] ;# Bank  64 VCCO - VADJ_FMC - IO_L16N_T2U_N7_QBC_AD3N_64 - FMCP_HSPC_LA30_N
set_property IOSTANDARD  LVCMOS18 [get_ports "ui_board_miso"] ;# Bank  64 VCCO - VADJ_FMC - IO_L16N_T2U_N7_QBC_AD3N_64 - FMCP_HSPC_LA30_N
set_property PACKAGE_PIN AG17     [get_ports "ui_board_cs_n[1]"] ;# Bank  64 VCCO - VADJ_FMC - IO_L16P_T2U_N6_QBC_AD3P_64 - FMCP_HSPC_LA30_P
set_property IOSTANDARD  LVCMOS18 [get_ports "ui_board_cs_n[1]"] ;# Bank  64 VCCO - VADJ_FMC - IO_L16P_T2U_N6_QBC_AD3P_64 - FMCP_HSPC_LA30_P
set_property PACKAGE_PIN AJ15     [get_ports "ui_board_mosi"] ;# Bank  64 VCCO - VADJ_FMC - IO_L15N_T2L_N5_AD11N_64 - FMCP_HSPC_LA31_N
set_property IOSTANDARD  LVCMOS18 [get_ports "ui_board_mosi"] ;# Bank  64 VCCO - VADJ_FMC - IO_L15N_T2L_N5_AD11N_64 - FMCP_HSPC_LA31_N
set_property PACKAGE_PIN AJ16     [get_ports "ui_board_res_n"] ;# Bank  64 VCCO - VADJ_FMC - IO_L15P_T2L_N4_AD11P_64 - FMCP_HSPC_LA31_P
set_property IOSTANDARD  LVCMOS18 [get_ports "ui_board_res_n"] ;# Bank  64 VCCO - VADJ_FMC - IO_L15P_T2L_N4_AD11P_64 - FMCP_HSPC_LA31_P
set_property PACKAGE_PIN AH15     [get_ports "ui_board_clk"] ;# Bank  64 VCCO - VADJ_FMC - IO_L17N_T2U_N9_AD10N_64 - FMCP_HSPC_LA33_N
set_property IOSTANDARD  LVCMOS18 [get_ports "ui_board_clk"] ;# Bank  64 VCCO - VADJ_FMC - IO_L17N_T2U_N9_AD10N_64 - FMCP_HSPC_LA33_N
set_property PACKAGE_PIN AH16     [get_ports "ui_board_d_c"] ;# Bank  64 VCCO - VADJ_FMC - IO_L17P_T2U_N8_AD10P_64 - FMCP_HSPC_LA33_P
set_property IOSTANDARD  LVCMOS18 [get_ports "ui_board_d_c"] ;# Bank  64 VCCO - VADJ_FMC - IO_L17P_T2U_N8_AD10P_64 - FMCP_HSPC_LA33_P