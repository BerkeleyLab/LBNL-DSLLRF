//-----------------------------------------------------------------------------
// Banked memory with an address-mapped bus port and a row port
//
// NUM_BANKS = ROW_WIDTH / GRANULE banks, each GRANULE bits wide and DEPTH rows deep. Row r is row r of all banks.
// Used by wave_gen (port B reads rows for playback) and wave_cap (port B writes captured rows).
//
// Port A (bus side) sees the memory as a flat byte array in row order. Granule G (bytes GRANULE/8*G and up) lives at
//     bank = G mod NUM_BANKS, row = G div NUM_BANKS.
// A bus beat carries BUS_GRANULES consecutive granules; with BUS_GRANULES <= NUM_BANKS they fall into distinct banks
// (rows r and r+1), so a beat is written or read in one cycle. Writes honour the strobes, so any address, size and
// order works. One request per cycle (write wins if both are requested); the beat-aligned address is used. Reads return
// the full beat A_RD_LATENCY cycles later; requests are processed in order, so a read after a write sees the new data.
// The division by NUM_BANKS is an exact reciprocal multiply. See doc/wave_gen.md.
//
// Port B (row side): one full row per cycle, b_we = 1 writes b_wdata to row b_addr, b_we = 0 reads it into b_rdata
// on the next clock edge. b_rdata holds its value while b_en is low.
//-----------------------------------------------------------------------------

