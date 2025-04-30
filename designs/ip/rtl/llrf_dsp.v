`timescale 1ns / 1ps

// Baseband DSP module for LLRF system
module llrf_dsp #(
    parameter integer SAMP_DW = 16,
    parameter integer S_AXIS_SAMP_NUM = 2,
    parameter integer S_AXIS_DW = SAMP_DW * S_AXIS_SAMP_NUM,
    parameter integer M_AXIS_SAMP_NUM = 16,
    parameter integer M_AXIS_DW = SAMP_DW * M_AXIS_SAMP_NUM,
    parameter integer KW = 18,          // signal width
    parameter integer EW = 12           // error width
) (
    input wire clk,

    input wire dsp_reset,
    input wire trigger, // single clock cycle pulse
    input wire rf_permit,
    input wire pulse_enable,
    input wire [15:0] pulse_length,
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
    input wire [S_AXIS_DW-1:0] s0_axis_tdata,
    input wire s0_axis_tvalid,
    output wire s0_axis_tready,

    // AXI Stream input interface for feedback channel, base band, Q
    input wire [S_AXIS_DW-1:0] s1_axis_tdata,
    input wire s1_axis_tvalid,
    output wire s1_axis_tready,

    // AXI Stream output interface for feedback channel
    output wire [M_AXIS_DW-1:0] m_axis_tdata,
    output wire m_axis_tvalid,
    input wire m_axis_tready
);

    assign s0_axis_tready = m_axis_tready;
    assign s1_axis_tready = m_axis_tready;

    wire signed [SAMP_DW-1:0] s0_axis_tdata_avg;
    wire signed [SAMP_DW-1:0] s1_axis_tdata_avg;
    averager #(
        .SAMP_DW(SAMP_DW),
        .SAMP_NUM(S_AXIS_SAMP_NUM)
    ) average_i (
        .clk(clk),
        .data_in(s0_axis_tdata),
        .data_in_valid(s0_axis_tvalid),
        .data_out(s0_axis_tdata_avg),
        .data_out_valid()
    );

    averager #(
        .SAMP_DW(SAMP_DW),
        .SAMP_NUM(S_AXIS_SAMP_NUM)
    ) average_q (
        .clk(clk),
        .data_in(s1_axis_tdata),
        .data_in_valid(s1_axis_tvalid),
        .data_out(s1_axis_tdata_avg),
        .data_out_valid()
    );
    // rx_coupler
    // gain: 2**(KW-SAMP_DW)
    wire signed [KW-1:0] field_i = s0_axis_tdata_avg <<< (KW - SAMP_DW);
    wire signed [KW-1:0] field_q = s1_axis_tdata_avg <<< (KW - SAMP_DW);

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

    // tx_coupler
    // gain: 1 / 2**(KW-SAMP_DW)
    wire signed [SAMP_DW-1:0] drive_i_int = drive_i >>> (KW - SAMP_DW);
    wire signed [SAMP_DW-1:0] drive_q_int = drive_q >>> (KW - SAMP_DW);

    wire [M_AXIS_DW/2-1:0] drive_i_interpolated;
    wire [M_AXIS_DW/2-1:0] drive_q_interpolated;
    interpolator #(
        .SAMP_DW(SAMP_DW),
        .SAMP_NUM(M_AXIS_SAMP_NUM/2)
    ) interp_i (
        .clk(clk),
        .reset(dsp_reset),
        .data_in(drive_i_int),
        .data_in_valid(1'b1),
        .data_out(drive_i_interpolated),
        .data_out_valid()
    );

    interpolator #(
        .SAMP_DW(SAMP_DW),
        .SAMP_NUM(M_AXIS_SAMP_NUM/2)
    ) interp_q (
        .clk(clk),
        .reset(dsp_reset),
        .data_in(drive_q_int),
        .data_in_valid(1'b1),
        .data_out(drive_q_interpolated),
        .data_out_valid()
    );

    // interleave I and Q samples
    wire [M_AXIS_DW-1:0] drive_axis_tdata_i;
    generate
        genvar i;
        for (i = 0; i < M_AXIS_SAMP_NUM/2; i = i + 1) begin : drive_gen
            assign drive_axis_tdata_i[SAMP_DW * (2*i)   +: SAMP_DW] = drive_i_interpolated[SAMP_DW * i +: SAMP_DW];
            assign drive_axis_tdata_i[SAMP_DW * (2*i+1) +: SAMP_DW] = drive_q_interpolated[SAMP_DW * i +: SAMP_DW];
        end
    endgenerate

    wire pulse_valid;
    pulse_gen #(
        .AW(16)
    ) pulse_gen_inst (
        .clk(clk),
        .trigger(trigger),
        .high_len(pulse_length),
        .pulse_out(pulse_valid)
    );
    wire [M_AXIS_DW-1:0] drive_axis_tdata_pulse;
    assign drive_axis_tdata_pulse = pulse_valid ? drive_axis_tdata_i : {M_AXIS_DW{1'b0}};

    reg [M_AXIS_DW-1:0] drive_axis_tdata=0;
    always @(posedge clk) begin
        if (rf_permit) begin
            drive_axis_tdata <= pulse_enable ? drive_axis_tdata_pulse : drive_axis_tdata_i;
        end else begin
            drive_axis_tdata <= {M_AXIS_DW{1'b0}};
        end
    end

    // assemble axi stream output
    assign m_axis_tdata = drive_axis_tdata;
    assign m_axis_tvalid = 1'b1;

endmodule
