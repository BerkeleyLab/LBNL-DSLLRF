// CORDIC processor, machine generated from cordicgx.py
// 22 is the internal data path width
`timescale 1ns / 1ns
module cordicg_b22 #(
    parameter width=19,
    parameter nstg=21,
    parameter def_op=0
) (
    input clk,
    input [1:0] opin,
    //  opin = 1 forces y to zero (rect to polar),
    //  opin = 0 forces theta to zero (polar to rect),
    //  opin = 3 for follow mode
    input [width-1:0] xin,
    input [width-1:0] yin,
    input [width:0] phasein,
    output [width-1:0] xout,
    output [width-1:0] yout,
    output [width:0] phaseout
);

// input buffer stage (routing)
reg [1:0] opin0=def_op;
reg [width-1:0] xin0=0, yin0=0;
reg [width:0] phasein0=0;
always @(posedge clk) begin
    opin0    <= opin;
    xin0     <= xin;
    yin0     <= yin;
    phasein0 <= phasein;
end

// zero stage: doesn't quite fit the pattern
reg  [1:0] op0=def_op;
wire [width-1:0] xw0,  yw0  ; wire [width:0] zw0;
reg  [width-1:0] x0=0, y0=0 ; reg  [width:0] z0=0;
wire control0_l = opin0[0] ? xin0[width-1] : phasein0[width]^phasein0[width-1];
reg control0_h=0;
// No inversion of control0_h, unlike all the other stages!
// Rotation is either 0 or 180, which are their own inverses.
wire control0 = opin0[1] ? control0_h : control0_l;
addsubg #(width) ax0 ({width{1'b0}}, xin0, xw0, ~control0);
addsubg #(width) ay0 ({width{1'b0}}, yin0, yw0, ~control0);
assign zw0 = {phasein0[width]^control0,phasein0[width-1:0]};
always @(posedge clk) begin
   op0 <= opin0;
   x0 <= xw0;
   y0 <= yw0;
   z0 <= zw0;
   control0_h <= control0_l;
end

// first stage: can't use cstageg because repeat operator of zero is illegal
reg  [1:0] op1=def_op;
wire [width-1:0] xw1,   yw1   ; wire [width:0] zw1;
reg  [width-1:0] xt1=0, yt1=0 ; reg  [width:0] zt1=0;
wire control1_l = op0[0] ? ~y0[width-1] : z0[width];
reg control1_h=0;
wire control1 = op0[1] ? ~control1_h : control1_l;
addsubg #(width) ax1 (x0, y0, xw1,  control1);
addsubg #(width) ay1 (y0, x0, yw1, ~control1);
addsubg #(width+1) az1 (z0, {3'b001,{(width-2){1'b0}}}, zw1,  control1);
always @(posedge clk) begin
    op1 <= op0;
    xt1 <= xw1;
    yt1 <= yw1;
    zt1 <= zw1;
    control1_h <= control1_l;
end

wire [1:0] opn[1:21];
wire [21:0] xn[1:21], yn[1:21];
wire [22:0] zn[1:21];
assign opn[1] = op1;
assign xn[1] = {xt1,{(22-width){1'b0}}};
assign yn[1] = {yt1,{(22-width){1'b0}}};
assign zn[1] = {zt1,{(22-width){1'b0}}};
cstageg #(  1, 23, 22, def_op) cs1  ( clk, opn[1 ], xn[1 ],  yn[1 ], zn[1 ], 23'd619011   , opn[2 ], xn[2 ],  yn[2 ],  zn[2 ]);
cstageg #(  2, 23, 22, def_op) cs2  ( clk, opn[2 ], xn[2 ],  yn[2 ], zn[2 ], 23'd327068   , opn[3 ], xn[3 ],  yn[3 ],  zn[3 ]);
cstageg #(  3, 23, 22, def_op) cs3  ( clk, opn[3 ], xn[3 ],  yn[3 ], zn[3 ], 23'd166025   , opn[4 ], xn[4 ],  yn[4 ],  zn[4 ]);
cstageg #(  4, 23, 22, def_op) cs4  ( clk, opn[4 ], xn[4 ],  yn[4 ], zn[4 ], 23'd83335    , opn[5 ], xn[5 ],  yn[5 ],  zn[5 ]);
cstageg #(  5, 23, 22, def_op) cs5  ( clk, opn[5 ], xn[5 ],  yn[5 ], zn[5 ], 23'd41708    , opn[6 ], xn[6 ],  yn[6 ],  zn[6 ]);
cstageg #(  6, 23, 22, def_op) cs6  ( clk, opn[6 ], xn[6 ],  yn[6 ], zn[6 ], 23'd20859    , opn[7 ], xn[7 ],  yn[7 ],  zn[7 ]);
cstageg #(  7, 23, 22, def_op) cs7  ( clk, opn[7 ], xn[7 ],  yn[7 ], zn[7 ], 23'd10430    , opn[8 ], xn[8 ],  yn[8 ],  zn[8 ]);
cstageg #(  8, 23, 22, def_op) cs8  ( clk, opn[8 ], xn[8 ],  yn[8 ], zn[8 ], 23'd5215     , opn[9 ], xn[9 ],  yn[9 ],  zn[9 ]);
cstageg #(  9, 23, 22, def_op) cs9  ( clk, opn[9 ], xn[9 ],  yn[9 ], zn[9 ], 23'd2608     , opn[10], xn[10],  yn[10],  zn[10]);
cstageg #( 10, 23, 22, def_op) cs10 ( clk, opn[10], xn[10],  yn[10], zn[10], 23'd1304     , opn[11], xn[11],  yn[11],  zn[11]);
cstageg #( 11, 23, 22, def_op) cs11 ( clk, opn[11], xn[11],  yn[11], zn[11], 23'd652      , opn[12], xn[12],  yn[12],  zn[12]);
cstageg #( 12, 23, 22, def_op) cs12 ( clk, opn[12], xn[12],  yn[12], zn[12], 23'd326      , opn[13], xn[13],  yn[13],  zn[13]);
cstageg #( 13, 23, 22, def_op) cs13 ( clk, opn[13], xn[13],  yn[13], zn[13], 23'd163      , opn[14], xn[14],  yn[14],  zn[14]);
cstageg #( 14, 23, 22, def_op) cs14 ( clk, opn[14], xn[14],  yn[14], zn[14], 23'd81       , opn[15], xn[15],  yn[15],  zn[15]);
cstageg #( 15, 23, 22, def_op) cs15 ( clk, opn[15], xn[15],  yn[15], zn[15], 23'd41       , opn[16], xn[16],  yn[16],  zn[16]);
cstageg #( 16, 23, 22, def_op) cs16 ( clk, opn[16], xn[16],  yn[16], zn[16], 23'd20       , opn[17], xn[17],  yn[17],  zn[17]);
cstageg #( 17, 23, 22, def_op) cs17 ( clk, opn[17], xn[17],  yn[17], zn[17], 23'd10       , opn[18], xn[18],  yn[18],  zn[18]);
cstageg #( 18, 23, 22, def_op) cs18 ( clk, opn[18], xn[18],  yn[18], zn[18], 23'd5        , opn[19], xn[19],  yn[19],  zn[19]);
cstageg #( 19, 23, 22, def_op) cs19 ( clk, opn[19], xn[19],  yn[19], zn[19], 23'd3        , opn[20], xn[20],  yn[20],  zn[20]);
cstageg #( 20, 23, 22, def_op) cs20 ( clk, opn[20], xn[20],  yn[20], zn[20], 23'd1        , opn[21], xn[21],  yn[21],  zn[21]);
wire [21:0] xfinal = xn[nstg-1];
wire [21:0] yfinal = yn[nstg-1];
wire [22:0] zfinal = zn[nstg-1];

// round, not truncate
assign xout     = xfinal[21:22-width] + xfinal[21-width];
assign yout     = yfinal[21:22-width] + yfinal[21-width];
assign phaseout = zfinal[22:22-width] + zfinal[21-width];

endmodule