module banked_mem #(
    parameter BUS_DATA_WIDTH = 256,     // port A width: power of 2, <= ROW_WIDTH
    parameter ROW_WIDTH      = 320,     // port B width: multiple of GRANULE
    parameter GRANULE        = 64,      // bank width; multiple of 8
    parameter DEPTH          = 4096,    // rows; power of 2
    parameter RAM_STYLE      = "ultra", // "ultra" or "block"
    // Derived (do not override): port A byte address width and port B row address width
    parameter A_ADDR_WIDTH   = $clog2(DEPTH) + $clog2(ROW_WIDTH / 8),
    parameter B_ADDR_WIDTH   = $clog2(DEPTH)
) (
    input  wire                         clk,
    input  wire                         rst_n,

    // Port A: bus side, byte addressed
    input  wire                         a_wr_en,
    input  wire [A_ADDR_WIDTH-1:0]      a_wr_addr,
    input  wire [BUS_DATA_WIDTH-1:0]    a_wr_data,
    input  wire [BUS_DATA_WIDTH/8-1:0]  a_wr_strb,
    input  wire                         a_rd_en,
    input  wire [A_ADDR_WIDTH-1:0]      a_rd_addr,
    output reg  [BUS_DATA_WIDTH-1:0]    a_rd_data,
    output reg                          a_rd_valid,

    // Port B: row side
    input  wire                         b_en,
    input  wire                         b_we,
    input  wire [B_ADDR_WIDTH-1:0]      b_addr,
    input  wire [ROW_WIDTH-1:0]         b_wdata,
    output wire [ROW_WIDTH-1:0]         b_rdata
);

    //-------------------------------------------------------------------------
    // Parameter Calculations
    //-------------------------------------------------------------------------

    localparam integer BUS_GRANULES   = BUS_DATA_WIDTH / GRANULE;   // lanes per bus beat
    localparam integer NUM_BANKS      = ROW_WIDTH / GRANULE;
    localparam integer GB             = GRANULE / 8;                // bytes per granule
    localparam integer BUS_BYTES      = BUS_DATA_WIDTH / 8;

    localparam integer BEAT_LSB       = $clog2(BUS_BYTES);
    localparam integer GIDX_WIDTH     = A_ADDR_WIDTH - $clog2(GB);  // granule index width
    localparam integer RIDX_WIDTH     = GIDX_WIDTH;                 // row index before the range check
    localparam integer BANK_IDX_WIDTH = $clog2(NUM_BANKS + 1);
    localparam integer LANE_WIDTH     = (BUS_GRANULES > 1) ? $clog2(BUS_GRANULES) : 1;

    // Exact division by NUM_BANKS for x < 2**GIDX_WIDTH: x / N == (x * RECIP) >> RECIP_SHIFT,
    // with RECIP_SHIFT = GIDX_WIDTH + ceil(log2 N) and RECIP = floor(2**RECIP_SHIFT / N) + 1.
    localparam integer RECIP_SHIFT    = GIDX_WIDTH + $clog2(NUM_BANKS);
    localparam integer RECIP          = (1 << RECIP_SHIFT) / NUM_BANKS + 1;
    localparam integer RECIP_WIDTH    = RECIP_SHIFT + 1;
    localparam [RECIP_WIDTH-1:0] RECIP_V = RECIP;

    //-------------------------------------------------------------------------
    // Port A pipeline: s1 inputs, s2 row0 (divide), s3 bank0, s4 bank port regs, s5 RAM, s6 RAM out reg,
    // s7 assembled read data (A_RD_LATENCY = 7)
    //-------------------------------------------------------------------------

    wire                    op_en   = a_wr_en || a_rd_en;
    wire                    op_we   = a_wr_en;
    wire [A_ADDR_WIDTH-1:0] op_addr = a_wr_en ? a_wr_addr : a_rd_addr;

    // s1: register the request; granule index of the beat-aligned address
    reg                         s1_en, s1_we;
    reg  [GIDX_WIDTH-1:0]       s1_gidx;
    reg  [BUS_DATA_WIDTH-1:0]   s1_data;
    reg  [BUS_BYTES-1:0]        s1_strb;

    always @(posedge clk) begin
        s1_en   <= rst_n && op_en;
        s1_we   <= op_we;
        s1_gidx <= (op_addr >> BEAT_LSB) * BUS_GRANULES;
        s1_data <= a_wr_data;
        s1_strb <= op_we ? a_wr_strb : {BUS_BYTES{1'b0}};
    end

    // s2: row0 = gidx / NUM_BANKS
    reg                         s2_en, s2_we;
    reg  [GIDX_WIDTH-1:0]       s2_gidx;
    reg  [RIDX_WIDTH-1:0]       s2_row0;
    reg  [BUS_DATA_WIDTH-1:0]   s2_data;
    reg  [BUS_BYTES-1:0]        s2_strb;
    wire [GIDX_WIDTH+RECIP_WIDTH-1:0] s1_prod = s1_gidx * RECIP_V;

    always @(posedge clk) begin
        s2_en   <= rst_n && s1_en;
        s2_we   <= s1_we;
        s2_gidx <= s1_gidx;
        s2_row0 <= s1_prod >> RECIP_SHIFT;
        s2_data <= s1_data;
        s2_strb <= s1_strb;
    end

    // s3: bank0 = gidx - row0 * NUM_BANKS (the bank of lane 0)
    reg                         s3_en, s3_we;
    reg  [RIDX_WIDTH-1:0]       s3_row0;
    reg  [BANK_IDX_WIDTH-1:0]   s3_bank0;
    reg  [BUS_DATA_WIDTH-1:0]   s3_data;
    reg  [BUS_BYTES-1:0]        s3_strb;
    wire [GIDX_WIDTH-1:0]       s2_rem = s2_gidx - s2_row0 * NUM_BANKS;

    always @(posedge clk) begin
        s3_en    <= rst_n && s2_en;
        s3_we    <= s2_we;
        s3_row0  <= s2_row0;
        s3_bank0 <= s2_rem[BANK_IDX_WIDTH-1:0];
        s3_data  <= s2_data;
        s3_strb  <= s2_strb;
    end

    // s4: per-bank port A registers. Bank b takes lane (b - bank0) mod NUM_BANKS, in row0 if b >= bank0, else row0+1.
    reg                         a_en    [0:NUM_BANKS-1];
    reg  [GB-1:0]               a_we    [0:NUM_BANKS-1];
    reg  [B_ADDR_WIDTH-1:0]     a_addr  [0:NUM_BANKS-1];
    reg  [GRANULE-1:0]          a_din   [0:NUM_BANKS-1];
    wire [GRANULE-1:0]          a_dout  [0:NUM_BANKS-1];

    // Read-data assembly: lane l of the beat comes from bank (bank0 + l) mod NUM_BANKS
    reg  [BANK_IDX_WIDTH-1:0]   s4_bank0, s5_bank0, s6_bank0;
    reg                         s4_rd, s5_rd, s6_rd;

    genvar g;
    generate
        for (g = 0; g < NUM_BANKS; g = g + 1) begin : gen_port_a
            wire                      wrap = (g < s3_bank0);
            wire [BANK_IDX_WIDTH-1:0] lane = wrap ? (g + NUM_BANKS - s3_bank0) : (g - s3_bank0);
            wire                      hit  = (lane < BUS_GRANULES);
            wire [RIDX_WIDTH-1:0]     row  = s3_row0 + wrap;
            wire                      in_range = (row < DEPTH);
            wire [LANE_WIDTH-1:0]     l    = lane[LANE_WIDTH-1:0];

            always @(posedge clk) begin
                a_en[g]   <= rst_n && s3_en && hit && in_range;
                a_we[g]   <= (s3_we && hit && in_range) ? s3_strb[l*GB +: GB] : {GB{1'b0}};
                a_addr[g] <= row[B_ADDR_WIDTH-1:0];
                a_din[g]  <= s3_data[l*GRANULE +: GRANULE];
            end
        end
    endgenerate

    always @(posedge clk) begin
        s4_rd    <= rst_n && s3_en && !s3_we;
        s5_rd    <= rst_n && s4_rd;
        s6_rd    <= rst_n && s5_rd;
        s4_bank0 <= s3_bank0;
        s5_bank0 <= s4_bank0;
        s6_bank0 <= s5_bank0;
    end

    // s7: assemble the read beat
    integer k;
    always @(posedge clk) begin
        a_rd_valid <= rst_n && s6_rd;
        for (k = 0; k < BUS_GRANULES; k = k + 1) begin
            a_rd_data[k*GRANULE +: GRANULE] <= a_dout[(s6_bank0 + k) % NUM_BANKS];
        end
    end

    //-------------------------------------------------------------------------
    // Bank memories: port A byte-write / read (no-change), port B row write / read
    //-------------------------------------------------------------------------

    generate
        for (g = 0; g < NUM_BANKS; g = g + 1) begin : gen_banks
            reg [GRANULE-1:0] a_q, a_q2, b_q;
            integer c;

            if (RAM_STYLE == "ultra") begin : gen_ultra
                (* ram_style = "ultra" *)
                reg [GRANULE-1:0] mem [0:DEPTH-1];

                always @(posedge clk) begin
                    if (a_en[g]) begin
                        for (c = 0; c < GB; c = c + 1)
                            if (a_we[g][c]) mem[a_addr[g]][c*8 +: 8] <= a_din[g][c*8 +: 8];
                        if (~|a_we[g]) a_q <= mem[a_addr[g]];
                    end
                end

                always @(posedge clk) begin
                    if (b_en) begin
                        if (b_we) mem[b_addr] <= b_wdata[g*GRANULE +: GRANULE];
                        else      b_q <= mem[b_addr];
                    end
                end
            end else begin : gen_block
                (* ram_style = "block" *)
                reg [GRANULE-1:0] mem [0:DEPTH-1];

                always @(posedge clk) begin
                    if (a_en[g]) begin
                        for (c = 0; c < GB; c = c + 1)
                            if (a_we[g][c]) mem[a_addr[g]][c*8 +: 8] <= a_din[g][c*8 +: 8];
                        if (~|a_we[g]) a_q <= mem[a_addr[g]];
                    end
                end

                always @(posedge clk) begin
                    if (b_en) begin
                        if (b_we) mem[b_addr] <= b_wdata[g*GRANULE +: GRANULE];
                        else      b_q <= mem[b_addr];
                    end
                end
            end

            // Port A output register (s6)
            always @(posedge clk) a_q2 <= a_q;
            assign a_dout[g] = a_q2;
            assign b_rdata[g*GRANULE +: GRANULE] = b_q;
        end
    endgenerate

    //-------------------------------------------------------------------------
    // Parameter Validation
    //-------------------------------------------------------------------------

    initial begin
        if (BUS_DATA_WIDTH % GRANULE != 0)
            $error("BUS_DATA_WIDTH must be a multiple of GRANULE");
        if (ROW_WIDTH % GRANULE != 0)
            $error("ROW_WIDTH must be a multiple of GRANULE");
        if (GRANULE % 8 != 0)
            $error("GRANULE must be a multiple of 8");
        if (BUS_GRANULES > NUM_BANKS)
            $error("BUS_DATA_WIDTH must not exceed ROW_WIDTH (one lane per bank per beat)");
        if ((1 << $clog2(BUS_GRANULES)) != BUS_GRANULES)
            $error("BUS_DATA_WIDTH / GRANULE must be a power of 2");
        if ((1 << $clog2(DEPTH)) != DEPTH)
            $error("DEPTH must be a power of 2");
        if (RECIP_SHIFT > 30)
            $error("Address too wide for the 32-bit reciprocal constant");
    end

endmodule
