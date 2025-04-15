// base band feedback dsp core
module dsp_core #(
    parameter KW = 18,
    parameter EW = 15
) (
    input clk,
    input reset,

    input signed [KW-1:0] field_i,
    input signed [KW-1:0] field_q,

    output signed [KW-1:0] drive_i,
    output signed [KW-1:0] drive_q,

    input [18:0] rx_phase_offset,
    input [18:0] tx_phase_offset,

    output signed [KW-1:0] amp_measured,
    output signed [KW-1:0] phs_measured,

    input signed [KW-1:0] amp_setpoint,
    input signed [KW-1:0] phs_setpoint,

    input signed [KW-1:0] Kp_amp,
    input signed [KW-1:0] Kp_phs,
    input signed [KW-1:0] Ki_amp,
    input signed [KW-1:0] Ki_phs,
    input amp_loop_enable,
    input phs_loop_enable,
    input amp_loop_reset,
    input phs_loop_reset,
    output signed [EW-1:0] err_out_amp,
    output signed [EW-1:0] err_out_phs
);

// gain: 1.64676
// delay: 20 cycles
wire signed [KW-1:0] amp_measured_raw;
wire signed [KW:0] phs_measured_raw;
cordicg_b22 #(.nstg(20), .width(KW)) rx_cordic (
    .clk       (clk),
    .opin      (2'b01),
    .xin       (field_i),
    .yin       (field_q),
    .phasein   (rx_phase_offset),
    .xout      (amp_measured_raw),
    .phaseout  (phs_measured_raw)
);

// Amp/Phs PI loop
// delay: 4 cycles
assign amp_measured = amp_measured_raw;
assign phs_measured = phs_measured_raw[KW:1];

wire signed [KW-1:0] drive_amp;
pi_scalar #(.KW(KW), .EW(EW), .WRAP(0)) pi_amp (
    .clk        (clk),
    .reset      (amp_loop_reset),
    .enable     (amp_loop_enable),
    .Kp         (Kp_amp),
    .Ki         (Ki_amp),
    .setpoint   (amp_setpoint),
    .measured   (amp_measured),
    .err_out    (err_out_amp),
    .drive      (drive_amp)
);

wire signed [KW-1:0] drive_phs;
pi_scalar #(.KW(KW), .EW(EW), .WRAP(1)) pi_phs (
    .clk        (clk),
    .reset      (phs_loop_reset),
    .enable     (phs_loop_enable),
    .Kp         (Kp_phs),
    .Ki         (Ki_phs),
    .setpoint   (phs_setpoint),
    .measured   (phs_measured),
    .err_out    (err_out_phs),
    .drive      (drive_phs)
);

// compensate measured lo shift
// delay: 20 cycles
cordicg_b22 #(.nstg(20), .width(KW)) tx_cordic (
    .clk        (clk),
    .opin       (2'b00),
    .xin        (drive_amp),
    .yin        (18'h0),
    .phasein    ({drive_phs, 1'b0} + tx_phase_offset),
    .xout       (drive_i),
    .yout       (drive_q)
);

endmodule
