/* Square pulse generator
 */

module pulser_envelope #(
   parameter CW = 8   // Counter width
  ,parameter DW = 16  // Signed signal bit width
)(
   input clk
  ,input en
  // Pulse Controls
  ,input trig_strobe
  ,input [CW-1:0] count_max
  ,input signed [DW-1:0] amplitude
  // Pulse Outputs
  ,output pulse_en
  ,output signed [DW-1:0] envelope
);

reg [CW-1:0] counter = 0;
reg trig_strobe_d = 0;
reg trig_strobe_re = 0;
reg enabled = 0;
reg [CW-1:0] counter_max = 0;
assign pulse_en = enabled;
reg signed [DW-1:0] amplitude_d = 0;
assign envelope = enabled ? amplitude_d : 0;

always @(posedge clk) begin
  trig_strobe_d <= trig_strobe;
  trig_strobe_re <= trig_strobe ? ~trig_strobe_re : 1'b0;
  if (en) begin
    amplitude_d <= amplitude;
    if (enabled) begin
      if (counter < counter_max) begin
        counter <= counter + 1;
      end else begin
        enabled <= 1'b0;
        counter <= 0;
      end
    end else begin
      if (trig_strobe_re) begin
        counter_max <= count_max;
        enabled <= 1'b1;
        counter <= 0;
      end
    end
  end else begin // ~en
    amplitude_d <= 0;
    enabled <= 1'b0;
    counter <= 0;
  end
end

endmodule
