`timescale 1ns / 1ps

// Data interpolator module: 1 to N

module interpolator #(
    parameter SAMP_DW = 16,       // Data width
    parameter SAMP_NUM = 8   // Number of samples per clock cycle
)(
    input wire clk,
    input wire reset,
    input wire signed [SAMP_DW-1:0] data_in,
    input wire data_in_valid,
    output wire [SAMP_DW*SAMP_NUM-1:0] data_out,
    output reg data_out_valid
);
    localparam integer SAMP_NUM_WIDTH = $clog2(SAMP_NUM);
    reg signed [SAMP_DW-1:0] prev_data=0;
    always @(posedge clk) begin
        if (reset) begin
            prev_data <= {SAMP_DW{1'b0}};
        end else if (data_in_valid) begin
            prev_data <= data_in;
        end
        data_out_valid <= data_in_valid;
    end

    wire signed [SAMP_DW:0] diff = data_in - prev_data;
    wire signed [SAMP_DW-1:0] delta;
    assign delta = diff >>> SAMP_NUM_WIDTH;

    wire signed [SAMP_DW-1:0] interp_array [0:SAMP_NUM-1];
    genvar i;
    generate
        for (i = 0; i < SAMP_NUM; i = i + 1) begin
            assign interp_array[i] = prev_data + $signed(delta * i);
            assign data_out[SAMP_DW*i +: SAMP_DW] = interp_array[i];
        end
    endgenerate
endmodule