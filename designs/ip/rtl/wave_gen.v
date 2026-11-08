//-----------------------------------------------------------------------------
// Parameterized Waveform Generator
//
// The waveform memory is NUM_BANKS = OUT_DATA_WIDTH / GRANULE banks, each GRANULE bits wide and BANK_DEPTH deep.
// Output word r (one AXI-Stream beat, OUT_DATA_WIDTH bits) is row r of all banks read in parallel.
//
// The AXI side sees the waveform as a flat byte array in output order. Granule G (bytes GRANULE/8*G and up) lives at
//     bank = G mod NUM_BANKS, row = G div NUM_BANKS.
// An AXI beat carries AXI_GRANULES consecutive granules; with AXI_GRANULES <= NUM_BANKS they fall into distinct banks
// (rows r and r+1), so each beat is written in one cycle, honouring WSTRB, at any address, size and order. The width
// conversion is therefore done by the address mapping, not by a gearbox, and the memory port never back-pressures.
// See doc/wave_gen.md for the design notes.
//
// Memory port (AXI side, bank port A): one write *or* read per cycle (write wins if both are requested), byte
// addressed; the beat-aligned address is used and WSTRB selects the bytes, so narrow transfers work. Reads return the
// full beat after RD_LATENCY cycles. Requests are processed in order, so a read after a write returns the new data.
//
// Playback (bank port B): on trigger, rows 0 .. wave_length-1 are streamed on m_axis with back-pressure; tlast marks
// the last row. wave_length = 0 plays BANK_DEPTH rows. Writes are accepted during playback and take effect on rows
// not yet read.
//-----------------------------------------------------------------------------

