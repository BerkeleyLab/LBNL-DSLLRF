`timescale 1ns / 1ns

module pi_scalar #(
    parameter KW = 18,  // signal width
    parameter EW = 12,  // error width (saturated)
    parameter WRAP = 0  // enable phase wrapping
) (
    input clk,
    input reset,
    input enable,
    input signed [KW-1:0] Kp,
    input signed [KW-1:0] Ki,
    input signed [KW-1:0] setpoint,
    input signed [KW-1:0] measured,
    output signed [EW-1:0] err_out,
    output signed [KW-1:0] drive
);

localparam [KW:0] full = (1<<KW);
localparam [KW:0] half = full >> 1;  // 180 deg

`define SAT(x,old,new) ((~|x[old:new] | &x[old:new]) ? x[new:0] : {x[old],{new{~x[old]}}})

reg signed [KW:0] err=0;
reg signed [EW-1:0] err_clip=0;
wire reset_all = reset | ~enable; // forget old states when relocking

wire signed [KW:0] err_raw = setpoint - measured;

always @(posedge clk) begin
    if (reset_all) begin
        err <= 0;
        err_clip <= 0;
    end else begin
        err <= WRAP ? (err_raw + half) % full - half : err_raw; // wrap phase error
        err_clip <= `SAT(err, KW, EW-1); // slew rate limiter, clip to EW bits
    end
end
assign err_out = err_clip;

// Proportional
reg signed [KW+EW-1:0] prop=0;
reg signed [KW+EW-1:0] prop_out=0;
always @(posedge clk) begin
    if (reset_all) begin
        prop <= 0;
        prop_out <= 0;
    end else begin
        prop <= err_clip * Kp;
        prop_out <= prop;
    end
end

// Integral
reg signed [KW+EW-1:0] intg=0;
reg signed [KW+EW-1:0] intg_out=0;
always @ (posedge clk) begin
    if (reset_all) begin
        intg <= 0;
        intg_out <= 0;
    end else begin
		intg <= err_clip * Ki;
		intg_out <= intg + intg_out;
	end
end

// Proportional + Integral
assign drive = enable ? intg_out[KW+EW-1:EW]+ prop_out[KW+EW-1:EW] : setpoint;

endmodule
