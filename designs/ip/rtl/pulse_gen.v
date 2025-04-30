module pulse_gen #(
    parameter AW=12
) (
    input clk,
    input trigger,
    input [AW-1:0] high_len,
    output pulse_out
);

reg [AW-1:0] len=0;
reg [AW-1:0] pc=0;
reg counting=0;
wire last = (pc==len);
always @(posedge clk) begin
    len <= high_len;
    if (last) counting <= 1'b0;
    else if (trigger) counting <= 1'b1;
    pc <= counting ? pc + 1 : 0;
end

assign pulse_out = counting & ~last;

endmodule
