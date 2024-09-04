// Keep track of time using system clock

module clk_interval_counters #(
    parameter CLK_RATE = 100000000
    ) (
    input             clk,
    output reg [31:0] microseconds_sinceboot,
    output reg [31:0] seconds_sinceboot,
    output reg        PPS);

localparam USEC_DIVIDER_WIDTH = $clog2((CLK_RATE/1000000) - 1);
reg [USEC_DIVIDER_WIDTH:0] usecdivider = (CLK_RATE/1000000) - 2;
wire usectick = usecdivider[USEC_DIVIDER_WIDTH];

localparam SEC_DIVIDER_WIDTH = $clog2(1000000 - 1);
reg [SEC_DIVIDER_WIDTH:0] secdivider = 1000000 - 2;
wire sectick = secdivider[SEC_DIVIDER_WIDTH];

always @(posedge clk) begin
    if (usectick) begin
        usecdivider <= (CLK_RATE/1000000) - 2;
        microseconds_sinceboot <= microseconds_sinceboot + 1;
        if (sectick) begin
            secdivider <= 1000000 - 2;
            seconds_sinceboot <= seconds_sinceboot + 1;
            PPS <= 1;
        end
        else begin
            secdivider <= secdivider - 1;
            PPS <= 0;
        end
    end
    else begin
        usecdivider <= usecdivider - 1;
    end
end

endmodule
