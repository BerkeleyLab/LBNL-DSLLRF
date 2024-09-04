// Wrapper around wizard-generated event receiver GTY block
// and tinyEVR
//
// Can't use manual or automatic bit slide to achieve framing since this
// leaves the recovered clock at a variable bit offset from the event
// generator reference clock.  Instead the transceiver is reset until it
// starts up with correct framing.  This has a 99.9% chance of happening
// within 135 attempts ((19/20)^135=0.983e-3).

module evr_gty_wrapper #(
    parameter DEBUG = "false",
    parameter DSP_EV1 = 1,
    parameter DSP_EV2 = 2
    ) (
    // GTY ports
    input              sys_clk,
    output wire [31:0] csr,
    input              reset_all,
    input              rx_slide_req,

    input              USER_MGT_SI570_CLK,
    input              RX_P, RX_N,
    output             TX_P, TX_N,
    output             gty_tx_clk,
    output wire        SFP_REC_CLK_P,
    output wire        SFP_REC_CLK_N,

    output wire        evr_clk,
    // EVR ports
    output wire [15:0] evr_evcnt,
    output wire        evr_timestamp_valid,

    input              dsp_clk,
    output wire [63:0] dsp_live_ts,
    // needs to be stretched????
    output wire        dsp_pps_marker,
    output wire        dsp_hb_marker,

    output wire        evr_event1,
    output wire        dsp_event1, // DSP_EV1
    output wire        dsp_event2  // DSP_EV2
);

localparam LOOPBACK = 3'd4; // 4 == Far end PMA loopback

// Extract status bits of interest
wire [15:0] rx_data;
wire [15:0] rxctrl0, rxctrl1;
wire  [7:0] rxctrl2, rxctrl3;
wire  [1:0] rx_charisk        = rxctrl0[1:0];
wire  [1:0] rx_disparity_error = rxctrl1[1:0];
wire  [1:0] rx_char_iscomma    = rxctrl2[1:0];
wire  [1:0] rx_notintable = rxctrl3[1:0];

//////////////////////////////////////////////////////////////////////////////
// Receiver alignment detection
// only for the rx_slide (unused for now)
(*ASYNC_REG="true"*) reg slideRequest_m = 0;
reg slideRequest_d0 = 0, slideRequest_d1 = 0;
reg rxslide = 0;
localparam FAULT_COUNTER_WIDTH = 10;
reg [FAULT_COUNTER_WIDTH-1:0] badCharCount = 0, badKcount = 0;
always @(posedge evr_clk) begin
    slideRequest_m  <= rx_slide_req;
    slideRequest_d0 <= slideRequest_m;
    slideRequest_d1 <= slideRequest_d0;
    rxslide <= slideRequest_d0 ^ slideRequest_d1;
