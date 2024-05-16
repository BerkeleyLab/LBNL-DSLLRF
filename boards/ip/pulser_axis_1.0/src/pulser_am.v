/* AM square-wave carrier (100% modulation depth)
 *
 * TODO:
 *  1. Currently open-loop, frequency set by DDS settings
 *  2. Gating the sinusoids to avoid the cordic delay; this may not be
 *     desirable because the delay is still present in the amplitude, so
 *     it probably makes most sense to make the amplitude/phase/time
 *     delays are all equal.
 */

module pulser_am #(
   parameter CW = 8   // Counter width
  ,parameter DW = 16  // Signed signal bit width
)(
   input clk
  ,input en
  // DDS Settings
  ,input [19:0] phase_step_h  // High order (coarse, binary) phase step
  ,input [11:0] phase_step_l  // Low order (fine, possibly non-binary) phase step
  ,input [11:0] modulo  // Encoding of non-binary modulus; 0 means binary
  // Pulse Controls
  ,input trig_strobe
  ,input force_on   // OR'd with pulse envelope for constant-on
  ,input [CW-1:0] count_max
  ,input signed [DW-1:0] amplitude
  // Pulse Outputs
  ,output pulse_en
  ,output signed [DW-1:0] envelope
  ,output signed [DW-1:0] iout
  ,output signed [DW-1:0] qout
);

pulser_envelope #(
   .CW(CW)
  ,.DW(DW)
) pulser_envelope_i (
   .clk(clk)  // input
  ,.en(en)  // input
  ,.trig_strobe(trig_strobe)  // input
  ,.force_on(force_on)    // input
  ,.count_max(count_max)  // input [CW-1:0]
  ,.amplitude(amplitude)  // input [DW-1:0]
  ,.pulse_en(pulse_en)  // output
  ,.envelope(envelope)  // output signed [DW-1:0]
);

wire [18:0] dds_phase_acc;
wire [DW:0] cordic_phasein;
reg [DW:0] cordic_phasein_d = 0;
always @(posedge clk) begin
  cordic_phasein_d <= cordic_phasein_d + 20000;
end
assign cordic_phasein = dds_phase_acc[18:18-DW];
//assign cordic_phasein = dds_phase_acc;

ph_acc dds_lo (
   .clk(clk)
  ,.reset(1'b0)
  ,.en(1'b1)
  ,.phase_acc(dds_phase_acc) // output [18:0]
  ,.phase_step_h(phase_step_h) // input [19:0]
  ,.phase_step_l(phase_step_l) // input [11:0] 
  ,.modulo(modulo) // input [11:0]
);

wire signed [DW-1:0] iout_ungated, qout_ungated;
assign iout = pulse_en ? iout_ungated : 0;
assign qout = pulse_en ? qout_ungated : 0;
localparam [DW-1:0] DW_ZERO = 0;
`include "cordic_ops.vh"
cordicg_b22 #(
  .width(DW),
  .nstg(21),
  .def_op(CORDIC_OP_POLAR_TO_RECT)
) cordicg_b22_i (
  .clk(clk),
  .opin(CORDIC_OP_POLAR_TO_RECT),  // input [1:0]
  .xin(envelope), // input [width-1:0]
  .yin(DW_ZERO), // input [width-1:0]
  .phasein(cordic_phasein), // input [width:0]
  .xout(iout_ungated), // output [width-1:0]
  .yout(qout_ungated), // output [width-1:0]
  .phaseout() // output [width:0]
);

endmodule
