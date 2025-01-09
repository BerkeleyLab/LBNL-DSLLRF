# Create the IP core
create_ip -name gtwizard_ultrascale -vendor xilinx.com -library ip -version 1.7 -module_name evrgty

# Configure the IP core parameters
set_property -dict [list \
    CONFIG.preset {GTY-Aurora_8B10B} \
    CONFIG.CHANNEL_ENABLE {X0Y8} \
    CONFIG.TX_MASTER_CHANNEL {X0Y8} \
    CONFIG.RX_MASTER_CHANNEL {X0Y8} \
    CONFIG.TX_LINE_RATE {2.4982} \
    CONFIG.TX_REFCLK_FREQUENCY {156.1375} \
    CONFIG.TX_OUTCLK_SOURCE {TXPROGDIVCLK} \
    CONFIG.RX_LINE_RATE {2.4982} \
    CONFIG.RX_REFCLK_FREQUENCY {156.1375} \
    CONFIG.RX_BUFFER_MODE {0} \
    CONFIG.RX_JTOL_FC {1.4986203} \
    CONFIG.RX_SLIDE_MODE {PCS} \
    CONFIG.RX_CB_NUM_SEQ {0} \
    CONFIG.RX_CB_MAX_SKEW {1} \
    CONFIG.RX_CB_VAL_0_0 {00000000} \
    CONFIG.RX_CB_K_0_0 {false} \
    CONFIG.RX_CC_NUM_SEQ {0} \
    CONFIG.RX_CC_LEN_SEQ {1} \
    CONFIG.RX_CC_VAL {00000000000000000000000000000000000000000000000000000000000000000000000000000000} \
    CONFIG.RX_CC_VAL_0_0 {00000000} \
    CONFIG.RX_CC_K_0_0 {false} \
    CONFIG.RX_CC_VAL_0_1 {00000000} \
    CONFIG.RX_CC_K_0_1 {false} \
    CONFIG.ENABLE_OPTIONAL_PORTS {cplllockdetclk_in cplllocken_in cpllreset_in drpclk_in loopback_in cplllock_out rxslide_in} \
    CONFIG.RX_REFCLK_SOURCE {X0Y8 clk1+2} \
    CONFIG.TX_REFCLK_SOURCE {X0Y8 clk1+2} \
    CONFIG.LOCATE_TX_USER_CLOCKING {CORE} \
    CONFIG.LOCATE_RX_USER_CLOCKING {CORE} \
    CONFIG.TXPROGDIV_FREQ_VAL {124.91} \
    CONFIG.FREERUN_FREQUENCY {100} \
] [get_ips evrgty]

# Generate output products for the IP core
generate_target all [get_ips evrgty]