end
reg [1:0] evr_charisk = 0, evr_char_comma = 0;
reg [15:0] evr_chars = 0;
localparam COMMAS_NEEDED = 60;
localparam COMMA_COUNTER_RELOAD = COMMAS_NEEDED - 1;
localparam COMMA_COUNTER_WIDTH = $clog2(COMMA_COUNTER_RELOAD+1) + 1;
reg [COMMA_COUNTER_WIDTH-1:0] comma_counter = COMMA_COUNTER_RELOAD;
wire evr_rx_synchronized = comma_counter[COMMA_COUNTER_WIDTH-1];
// K character can only appear on word 0
wire rx_dataErr = (rx_notintable != 0) || rx_charisk[1] || (rx_disparity_error != 0);
always @(posedge evr_clk) begin
    if (rx_dataErr) begin
        comma_counter <= COMMA_COUNTER_RELOAD;
    end
    else if (!evr_rx_synchronized && rx_charisk[0] && (rx_data[7:0] == 8'hBC)) begin
        comma_counter <= comma_counter - 1;
    end
end

always @(posedge evr_clk) begin
    if (evr_rx_synchronized && !rx_dataErr) begin
        evr_chars <= rx_data;
        evr_charisk <= rx_charisk[1:0];
        evr_char_comma <= rx_char_iscomma[1:0];
    end
    else begin
        evr_chars <= 0;
        evr_charisk <= 0;
        evr_char_comma <= 0;
    end
end

always @(posedge evr_clk) begin
    if (evr_rx_synchronized) begin
        if (rx_notintable != 0) badCharCount <= badCharCount + 1;
        if (rx_charisk[1]) badKcount <= badKcount + 1;
    end
end

// Status register
wire reset_rx_done, reset_tx_done, cplllocked;
assign csr = { badKcount, badCharCount,
               {32-FAULT_COUNTER_WIDTH-FAULT_COUNTER_WIDTH-8{1'b0}},
               evr_rx_synchronized, reset_tx_done,
               reset_rx_done, cplllocked,
               1'b0, 1'b0,
               1'b0, reset_all };

//////////////////////////////////////////////////////////////////////////////
// Instantiate the transceiver
`ifndef SIMULATE
  evrgty evrgty (
    .gtwiz_userclk_tx_reset_in(1'b0), // input wire [0 : 0] gtwiz_userclk_tx_reset_in
    .gtwiz_userclk_tx_srcclk_out(),              // output wire [0 : 0] gtwiz_userclk_tx_srcclk_out
    .gtwiz_userclk_tx_usrclk_out(),              // output wire [0 : 0] gtwiz_userclk_tx_usrclk_out
    .gtwiz_userclk_tx_usrclk2_out(gty_tx_clk),     // output wire [0 : 0] gtwiz_userclk_tx_usrclk2_out
    .gtwiz_userclk_tx_active_out(),              // output wire [0 : 0] gtwiz_userclk_tx_active_out
    .gtwiz_userclk_rx_reset_in(1'b0),            // input wire [0 : 0] gtwiz_userclk_rx_reset_in
    .gtwiz_userclk_rx_srcclk_out(),              // output wire [0 : 0] gtwiz_userclk_rx_srcclk_out
    .gtwiz_userclk_rx_usrclk_out(),              // output wire [0 : 0] gtwiz_userclk_rx_usrclk_out
    .gtwiz_userclk_rx_usrclk2_out(evr_clk),       // output wire [0 : 0] gtwiz_userclk_rx_usrclk2_out
    .gtwiz_userclk_rx_active_out(),              // output wire [0 : 0] gtwiz_userclk_rx_active_out
    .gtwiz_buffbypass_rx_reset_in(1'b0),         // input wire [0 : 0] gtwiz_buffbypass_rx_reset_in
    .gtwiz_buffbypass_rx_start_user_in(1'b0),    // input wire [0 : 0] gtwiz_buffbypass_rx_start_user_in
    .gtwiz_buffbypass_rx_done_out(),             // output wire [0 : 0] gtwiz_buffbypass_rx_done_out
    .gtwiz_buffbypass_rx_error_out(),            // output wire [0 : 0] gtwiz_buffbypass_rx_error_out
    .gtwiz_reset_clk_freerun_in(sys_clk),         // input wire [0 : 0] gtwiz_reset_clk_freerun_in
    .gtwiz_reset_all_in(reset_all),              // input wire [0 : 0] gtwiz_reset_all_in
    .gtwiz_reset_tx_pll_and_datapath_in(1'b0),   // input wire [0 : 0] gtwiz_reset_tx_pll_and_datapath_in
    .gtwiz_reset_tx_datapath_in(1'b0),           // input wire [0 : 0] gtwiz_reset_tx_datapath_in
    .gtwiz_reset_rx_pll_and_datapath_in(1'b0),   // input wire [0 : 0] gtwiz_reset_rx_pll_and_datapath_in
    .gtwiz_reset_rx_datapath_in(1'b0),           // input wire [0 : 0] gtwiz_reset_rx_datapath_in
    .gtwiz_reset_rx_cdr_stable_out(),            // output wire [0 : 0] gtwiz_reset_rx_cdr_stable_out
    .gtwiz_reset_tx_done_out(reset_tx_done),     // output wire [0 : 0] gtwiz_reset_tx_done_out
    .gtwiz_reset_rx_done_out(reset_rx_done),     // output wire [0 : 0] gtwiz_reset_rx_done_out
    .gtwiz_userdata_tx_in(16'h00BC),             // input wire [15 : 0] gtwiz_userdata_tx_in
    .gtwiz_userdata_rx_out(rx_data),              // output wire [15 : 0] gtwiz_userdata_rx_out
    .cplllockdetclk_in(sys_clk),                  // input wire [0 : 0] cplllockdetclk_in
    .cplllocken_in(1'b1),                        // input wire [0 : 0] cplllocken_in
    .cpllreset_in(1'b0),                         // input wire [0 : 0] cpllreset_in
    .drpclk_in(sys_clk),                          // input wire [0 : 0] drpclk_in
    .gtrefclk0_in(USER_MGT_SI570_CLK),           // input wire [0 : 0] gtrefclk0_in
    .gtyrxn_in(RX_N),                            // input wire [0 : 0] gtyrxn_in
    .gtyrxp_in(RX_P),                            // input wire [0 : 0] gtyrxp_in
    .loopback_in(LOOPBACK),                      // input wire [2 : 0] loopback_in
    .rx8b10ben_in(1'b1),                         // input wire [0 : 0] rx8b10ben_in
    .rxcommadeten_in(1'b1),                      // input wire [0 : 0] rxcommadeten_in
    .rxmcommaalignen_in(1'b0),                   // input wire [0 : 0] rxmcommaalignen_in
    .rxpcommaalignen_in(1'b0),                   // input wire [0 : 0] rxpcommaalignen_in
    .rxslide_in(rxslide),                        // input wire [0 : 0] rxslide_in
    .tx8b10ben_in(1'b1),                         // input wire [0 : 0] tx8b10ben_in
    .txctrl0_in(16'h0000),                       // input wire [15 : 0] txctrl0_in
    .txctrl1_in(16'h0000),                       // input wire [15 : 0] txctrl1_in
    .txctrl2_in(8'h01),                          // input wire [7 : 0] txctrl2_in
    .cplllock_out(cplllocked),                   // output wire [0 : 0] cplllock_out
    .gtpowergood_out(),                          // output wire [0 : 0] gtpowergood_out
    .gtytxn_out(TX_N),                           // output wire [0 : 0] gtytxn_out
    .gtytxp_out(TX_P),                           // output wire [0 : 0] gtytxp_out
    .rxbyteisaligned_out(),                      // output wire [0 : 0] rxbyteisaligned_out
    .rxbyterealign_out(),                        // output wire [0 : 0] rxbyterealign_out
    .rxcommadet_out(),                           // output wire [0 : 0] rxcommadet_out
    .rxctrl0_out(rxctrl0),                       // output wire [15 : 0] rxctrl0_out
    .rxctrl1_out(rxctrl1),                       // output wire [15 : 0] rxctrl1_out
    .rxctrl2_out(rxctrl2),                       // output wire [7 : 0] rxctrl2_out
    .rxctrl3_out(rxctrl3),                       // output wire [7 : 0] rxctrl3_out
    .rxpmaresetdone_out(),                       // output wire [0 : 0] rxpmaresetdone_out
    .txpmaresetdone_out(),                       // output wire [0 : 0] txpmaresetdone_out
    .txprgdivresetdone_out()                     // output wire [0 : 0] txprgdivresetdone_out
  );

`endif

// Reference clock for RF ADC jitter cleaner
wire evr_clkF;
ODDRE1 ODDRE1_EVR_CLK_F (
   .Q(evr_clkF),
   .C(evr_clk),
   .D1(1'b1),
   .D2(1'b0),
   .SR(1'b0)
);

OBUFDS #(
    .SLEW("FAST")
) OBUFDS_SFP_REC_CLK (
    .O(SFP_REC_CLK_P),
    .OB(SFP_REC_CLK_N),
    .I(evr_clkF)
);

// EVR part
timing_core #(
        .DSP_EV1(DSP_EV1),
        .DSP_EV2(DSP_EV2)
) timing (
    .lb_clk              (sys_clk),
    .evr_clk             (evr_clk),
    .evr_rxd             (evr_chars),
    .evr_rxk             (evr_charisk),
    .evr_evcnt           (evr_evcnt),
    .evr_timestamp_valid (evr_timestamp_valid),
    .dsp_clk             (dsp_clk),
    .dsp_live_ts         (dsp_live_ts),
    // unused: these markers cannot be seen without stretching
    .dsp_pps_marker      (dsp_pps_marker),
    .dsp_hb_marker       (dsp_hb_marker),
    // unused
    .evr_event1          (evr_event1),
    .dsp_event1          (dsp_event1),
    .dsp_event2          (dsp_event2)
);

endmodule
