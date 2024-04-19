/* CORDIC operating modes for self-documentation
 * These are the 3 valid inputs for port 'opin' in
 * any generated cordic module (i.e. cordicg_bXX.v)
 */
//  opin = 0 forces theta to zero (polar to rect),
localparam [1:0] CORDIC_OP_POLAR_TO_RECT = 2'h0;
//  opin = 1 forces y to zero (rect to polar),
localparam [1:0] CORDIC_OP_RECT_TO_POLAR = 2'h1;
//  opin = 3 for follow mode
localparam [1:0] CORDIC_OP_FOLLOW_MODE   = 2'h3;
