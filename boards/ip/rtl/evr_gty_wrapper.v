// Wrapper around wizard-generated event receiver GTY block
// and tinyEVR

module evr_gty_wrapper #(
    parameter DEBUG = "false",
    parameter DSP_EV1 = 1,
    parameter DSP_EV2 = 2,
    parameter integer CHECK_TIMEOUT = 125000
    ) (
    // GTY ports
    input              sys_clk,
    output wire [31:0] gty_evr_status,
    output wire [31:0] gty_rx_reset_cnt,  // in sys_clk
    // user settable
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
    output wire [63:0] evr_live_ts,

    input              dsp_clk,
    output wire [63:0] dsp_live_ts,
    // needs to be stretched
    output wire        dsp_pps_marker,
    output wire        dsp_hb_marker,

    output wire        evr_event1,
    output wire        dsp_event1, // DSP_EV1
    output wire        dsp_event2  // DSP_EV2
);

localparam LOOPBACK = 3'd4; // 4 == Far end PMA loopback
localparam COMMAS_NEEDED = 60;

// Extract status bits of interest
wire [15:0] rx_data;
wire [15:0] rxctrl0, rxctrl1;
wire  [7:0] rxctrl2, rxctrl3;
wire  [1:0] rx_charisk        = rxctrl0[1:0];
wire  [1:0] rx_disparity_error = rxctrl1[1:0];
wire  [1:0] rx_char_iscomma    = rxctrl2[1:0];
wire  [1:0] rx_notintable = rxctrl3[1:0];

