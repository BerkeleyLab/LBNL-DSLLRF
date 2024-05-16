/* Wrap up the pulser_envelope in an AXI stream output to feed to the Zynq-RFSoC RF
 * Data Converter DAC input
 */

module pulser_sq_axis #(
   parameter CW = 8              // Pulse counter width
  ,parameter [4:0] STREAM_SAMPLES = 1 // Stream data width = 16*STREAM_SAMPLES
  ,parameter MODE_IQ = "false"
)(
   input clk
  ,input en
  // Pulse Controls
  ,input trig_strobe
  ,input force_on   // OR'd with pulse envelope for constant-on
  ,input [CW-1:0] count_max
  ,input signed [13:0] amplitude
  // AXI Stream Output
  ,input DAC_stream_tready
  ,output [16*STREAM_SAMPLES-1:0] DAC_stream_tdata
  ,output pulse_en
  // According to datasheet: The RF-DAC does not use the sXY_axis_tvalid input to gate the data.
);

// TODO - Phase input to rotate the I/Q vector

reg [16*STREAM_SAMPLES-1:0] DAC_stream_tdata_d=0;
assign DAC_stream_tdata = DAC_stream_tdata_d;

localparam DW = 14;
wire signed [DW-1:0] envelope;
integer N;
generate if (MODE_IQ == "false") begin : mode_real

  always @(posedge clk) begin
    if (en) begin
      for (N = 0; N < STREAM_SAMPLES; N = N + 1) begin
        DAC_stream_tdata_d[16*(N+1)-1-:16] <= {{2{envelope[DW-1]}}, envelope}; // sign-extension
      end
    end
  end

end else begin : mode_iq

  always @(posedge clk) begin
    if (en) begin
      for (N = 0; N < (STREAM_SAMPLES/2); N = N + 1) begin
        DAC_stream_tdata_d[16*(2*N+1)-1-:16] <= {{2{envelope[DW-1]}}, envelope}; // sign-extension
        DAC_stream_tdata_d[16*2*(N+1)-1-:16] <= 16'h00; // TODO - Currently fixed at real axis
      end
    end
  end

end endgenerate

pulser_envelope #(
   .CW(CW)
  ,.DW(DW)
) pulser_envelope_i (
   .clk(clk) // input
  ,.en(en) // input
  // Pulse Controls
  ,.trig_strobe(trig_strobe) // input
  ,.force_on(force_on)   // input
  ,.count_max(count_max) // input [CW-1:0]
  ,.amplitude(amplitude) // input [DW-1:0]
  // Pulse Outputs
  ,.pulse_en(pulse_en) // output
  ,.envelope(envelope) // output [DW-1:0]
);

endmodule
