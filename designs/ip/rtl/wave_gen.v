//-----------------------------------------------------------------------------
// Parameterized Waveform Generator
//
// The waveform lives in a banked_mem: NUM_BANKS = OUT_DATA_WIDTH / GRANULE banks of GRANULE bits, BANK_DEPTH rows.
// Output word r (one AXI-Stream beat, OUT_DATA_WIDTH bits) is row r. The bus side sees the waveform as a flat byte
// array in output order and writes it at any address, size and order (banked_mem port A); the width conversion is done
// by the address mapping, not by a gearbox, and writes never back-pressure. See doc/wave_gen.md.
//
// Memory port (bus side): one write *or* read per cycle, byte addressed, WSTRB honoured; reads return the full beat
// after 7 cycles, in order.
//
// Playback (banked_mem port B): on trigger, rows 0 .. wave_length-1 are streamed on m_axis with back-pressure; tlast
// marks the last row. wave_length = 0 plays BANK_DEPTH rows. Writes are accepted during playback and take effect on
// rows not yet read.
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

    // Memory port (bus side)
    input  wire                              axi_wr_en,
    input  wire [AXI_ADDR_WIDTH-1:0]         axi_wr_addr,
    input  wire [AXI_DATA_WIDTH-1:0]         axi_wr_data,
    input  wire [AXI_DATA_WIDTH/8-1:0]       axi_wr_strb,
    output wire                              axi_wr_ready,   // always 1
    input  wire                              axi_rd_en,
    input  wire [AXI_ADDR_WIDTH-1:0]         axi_rd_addr,
    output wire [AXI_DATA_WIDTH-1:0]         axi_rd_data,
    output wire                              axi_rd_valid,

    // Waveform Control
    input  wire                              trigger,
    input  wire [SAMPLE_ADDR_WIDTH-1:0]      wave_length,
    output wire                              busy,           // playback running
    output wire [SAMPLE_ADDR_WIDTH-1:0]      play_row,       // next row to read (debug)

    // Output AXI-Stream
    output wire [OUT_DATA_WIDTH-1:0]         m_axis_tdata,
    output wire                              m_axis_tvalid,
    output wire                              m_axis_tlast,
    input  wire                              m_axis_tready
);

    localparam integer SAMPLE_ADDR_WIDTH = $clog2(BANK_DEPTH);
    localparam integer AXI_ADDR_WIDTH    = SAMPLE_ADDR_WIDTH + $clog2(OUT_DATA_WIDTH/8);

    assign axi_wr_ready = 1'b1;

    //-------------------------------------------------------------------------
    // Playback control and pipeline
    //-------------------------------------------------------------------------

    reg [SAMPLE_ADDR_WIDTH-1:0]  rd_addr;
    reg [SAMPLE_ADDR_WIDTH-1:0]  rd_length;
    reg                          rd_running;
    reg                          rd_active;
    reg [READ_LATENCY-1:0]       rd_valid_pipe;
    reg [READ_LATENCY-1:0]       rd_last_pipe;
    wire [OUT_DATA_WIDTH-1:0]    row_q;
    reg  [OUT_DATA_WIDTH-1:0]    row_pipe [0:READ_LATENCY-1];

    // Last row index at the row-address width: wave_length = 0 gives BANK_DEPTH - 1 (play all rows). Written as
    // `rd_length - 1` in a compare, the subtraction would be done at 32 bits (0 - 1 = 0xFFFFFFFF) and the playback
    // would never end.
    wire [SAMPLE_ADDR_WIDTH-1:0] rd_last_row = rd_length - 1'b1;

    // The RAM read, data pipeline and valid/last pipeline all advance only when the output is accepted
    wire rd_advance = !m_axis_tvalid || m_axis_tready;

    banked_mem #(
        .BUS_DATA_WIDTH (AXI_DATA_WIDTH),
        .ROW_WIDTH      (OUT_DATA_WIDTH),
        .GRANULE        (GRANULE),
        .DEPTH          (BANK_DEPTH),
        .RAM_STYLE      (RAM_STYLE)
    ) u_mem (
        .clk        (clk),
        .rst_n      (rst_n),
        .a_wr_en    (axi_wr_en),
        .a_wr_addr  (axi_wr_addr),
        .a_wr_data  (axi_wr_data),
        .a_wr_strb  (axi_wr_strb),
        .a_rd_en    (axi_rd_en),
        .a_rd_addr  (axi_rd_addr),
        .a_rd_data  (axi_rd_data),
        .a_rd_valid (axi_rd_valid),
        .b_en       (rd_advance),
        .b_we       (1'b0),
        .b_addr     (rd_addr),
        .b_wdata    ({OUT_DATA_WIDTH{1'b0}}),
        .b_rdata    (row_q)
    );

    integer j;
    always @(posedge clk) begin
        if (rd_advance) begin
            row_pipe[0] <= row_q;
            for (j = 1; j < READ_LATENCY; j = j + 1)
                row_pipe[j] <= row_pipe[j-1];
        end
    end

    generate
        if (READ_LATENCY > 1) begin : gen_pipe_out
            assign m_axis_tdata = row_pipe[READ_LATENCY-2];
        end else begin : gen_direct_out
            assign m_axis_tdata = row_q;
        end
    endgenerate

    integer i;
    assign busy = rd_running;
    assign play_row = rd_addr;

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
                rd_last_pipe[0]  <= (rd_addr == rd_last_row);

                if (rd_addr == rd_last_row) begin
                    rd_active <= 1'b0;
                end else begin
                    rd_addr <= rd_addr + 1;
                end
            end else if (rd_advance) begin
                rd_valid_pipe[0] <= 1'b0;
                rd_last_pipe[0]  <= 1'b0;
            end
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

    initial begin
        if (READ_LATENCY < 1)
            $error("READ_LATENCY must be >= 1");
    end

endmodule