wire [1:0] comma_seen;
assign comma_seen[0] = rx_charisk[0] & (rx_data[0+:8] == 8'hBC);
assign comma_seen[1] = rx_charisk[1] & (rx_data[8+:8] == 8'hBC);

// error when the rxcharisk_out MSB bit is set and rxdata_out[15:8] == 8'hBC
// Allow commas (SOF, EOP - special ones) in the MSB,
// since MRF can support the "data protocol" on the dbus
// see page 18 of the [EVG MRF document](http://www.mrf.fi/dmdocuments/EVG-TREF-004.pdf)
wire data_err_comb = (rx_notintable != 0) || rx_charisk[1] || (rx_disparity_error != 0);
reg data_err=0; always @(posedge evr_clk) data_err <= data_err_comb;

// since RX elastic buffer bypassed, IP core's helper block is only used to adjust the phase difference between the PMA parallel clock (XCLK) and the RXUSRCLK
// a separate FSM module (evr_reset_fsm) outside of IP core is used to check for data alignment
// keep everything in evr_clk
(*mark_debug=DEBUG*) wire gty_reset_all, gty_reset_fsm, rx_aligned, rx_aligned_sys;
wire [31:0] gty_rx_reset_cnt_x;
evr_reset_fsm #(
    .COMMAS_NEEDED  (COMMAS_NEEDED),
    .CHECK_TIMEOUT  (CHECK_TIMEOUT)
) evr_reset_fsm_i (
    .clk            (evr_clk),
    .rst            (1'b0),
    .error_seen     (data_err),
    .comma_seen     (comma_seen[0]),
    .reset_done     (reset_rx_done),
    .reset_out      (gty_reset_fsm),
    .ready_out      (rx_aligned),
    .reset_out_cnt  (gty_rx_reset_cnt_x)
);

data_xdomain #(.size(32)) i_rx_reset_cnt (
    .clk_in   (evr_clk), .gate_in  (1'b1),
    .data_in  (gty_rx_reset_cnt_x),
    .clk_out  (sys_clk), .gate_out (),
    .data_out (gty_rx_reset_cnt)
);

// combine fsm reset output and reset_all from control bus
// are all async
assign gty_reset_all = gty_reset_fsm | reset_all;

reg_tech_cdc rx_aligned_x (.I(rx_aligned), .C(sys_clk), .O(rx_aligned_sys));

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

reg [1:0] evr_charisk = 0;
reg [15:0] evr_chars = 0;
// K character can only appear on word 0
always @(posedge evr_clk) begin
    evr_chars <= rx_aligned ? rx_data : 16'd0;
    evr_charisk <= rx_charisk;
end

// Status register
wire reset_rx_done;  // in evr_clk
wire reset_tx_done;  // in gty_tx_clk
wire cplllocked;  // async

wire reset_rx_done_sys, reset_tx_done_sys;
reg_tech_cdc reset_rx_done_x (.I(reset_rx_done), .C(sys_clk), .O(reset_rx_done_sys));
reg_tech_cdc reset_tx_done_x (.I(reset_tx_done), .C(sys_clk), .O(reset_tx_done_sys));

assign gty_evr_status = {rx_aligned_sys, reset_tx_done_sys, reset_rx_done_sys, cplllocked, reset_all, gty_reset_all};

//////////////////////////////////////////////////////////////////////////////
// Instantiate the transceiver
`ifndef SIMULATE
  evrgty evrgty (
    .gtwiz_userclk_tx_reset_in(1'b0),            // input wire [0 : 0] gtwiz_userclk_tx_reset_in
    .gtwiz_userclk_tx_srcclk_out(),              // output wire [0 : 0] gtwiz_userclk_tx_srcclk_out
    .gtwiz_userclk_tx_usrclk_out(),              // output wire [0 : 0] gtwiz_userclk_tx_usrclk_out
    .gtwiz_userclk_tx_usrclk2_out(gty_tx_clk),   // output wire [0 : 0] gtwiz_userclk_tx_usrclk2_out
    .gtwiz_userclk_tx_active_out(),              // output wire [0 : 0] gtwiz_userclk_tx_active_out
    .gtwiz_userclk_rx_reset_in(1'b0),            // input wire [0 : 0] gtwiz_userclk_rx_reset_in
    .gtwiz_userclk_rx_srcclk_out(),              // output wire [0 : 0] gtwiz_userclk_rx_srcclk_out
    .gtwiz_userclk_rx_usrclk_out(),              // output wire [0 : 0] gtwiz_userclk_rx_usrclk_out
    .gtwiz_userclk_rx_usrclk2_out(evr_clk),      // output wire [0 : 0] gtwiz_userclk_rx_usrclk2_out
    .gtwiz_userclk_rx_active_out(),              // output wire [0 : 0] gtwiz_userclk_rx_active_out
    .gtwiz_buffbypass_rx_reset_in(1'b0),         // input wire [0 : 0] gtwiz_buffbypass_rx_reset_in
    .gtwiz_buffbypass_rx_start_user_in(1'b0),    // input wire [0 : 0] gtwiz_buffbypass_rx_start_user_in
    .gtwiz_buffbypass_rx_done_out(),             // output wire [0 : 0] gtwiz_buffbypass_rx_done_out
    .gtwiz_buffbypass_rx_error_out(),            // output wire [0 : 0] gtwiz_buffbypass_rx_error_out
    .gtwiz_reset_clk_freerun_in(sys_clk),        // input wire [0 : 0] gtwiz_reset_clk_freerun_in
    .gtwiz_reset_all_in(gty_reset_all),          // input wire [0 : 0] gtwiz_reset_all_in
    .gtwiz_reset_tx_pll_and_datapath_in(1'b0),   // input wire [0 : 0] gtwiz_reset_tx_pll_and_datapath_in
    .gtwiz_reset_tx_datapath_in(1'b0),           // input wire [0 : 0] gtwiz_reset_tx_datapath_in
    .gtwiz_reset_rx_pll_and_datapath_in(1'b0),   // input wire [0 : 0] gtwiz_reset_rx_pll_and_datapath_in
    .gtwiz_reset_rx_datapath_in(1'b0),           // input wire [0 : 0] gtwiz_reset_rx_datapath_in
    .gtwiz_reset_rx_cdr_stable_out(),            // output wire [0 : 0] gtwiz_reset_rx_cdr_stable_out
    .gtwiz_reset_tx_done_out(reset_tx_done),     // output wire [0 : 0] gtwiz_reset_tx_done_out
    .gtwiz_reset_rx_done_out(reset_rx_done),     // output wire [0 : 0] gtwiz_reset_rx_done_out
    .gtwiz_userdata_tx_in(16'h00BC),             // input wire [15 : 0] gtwiz_userdata_tx_in
    .gtwiz_userdata_rx_out(rx_data),             // output wire [15 : 0] gtwiz_userdata_rx_out
    .cplllockdetclk_in(sys_clk),                 // input wire [0 : 0] cplllockdetclk_in
    .cplllocken_in(1'b1),                        // input wire [0 : 0] cplllocken_in
    .cpllreset_in(1'b0),                         // input wire [0 : 0] cpllreset_in
    .drpclk_in(sys_clk),                         // input wire [0 : 0] drpclk_in
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
    .evr_live_ts         (evr_live_ts),
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

// copied from USPAS_LLRF
module evr_reset_fsm #(
    parameter DEBUG = "false",
    parameter integer COMMAS_NEEDED = 60,
    parameter integer CHECK_TIMEOUT = 125000  // ~125e6 Hz (124.91 MHz) * 1ms
) (
    input clk,
    input rst,
    input error_seen,
    input comma_seen,
    input reset_done,
    output reg ready_out = 0,
    output reg [31:0] reset_out_cnt = 0,
    output reset_out
);
    // State encoding
    localparam  READY = 2'd0,
                RESET = 2'd1,
                CHECK = 2'd2;
    // State register
    (*mark_debug=DEBUG*) reg [1:0] state=CHECK;
    (*mark_debug=DEBUG*) reg [1:0] current_state=CHECK, next_state=CHECK;

    (*mark_debug=DEBUG*) reg [7:0] comma_cnt = 0;
    (*mark_debug=DEBUG*) reg [17:0] check_timeout_cnt=0; // time out counter to count up to 1ms (100e3)

    // Task to update state string for simulation only
    reg [8*7:1] state_string;
    task update_state_string;
        input [1:0] state;
        begin
            case (state)
                READY: state_string = "READY ";
                RESET: state_string = "RESET ";
                CHECK: state_string = "CHECK ";
                default: state_string = "UNKNOWN";
            endcase
        end
    endtask

    // State transition logic
    always @(posedge clk) begin
        if (rst) begin
            comma_cnt <= 8'd0;
            current_state <= CHECK;
        end else begin
            current_state <= next_state;
            if (current_state == RESET) begin
                comma_cnt <= 8'b0; // Reset comma counter in RESET state
                check_timeout_cnt <= 18'b0; // Reset timeout counter
            end else if (current_state == CHECK) begin
                if (comma_seen && comma_cnt < COMMAS_NEEDED) begin
                    comma_cnt <= comma_cnt + 1'd1;
                end
                if (check_timeout_cnt < CHECK_TIMEOUT) begin
                    check_timeout_cnt <= check_timeout_cnt + 1'd1;
                end
            end else begin
                check_timeout_cnt <= 18'b0; // Reset timeout counter in other states
            end
        end
    end

    // Next state logic
    always @(*) begin
        case (current_state)
            READY: begin
                if (error_seen)
                    next_state = RESET;
                else
                    next_state = READY;
            end
            RESET: begin
                if (reset_done)
                    next_state = CHECK;
                else
                    next_state = RESET;
            end
            CHECK: begin
                if ((comma_cnt == COMMAS_NEEDED) && reset_done)
                    next_state = READY;
                else if (check_timeout_cnt == CHECK_TIMEOUT)
                    next_state = RESET;
                else
                    next_state = CHECK;
            end
            default: begin
                next_state = RESET;
            end
        endcase
    end

    reg reset=1'b0, reset_delay=1'b0;
    // Output logic
    always @(posedge clk) begin
        state <= current_state;
        update_state_string(current_state);
        reset_delay <= reset;
        reset <= (current_state == RESET);
        ready_out <= (current_state == READY);
        reset_out_cnt <= reset_out_cnt + reset_out;
    end
    assign reset_out = reset & ~reset_delay;   // Strobe reset_out for 1 cycle
endmodule
