module timing_core #(
    parameter DSP_EV1 = 1, // Configurable event code to route to dsp_clk.
    parameter DSP_EV2 = 2  // N.B: 0 is not a valid event code
) (
    input             lb_clk,
    // Fiber interface
    input             evr_clk,
    input [15:0]      evr_rxd,
    input [1:0]       evr_rxk,

    // EVR Control interface (@lb_clk)
    output [15:0]     evr_evcnt,
    output            evr_timestamp_valid,

    input             dsp_clk,
    output [63:0]     dsp_live_ts,
    // needs to be stretched????
    output            dsp_pps_marker,
    output            dsp_hb_marker,

    output            evr_event1,
    output            dsp_event1, // DSP_EV1
    output            dsp_event2  // DSP_EV2
);

    // ---------------------
    // Timing Event Receiver (EVR)
    // ---------------------
    localparam EVR_EVSTROBE_CNT = 126; // As large as the highest event code of interest
    localparam EVR_TSTAMP_WI = 64;
    wire evr_pps_marker, evr_ts_valid_x;
    wire [EVR_TSTAMP_WI-1:0] evr_timestamp_x;
    wire [EVR_EVSTROBE_CNT-1:0] evr_evstrobe;

    tinyEVR #(.EVSTROBE_COUNT(EVR_EVSTROBE_CNT)) tinyEVR (
        .evrRxClk       (evr_clk),
        .evrRxWord      (evr_rxd),
        .evrCharIsK     (evr_rxk),
        .ppsMarker      (evr_pps_marker),
        .timestampValid (evr_ts_valid_x),
        .timestamp      (evr_timestamp_x),
        .evStrobe       (evr_evstrobe)
    );

    reg evr_ts_valid=0;
    always @(posedge lb_clk) evr_ts_valid <= evr_ts_valid_x; // Quasi-static
    assign evr_timestamp_valid = evr_ts_valid;

    // Event masking and counting in evr_clk domain
    reg [15:0] evr_evcnt_x=0;
    wire [EVR_EVSTROBE_CNT-1:0] evr_evstb_masked = evr_evstrobe[EVR_EVSTROBE_CNT-1:0] & (1 << (DSP_EV1-1));

    // Start latching events only after timestamp has been recovered successfully to avoid registering
    // partially-decoded events
    wire count_event = |evr_evstb_masked && evr_ts_valid_x;
    reg count_event_r=0;
    always @(posedge evr_clk) begin
        if (count_event) evr_evcnt_x <= evr_evcnt_x + 1;
        count_event_r <= count_event;
    end

    // CDC to lb_clk
    data_xdomain #(.size(16)) i_evcnt_sync (
        .clk_in   (evr_clk), .gate_in  (count_event_r),
        .data_in  (evr_evcnt_x),
        .clk_out  (lb_clk), .gate_out (),
        .data_out (evr_evcnt)
    );

    // Make configurable events available to LLRF in dsp_clk domain
    `ifdef SIMULATE
        initial if ((DSP_EV1 == 0) || (DSP_EV2 == 0)) begin
            $display("ERROR %m: Event code must be > 0");
            $finish;
        end
    `endif

    assign evr_event1 = evr_evstrobe[DSP_EV1-1];
    // Note -1 to go from event code to array index
    flag_xdomain i_ev1 (.clk1(evr_clk), .flagin_clk1(evr_evstrobe[DSP_EV1-1]),
                        .clk2(dsp_clk), .flagout_clk2(dsp_event1));
    flag_xdomain i_ev2 (.clk1(evr_clk), .flagin_clk1(evr_evstrobe[DSP_EV2-1]),
                        .clk2(dsp_clk), .flagout_clk2(dsp_event2));

    // timestamp (seconds and ticks) CDC to dsp_clk
    wire [63:0] dsp_evr_timestamp;
    evr_ts_cdc dut(
        .evr_clk(evr_clk),
        .ts_secs(evr_timestamp_x[63:32]), .ts_tcks(evr_timestamp_x[31:0]),
        .evr_pps(evr_pps_marker),
        .usr_clk(dsp_clk),
        .usr_secs(dsp_live_ts[63:32]), .usr_tcks(dsp_live_ts[31:0])
    );

    flag_xdomain i_pps (.clk1(evr_clk), .flagin_clk1(evr_pps_marker),
                        .clk2(dsp_clk), .flagout_clk2(dsp_pps_marker));

    localparam EVCODE_HEARTBEAT_MARKER = 8'h7A;
    flag_xdomain i_hb (.clk1(evr_clk), .flagin_clk1(evr_evstrobe[EVCODE_HEARTBEAT_MARKER]),
                        .clk2(dsp_clk), .flagout_clk2(dsp_hb_marker));

endmodule
