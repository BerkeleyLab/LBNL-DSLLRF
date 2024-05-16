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
  ,input force_on   // OR'd with pulse envelope for constant-on
  ,input [CW-1:0] count_max
  ,input signed [DW-1:0] amplitude
  // Pulse Outputs
  ,output pulse_en
  ,output signed [DW-1:0] envelope
);

reg [CW-1:0] counter = 0;
reg trig_strobe_d = 0;
reg trig_strobe_re = 0;
reg trig_enabled = 0;
wire enabled = trig_enabled | force_on;
reg [CW-1:0] counter_max = 0;
assign pulse_en = enabled;
reg signed [DW-1:0] amplitude_d = 0;
assign envelope = enabled ? amplitude_d : 0;

always @(posedge clk) begin
  trig_strobe_d <= trig_strobe;
  trig_strobe_re <= trig_strobe & ~trig_strobe_d;
  if (en) begin
    amplitude_d <= amplitude;
    if (trig_enabled) begin
      if (counter < counter_max) begin
        counter <= counter + 1;
      end else begin
        trig_enabled <= 1'b0;
        counter <= 0;
      end
    end else begin
      if (trig_strobe_re) begin
        counter_max <= count_max;
        trig_enabled <= 1'b1;
        counter <= 0;
      end
    end
  end else begin // ~en
    amplitude_d <= 0;
    trig_enabled <= 1'b0;
    counter <= 0;
  end
end

endmodule
