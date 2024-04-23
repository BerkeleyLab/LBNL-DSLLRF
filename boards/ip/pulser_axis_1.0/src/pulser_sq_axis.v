/* Wrap up the pulser_envelope in an AXI stream output to feed to the Zynq-RFSoC RF
 * Data Converter DAC input
 */

module pulser_sq_axis #(
   parameter CW = 8              // Pulse counter width
   ,parameter [3:0] STREAM_SAMPLES = 1 // Stream data width = 16*STREAM_SAMPLES
)(
   input clk
  ,input en
  // Pulse Controls
  ,input trig_strobe
  ,input [CW-1:0] count_max
  ,input signed [DW-1:0] amplitude
  // AXI Stream Output
  ,input DAC_stream_tready
  ,output [16*STREAM_SAMPLES-1:0] DAC_stream_tdata
  ,output pulse_en
  // According to datasheet: The RF-DAC does not use the sXY_axis_tvalid input to gate the data.
);

reg [16*STREAM_SAMPLES-1:0] DAC_stream_tdata_d=0;
assign DAC_stream_tdata = DAC_stream_tdata_d;

localparam DW = 14;
wire signed [DW-1:0] envelope;
integer N;
always @(posedge clk) begin
  if (en) begin
    for (N = 0; N < STREAM_SAMPLES; N = N + 1) begin
      DAC_stream_tdata_d[(16*(N+1))-1-:16] <= {2'b00, envelope};
    end
  end
end

pulser_envelope #(
   .CW(CW)
  ,.DW(DW)
) pulser_envelope_i (
   .clk(clk) // input
  ,.en(en) // input
  // Pulse Controls
  ,.trig_strobe(trig_strobe) // input
  ,.count_max(count_max) // input [CW-1:0]
  ,.amplitude(amplitude) // input [DW-1:0]
  // Pulse Outputs
  ,.pulse_en(pulse_en) // output
  ,.envelope(envelope) // output [DW-1:0]
);

endmodule
