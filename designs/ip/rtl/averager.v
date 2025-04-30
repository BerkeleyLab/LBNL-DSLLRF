`timescale 1ns / 1ns

// Data average module: N to 1
module averager #(
    parameter SAMP_DW = 16,  // Data width
    parameter SAMP_NUM = 16  // Number of samples per clock cycle
)(
    input wire clk,
    input wire signed [SAMP_DW*SAMP_NUM-1:0] data_in,
    input wire data_in_valid,
    output reg [SAMP_DW-1:0] data_out,
    output reg data_out_valid
);
    localparam integer SAMP_NUM_WIDTH = $clog2(SAMP_NUM);
    reg signed [SAMP_NUM_WIDTH+SAMP_DW-1:0] sum=0;
    integer i;
    always @* begin
        sum = {SAMP_NUM_WIDTH+SAMP_DW{1'b0}};
        for (i = 0; i < SAMP_NUM; i = i + 1) begin
            sum = sum + $signed(data_in[SAMP_DW*i +: SAMP_DW]);
        end
    end

    always @(posedge clk) begin
        data_out <= sum >>> SAMP_NUM_WIDTH;
        data_out_valid <= data_in_valid;
    end
endmodule