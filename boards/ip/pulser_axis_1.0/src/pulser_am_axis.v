/* Wrap up the pulser_am in an AXI stream output to feed to the Zynq-RFSoC RF
 * Data Converter DAC input
 */

module pulser_am_axis #(
   parameter CW = 8              // Pulse counter width
  ,parameter [3:0] STREAM_SAMPLES = 1 // Stream data width = 16*STREAM_SAMPLES
  ,parameter MODE_IQ = "false"
)(
   input clk
  ,input en
  // DDS Settings (see ph_acc.v)
  ,input [19:0] phase_step_h
  ,input [11:0] phase_step_l
  ,input [11:0] modulo
  // Pulse Controls
  ,input trig_strobe
  ,input [CW-1:0] count_max
  ,input signed [13:0] amplitude
  // AXI Stream Output
  ,input DAC_stream_tready
  ,output [16*STREAM_SAMPLES-1:0] DAC_stream_tdata
  // According to datasheet: The RF-DAC does not use the sXY_axis_tvalid input to gate the data.
  // Diagnostics
  ,output pulse_en
);

reg [16*STREAM_SAMPLES-1:0] DAC_stream_tdata_d=0;
assign DAC_stream_tdata = DAC_stream_tdata_d;

localparam DW = 14;
wire signed [DW-1:0] iout, qout;
integer N;

generate if (MODE_IQ == "false") begin : mode_real

  always @(posedge clk) begin
    if (en) begin
      for (N = 0; N < STREAM_SAMPLES; N = N + 1) begin
        DAC_stream_tdata_d[16*(N+1)-1-:16] <= {2'b00, iout};
      end
    end
  end

end else begin : mode_iq

  always @(posedge clk) begin
    if (en) begin
      for (N = 0; N < (STREAM_SAMPLES/2); N = N + 1) begin
        DAC_stream_tdata_d[16*(2*N+1)-1-:16] <= {2'b00, iout};
        DAC_stream_tdata_d[16*2*(N+1)-1-:16] <= {2'b00, qout};
      end
    end
  end

end endgenerate

pulser_am #(
   .CW(CW)
  ,.DW(DW)
) pulser_am_i (
   .clk(clk) // input
  ,.en(en) // input
  // DDS Settings
  ,.phase_step_h(phase_step_h) // input [19:0]
  ,.phase_step_l(phase_step_l) // input [11:0]
  ,.modulo(modulo) // input [11:0]
  // Pulse Controls
  ,.trig_strobe(trig_strobe) // input
  ,.count_max(count_max) // input [7:0]
  ,.amplitude(amplitude) // input [15:0]
  // Pulse Outputs
  ,.pulse_en(pulse_en) // output
  ,.envelope() // output [15:0]
  ,.iout(iout) // output [15:0]
  ,.qout(qout) // output [15:0]
);

endmodule