module wave_gen #(
    parameter AXI_DATA_WIDTH   = 256,    // power of 2, <= OUT_DATA_WIDTH
    parameter OUT_DATA_WIDTH   = 320,    // multiple of GRANULE
    parameter GRANULE          = 64,     // bank width; multiple of 8
    parameter BANK_DEPTH       = 4096,   // rows (output words); power of 2
    parameter READ_LATENCY     = 3,      // playback pipeline stages (>= 1)
    parameter RAM_STYLE        = "ultra" // "ultra" or "block"
) (
    input  wire                              clk,
    input  wire                              rst_n,

    // Memory port (AXI side)
    input  wire                              axi_wr_en,
    input  wire [AXI_ADDR_WIDTH-1:0]         axi_wr_addr,
    input  wire [AXI_DATA_WIDTH-1:0]         axi_wr_data,
    input  wire [AXI_DATA_WIDTH/8-1:0]       axi_wr_strb,
    output wire                              axi_wr_ready,   // always 1
    input  wire                              axi_rd_en,
    input  wire [AXI_ADDR_WIDTH-1:0]         axi_rd_addr,
    output reg  [AXI_DATA_WIDTH-1:0]         axi_rd_data,
    output reg                               axi_rd_valid,

    // Waveform Control
    input  wire                              trigger,
    input  wire [SAMPLE_ADDR_WIDTH-1:0]      wave_length,
    output wire                              busy,           // playback running

    // Output AXI-Stream
    output wire [OUT_DATA_WIDTH-1:0]         m_axis_tdata,
    output wire                              m_axis_tvalid,
    output wire                              m_axis_tlast,
    input  wire                              m_axis_tready
);

    //-------------------------------------------------------------------------
    // Parameter Calculations
    //-------------------------------------------------------------------------

    localparam integer AXI_GRANULES      = AXI_DATA_WIDTH / GRANULE;   // lanes per AXI beat
    localparam integer OUT_GRANULES      = OUT_DATA_WIDTH / GRANULE;
    localparam integer NUM_BANKS         = OUT_GRANULES;
    localparam integer BANK_WIDTH        = GRANULE;
    localparam integer GB                = GRANULE / 8;                // bytes per granule
    localparam integer AXI_BYTES         = AXI_DATA_WIDTH / 8;

    localparam integer SAMPLE_ADDR_WIDTH = $clog2(BANK_DEPTH);
    localparam integer AXI_ADDR_WIDTH    = SAMPLE_ADDR_WIDTH + $clog2(OUT_DATA_WIDTH/8);
    localparam integer BEAT_LSB          = $clog2(AXI_BYTES);
    localparam integer GIDX_WIDTH        = AXI_ADDR_WIDTH - $clog2(GB); // granule index width
    localparam integer ROW_WIDTH         = GIDX_WIDTH;                  // row before range check
    localparam integer BANK_IDX_WIDTH    = $clog2(NUM_BANKS + 1);
    localparam integer LANE_WIDTH        = (AXI_GRANULES > 1) ? $clog2(AXI_GRANULES) : 1;

    // Exact division by NUM_BANKS for x < 2**GIDX_WIDTH: x / N == (x * RECIP) >> RECIP_SHIFT,
    // with RECIP_SHIFT = GIDX_WIDTH + ceil(log2 N) and RECIP = floor(2**RECIP_SHIFT / N) + 1.
    localparam integer RECIP_SHIFT       = GIDX_WIDTH + $clog2(NUM_BANKS);
    localparam integer RECIP             = (1 << RECIP_SHIFT) / NUM_BANKS + 1;
    localparam integer RECIP_WIDTH       = RECIP_SHIFT + 1;
    localparam [RECIP_WIDTH-1:0] RECIP_V = RECIP;

    // Memory-port pipeline: s1 inputs, s2 row0 (divide), s3 bank0, s4 bank port regs, s5 RAM, s6 RAM out reg,
    // s7 assembled read data
    localparam integer RD_LATENCY        = 7;

    //-------------------------------------------------------------------------
    // Memory port pipeline
    //-------------------------------------------------------------------------

    assign axi_wr_ready = 1'b1;

    wire                      op_en   = axi_wr_en || axi_rd_en;
    wire                      op_we   = axi_wr_en;
    wire [AXI_ADDR_WIDTH-1:0] op_addr = axi_wr_en ? axi_wr_addr : axi_rd_addr;

    // s1: register the request; granule index of the beat-aligned address
    reg                         s1_en, s1_we;
    reg  [GIDX_WIDTH-1:0]       s1_gidx;
    reg  [AXI_DATA_WIDTH-1:0]   s1_data;
    reg  [AXI_BYTES-1:0]        s1_strb;

    always @(posedge clk) begin
        s1_en   <= rst_n && op_en;
        s1_we   <= op_we;
        s1_gidx <= (op_addr >> BEAT_LSB) * AXI_GRANULES;
        s1_data <= axi_wr_data;
        s1_strb <= op_we ? axi_wr_strb : {AXI_BYTES{1'b0}};
    end

    // s2: row0 = gidx / NUM_BANKS
    reg                         s2_en, s2_we;
    reg  [GIDX_WIDTH-1:0]       s2_gidx;
    reg  [ROW_WIDTH-1:0]        s2_row0;
    reg  [AXI_DATA_WIDTH-1:0]   s2_data;
    reg  [AXI_BYTES-1:0]        s2_strb;
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
    reg  [ROW_WIDTH-1:0]        s3_row0;
    reg  [BANK_IDX_WIDTH-1:0]   s3_bank0;
    reg  [AXI_DATA_WIDTH-1:0]   s3_data;
    reg  [AXI_BYTES-1:0]        s3_strb;
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
    reg  [SAMPLE_ADDR_WIDTH-1:0] a_addr [0:NUM_BANKS-1];
    reg  [BANK_WIDTH-1:0]       a_din   [0:NUM_BANKS-1];
    wire [BANK_WIDTH-1:0]       a_dout  [0:NUM_BANKS-1];

    // Read-data assembly: lane l of the beat comes from bank (bank0 + l) mod NUM_BANKS
    reg  [BANK_IDX_WIDTH-1:0]   s4_bank0, s5_bank0, s6_bank0;
    reg                         s4_rd, s5_rd, s6_rd;

    genvar g;
    generate
        for (g = 0; g < NUM_BANKS; g = g + 1) begin : gen_port_a
            wire                      wrap = (g < s3_bank0);
            wire [BANK_IDX_WIDTH-1:0] lane = wrap ? (g + NUM_BANKS - s3_bank0) : (g - s3_bank0);
            wire                      hit  = (lane < AXI_GRANULES);
            wire [ROW_WIDTH-1:0]      row  = s3_row0 + wrap;
            wire                      in_range = (row < BANK_DEPTH);
            wire [LANE_WIDTH-1:0]     l    = lane[LANE_WIDTH-1:0];

            always @(posedge clk) begin
                a_en[g]   <= rst_n && s3_en && hit && in_range;
                a_we[g]   <= (s3_we && hit && in_range) ? s3_strb[l*GB +: GB] : {GB{1'b0}};
                a_addr[g] <= row[SAMPLE_ADDR_WIDTH-1:0];
                a_din[g]  <= s3_data[l*BANK_WIDTH +: BANK_WIDTH];
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
        axi_rd_valid <= rst_n && s6_rd;
        for (k = 0; k < AXI_GRANULES; k = k + 1) begin
            axi_rd_data[k*BANK_WIDTH +: BANK_WIDTH] <= a_dout[(s6_bank0 + k) % NUM_BANKS];
        end
    end

    //-------------------------------------------------------------------------
    // Playback (port B)
    //-------------------------------------------------------------------------

    reg [SAMPLE_ADDR_WIDTH-1:0]  rd_addr;
    reg [SAMPLE_ADDR_WIDTH-1:0]  rd_length;
    reg                          rd_running;
    reg                          rd_active;
    reg [READ_LATENCY-1:0]       rd_valid_pipe;
    reg [READ_LATENCY-1:0]       rd_last_pipe;
    wire [BANK_WIDTH-1:0]        b_dout [0:NUM_BANKS-1];
    reg  [BANK_WIDTH-1:0]        b_pipe [0:NUM_BANKS-1][0:READ_LATENCY-1];

    // Ready for next read when output is consumed or invalid
    wire rd_advance = !m_axis_tvalid || m_axis_tready;

    //-------------------------------------------------------------------------
    // Bank memories: port A byte-write / read (no-change), port B read
    //-------------------------------------------------------------------------

    generate
        for (g = 0; g < NUM_BANKS; g = g + 1) begin : gen_banks
            reg [BANK_WIDTH-1:0] a_q, a_q2, b_q;
            integer c;

            if (RAM_STYLE == "ultra") begin : gen_ultra
                (* ram_style = "ultra" *)
                reg [BANK_WIDTH-1:0] mem [0:BANK_DEPTH-1];

                always @(posedge clk) begin
                    if (a_en[g]) begin
                        for (c = 0; c < GB; c = c + 1)
                            if (a_we[g][c]) mem[a_addr[g]][c*8 +: 8] <= a_din[g][c*8 +: 8];
                        if (~|a_we[g]) a_q <= mem[a_addr[g]];
                    end
                end

                always @(posedge clk) begin
                    if (rd_advance) b_q <= mem[rd_addr];
                end
            end else begin : gen_block
                (* ram_style = "block" *)
                reg [BANK_WIDTH-1:0] mem [0:BANK_DEPTH-1];

                always @(posedge clk) begin
                    if (a_en[g]) begin
                        for (c = 0; c < GB; c = c + 1)
                            if (a_we[g][c]) mem[a_addr[g]][c*8 +: 8] <= a_din[g][c*8 +: 8];
                        if (~|a_we[g]) a_q <= mem[a_addr[g]];
                    end
                end

                always @(posedge clk) begin
                    if (rd_advance) b_q <= mem[rd_addr];
                end
            end

            // Port A output register (s6)
            always @(posedge clk) a_q2 <= a_q;
            assign a_dout[g] = a_q2;

            // Port B pipeline with back-pressure
            assign b_dout[g] = b_q;
            integer j;
            always @(posedge clk) begin
                if (rd_advance) begin
                    b_pipe[g][0] <= b_dout[g];
                    for (j = 1; j < READ_LATENCY; j = j + 1)
                        b_pipe[g][j] <= b_pipe[g][j-1];
                end
            end

            if (READ_LATENCY > 1) begin : gen_pipe_out
                assign m_axis_tdata[g*BANK_WIDTH +: BANK_WIDTH] = b_pipe[g][READ_LATENCY-2];
            end else begin : gen_direct_out
                assign m_axis_tdata[g*BANK_WIDTH +: BANK_WIDTH] = b_dout[g];
            end
        end
    endgenerate

    //-------------------------------------------------------------------------
    // Playback control
    //-------------------------------------------------------------------------

    integer i;
    assign busy = rd_running;

    always @(posedge clk) begin
        if (!rst_n) begin
            rd_addr       <= {SAMPLE_ADDR_WIDTH{1'b0}};
            rd_length     <= {SAMPLE_ADDR_WIDTH{1'b0}};
            rd_running    <= 1'b0;
            rd_active     <= 1'b0;
            rd_valid_pipe <= {(READ_LATENCY){1'b0}};
            rd_last_pipe  <= {(READ_LATENCY){1'b0}};
        end else begin
            // Start on trigger (only when not busy)
            if (trigger && !busy) begin
                rd_running <= 1'b1;
                rd_active  <= 1'b1;
                rd_addr    <= {SAMPLE_ADDR_WIDTH{1'b0}};
                rd_length  <= wave_length;
            end

            // Read with backpressure
            if (rd_active && rd_advance) begin
                rd_valid_pipe[0] <= 1'b1;
                rd_last_pipe[0]  <= (rd_addr == rd_length - 1);

                if (rd_addr == rd_length - 1) begin
                    rd_active <= 1'b0;
                end else begin
                    rd_addr <= rd_addr + 1;
                end
            end else if (rd_advance) begin
                rd_valid_pipe[0] <= 1'b0;
                rd_last_pipe[0]  <= 1'b0;
            end
            // Pipeline with backpressure support
            if (rd_advance) begin
                for (i = 1; i < READ_LATENCY; i = i + 1) begin
                    rd_valid_pipe[i] <= rd_valid_pipe[i-1];
                    rd_last_pipe[i]  <= rd_last_pipe[i-1];
                end
            end

            // Clear running on last output
            if (m_axis_tvalid && m_axis_tready && m_axis_tlast) begin
                rd_running <= 1'b0;
            end
        end
    end

    assign m_axis_tvalid = rd_valid_pipe[READ_LATENCY-1];
    assign m_axis_tlast  = rd_last_pipe[READ_LATENCY-1];

    //-------------------------------------------------------------------------
    // Parameter Validation
    //-------------------------------------------------------------------------

    initial begin
        if (AXI_DATA_WIDTH % GRANULE != 0)
            $error("AXI_DATA_WIDTH must be a multiple of GRANULE");
        if (OUT_DATA_WIDTH % GRANULE != 0)
            $error("OUT_DATA_WIDTH must be a multiple of GRANULE");
        if (GRANULE % 8 != 0)
            $error("GRANULE must be a multiple of 8");
        if (AXI_GRANULES > NUM_BANKS)
            $error("AXI_DATA_WIDTH must not exceed OUT_DATA_WIDTH (one lane per bank per beat)");
        if ((1 << $clog2(AXI_GRANULES)) != AXI_GRANULES)
            $error("AXI_DATA_WIDTH / GRANULE must be a power of 2");
        if ((1 << SAMPLE_ADDR_WIDTH) != BANK_DEPTH)
            $error("BANK_DEPTH must be a power of 2");
        if (READ_LATENCY < 1)
            $error("READ_LATENCY must be >= 1");
        if (RECIP_SHIFT > 30)
            $error("Address too wide for the 32-bit reciprocal constant");
    end

endmodule
