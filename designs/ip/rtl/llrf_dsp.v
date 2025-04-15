`timescale 1ns / 1ps

// Baseband DSP module for LLRF system
module llrf_dsp #(
    parameter integer SAMP_DW = 16,     // 16 bits data
    parameter integer SAMP_NUM = 16,    // 16 samples per clock
    parameter integer DW = SAMP_DW * SAMP_NUM,     // 32 bytes
    parameter integer KW = 18,          // signal width
    parameter integer EW = 12           // error width
) (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 clk CLK" *)
    (* X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF m_axis:s0_axis:s1_axis, ASSOCIATED_RESET axis_aresetn" *)
    input wire clk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 axis_aresetn RST" *)
    input wire axis_aresetn,

    input wire dsp_reset,
    input wire trigger, // single clock cycle pulse
    input wire rf_permit,
    input wire [11:0] pulse_length,
    input wire amp_loop_enable,
    input wire amp_loop_reset,
    input wire signed [KW-1:0] amp_loop_setpoint,
    input wire signed [KW-1:0] amp_loop_kp,
    input wire signed [KW-1:0] amp_loop_ki,
    input wire phs_loop_enable,
    input wire phs_loop_reset,
    input wire signed [KW-1:0] phs_loop_setpoint,
    input wire signed [KW-1:0] phs_loop_kp,
    input wire signed [KW-1:0] phs_loop_ki,

    output wire signed [KW-1:0] amp_measured,
    output wire signed [KW-1:0] phs_measured,
    output wire signed [EW-1:0] amp_loop_err,
    output wire signed [EW-1:0] phs_loop_err,

    // AXI Stream input interface for feedback channel, base band, I
    input wire [DW-1:0] s0_axis_tdata,
    input wire s0_axis_tvalid,
    output wire s0_axis_tready,

    // AXI Stream input interface for feedback channel, base band, Q
    input wire [DW-1:0] s1_axis_tdata,
    input wire s1_axis_tvalid,
    output wire s1_axis_tready,

    // AXI Stream output interface for feedback channel
    output wire [DW-1:0] m_axis_tdata,
    output wire m_axis_tvalid,
    input wire m_axis_tready
);

    assign s0_axis_tready = m_axis_tready;
    assign s1_axis_tready = m_axis_tready;

    // XXX handle s0_axis_tvalid and s1_axis_tvalid
    // XXX average instead of decimate (using the first sample)
    wire signed [KW-1:0] field_i = $signed(s0_axis_tdata[SAMP_DW-1:0]) <<< (KW - SAMP_DW);
    wire signed [KW-1:0] field_q = $signed(s1_axis_tdata[SAMP_DW-1:0]) <<< (KW - SAMP_DW);

    wire signed [KW-1:0] drive_i, drive_q;
    dsp_core #(.KW(KW), .EW(EW)) feedback (
        .clk              (clk),
        .reset            (dsp_reset),
        .field_i          (field_i),
        .field_q          (field_q),
        .drive_i          (drive_i),
        .drive_q          (drive_q),
        .rx_phase_offset  (19'h0),
        .tx_phase_offset  (19'h0),
        .amp_measured     (amp_measured),
        .phs_measured     (phs_measured),
        .amp_setpoint     (amp_loop_setpoint),
        .phs_setpoint     (phs_loop_setpoint),
        .Kp_amp           (amp_loop_kp),
        .Kp_phs           (phs_loop_kp),
        .Ki_amp           (amp_loop_ki),
        .Ki_phs           (phs_loop_ki),
        .amp_loop_enable  (amp_loop_enable),
        .phs_loop_enable  (phs_loop_enable),
        .amp_loop_reset   (amp_loop_reset),
        .phs_loop_reset   (phs_loop_reset),
        .err_out_amp      (amp_loop_err),
        .err_out_phs      (phs_loop_err)
    );

    // XXX interpolate instead of duplicate
    wire signed [SAMP_DW-1:0] drive_i_int = drive_i >>> (KW - SAMP_DW);
    wire signed [SAMP_DW-1:0] drive_q_int = drive_q >>> (KW - SAMP_DW);

    reg [DW-1:0] drive_axis_tdata=0;
    always @(posedge clk) begin
        if (rf_permit) begin
            drive_axis_tdata <= {(SAMP_NUM/2){drive_q_int, drive_i_int}};
        end else begin
            drive_axis_tdata <= {DW{1'b0}};
        end
    end

    // assemble axi stream output
    assign m_axis_tdata = drive_axis_tdata;
    assign m_axis_tvalid = 1'b1;

endmodule
