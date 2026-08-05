//-----------------------------------------------------------------------------
// Parameterized Waveform Generator
// Supports arbitrary AXI input width (256/512) and output width (320/448/etc)
// All widths must be multiples of GRANULE (default 64 bits)
//-----------------------------------------------------------------------------

// Write Sequence (256→320):
//                     ___     ___     ___     ___     ___     ___     ___
//     clk          __|   |___|   |___|   |___|   |___|   |___|   |___|   |___
//                     _______________________________________
//     axi_wr_en    __|                                       |_______________
//                     _______________________________________
//     axi_wr_ready ___|                                       |______________
//     axi_wr_data     │ D0  │ D1  │ D2  │ D3  │ D4  │ D5  │
//     wr_count        │  4  │  8  │  7  │  6  │  5  │  4  │  8  │
//                                   ▲           ▲           ▲
//     wr_sample_ready ______________|___________|___________|________________
//     wr_sample_addr  │  0  │  0  │  1  │  2  │  3  │  3  │  4  │

// Read Sequence (READ_LATENCY=2):
//                     ___     ___     ___     ___     ___     ___     ___
//     clk          __|   |___|   |___|   |___|   |___|   |___|   |___|   |___
//                     _______
//     trigger      __|       |_______________________________________________
//                             _______________________________________________
//     rd_running   __________|
//                             ___________________________________________
//     rd_active    __________|                                           |___
//     rd_addr         │  X  │  0  │  1  │  2  │  3  │ ... │  N  │  N  │
//     rd_valid_pipe[0]│  0  │  1  │  1  │  1  │  1  │ ... │  1  │  0  │
//     rd_valid_pipe[2]│  0  │  0  │  0  │  1  │  1  │ ... │  1  │  1  │
//     (m_axis_tvalid)                       ▲
//                               READ_LATENCY cycles
//     m_axis_tdata    │  X  │  X  │  X  │ S0  │ S1  │ ... │SN-1 │ SN  │

module wave_gen #(
    parameter AXI_DATA_WIDTH   = 256,    // 256 or 512
    parameter OUT_DATA_WIDTH   = 320,    // 320, 448, or any multiple of GRANULE
    parameter GRANULE          = 64,     // Base granularity (should be GCD of widths)
    parameter BANK_DEPTH       = 4096,   // Samples per bank
    parameter READ_LATENCY     = 3,      // Pipeline stages for read
    parameter RAM_STYLE        = "ultra" // "ultra" or "block"
) (
    input  wire                              clk,
    input  wire                              rst_n,

    // AXI Write Interface
    input  wire                              axi_wr_en,
    input  wire [AXI_ADDR_WIDTH-1:0]         axi_wr_addr,
    input  wire [AXI_DATA_WIDTH-1:0]         axi_wr_data,
    input  wire [AXI_DATA_WIDTH/8-1:0]       axi_wr_strb,
    output wire                              axi_wr_ready,

    // Waveform Control
    input  wire                              trigger,
    input  wire [SAMPLE_ADDR_WIDTH-1:0]      wave_length,
    input  wire                              flush_wr,
    output wire                              busy,

    // Output AXI-Stream
    output wire [OUT_DATA_WIDTH-1:0]         m_axis_tdata,
    output wire                              m_axis_tvalid,
    output wire                              m_axis_tlast,
    input  wire                              m_axis_tready
);

    //-------------------------------------------------------------------------
    // Parameter Calculations
    //-------------------------------------------------------------------------

    // Granule counts
    localparam integer AXI_GRANULES      = AXI_DATA_WIDTH / GRANULE;
    localparam integer OUT_GRANULES      = OUT_DATA_WIDTH / GRANULE;
    localparam integer NUM_BANKS         = OUT_GRANULES;
    localparam integer BANK_WIDTH        = GRANULE;

    // Address widths
    localparam integer SAMPLE_ADDR_WIDTH = $clog2(BANK_DEPTH);
    localparam integer AXI_ADDR_WIDTH    = SAMPLE_ADDR_WIDTH + $clog2(OUT_DATA_WIDTH/8);

    // Accumulator sizing: must hold residual + new input
    // Worst case residual is (OUT_GRANULES - 1) granules
    localparam integer ACC_GRANULES      = AXI_GRANULES + OUT_GRANULES;
    localparam integer ACC_WIDTH         = ACC_GRANULES * GRANULE;
    localparam integer COUNT_WIDTH       = $clog2(ACC_GRANULES + 1);

    //-------------------------------------------------------------------------
    // Internal Signals
    //-------------------------------------------------------------------------

    // Write path
    reg [ACC_WIDTH-1:0]          wr_accum;
    reg [COUNT_WIDTH-1:0]        wr_count;
    reg [SAMPLE_ADDR_WIDTH-1:0]  wr_sample_addr;
    reg                          wr_active;

    wire                         wr_can_accept;
    wire                         wr_sample_ready;
    wire [OUT_DATA_WIDTH-1:0]    wr_sample_data;

    // Read path
    reg [SAMPLE_ADDR_WIDTH-1:0]  rd_addr;
    reg [SAMPLE_ADDR_WIDTH-1:0]  rd_length;
    reg                          rd_running;
    reg                          rd_active;
    reg [READ_LATENCY-1:0]       rd_valid_pipe;
    reg [READ_LATENCY-1:0]       rd_last_pipe;

    // Bank interface signals
    wire [SAMPLE_ADDR_WIDTH-1:0] bank_wr_addr;
    wire [SAMPLE_ADDR_WIDTH-1:0] bank_rd_addr;
    wire                         bank_wr_en;
    wire [BANK_WIDTH-1:0]        bank_wr_data [0:NUM_BANKS-1];
    wire [BANK_WIDTH-1:0]        bank_rd_data [0:NUM_BANKS-1];
    reg  [BANK_WIDTH-1:0]        bank_rd_pipe [0:NUM_BANKS-1][0:READ_LATENCY-1];

    //-------------------------------------------------------------------------
    // Generate Individual Bank Memories
    // Each bank is a separate memory to avoid Vivado size limits
    //-------------------------------------------------------------------------

    genvar g;
    generate
        for (g = 0; g < NUM_BANKS; g = g + 1) begin : gen_banks

            // Bank memory declaration
            if (RAM_STYLE == "ultra") begin : gen_ultra
                (* ram_style = "ultra" *)
                reg [BANK_WIDTH-1:0] mem [0:BANK_DEPTH-1];

                // Write port
                always @(posedge clk) begin
                    if (bank_wr_en) begin
                        mem[bank_wr_addr] <= bank_wr_data[g];
                    end
                end

                // Read port
                reg [BANK_WIDTH-1:0] rd_data_reg;
                always @(posedge clk) begin
                    rd_data_reg <= mem[bank_rd_addr];
                end
                assign bank_rd_data[g] = rd_data_reg;

            end else begin : gen_block
                (* ram_style = "block" *)
                reg [BANK_WIDTH-1:0] mem [0:BANK_DEPTH-1];

                // Write port
                always @(posedge clk) begin
                    if (bank_wr_en) begin
                        mem[bank_wr_addr] <= bank_wr_data[g];
                    end
                end

                // Read port
                reg [BANK_WIDTH-1:0] rd_data_reg;
                always @(posedge clk) begin
                    rd_data_reg <= mem[bank_rd_addr];
                end
                assign bank_rd_data[g] = rd_data_reg;
            end

            // Extract write data for this bank from sample data
            assign bank_wr_data[g] = wr_sample_data[g*BANK_WIDTH +: BANK_WIDTH];

            // Read pipeline for this bank
            integer j;
            always @(posedge clk) begin
                bank_rd_pipe[g][0] <= bank_rd_data[g];
                for (j = 1; j < READ_LATENCY; j = j + 1) begin
                    bank_rd_pipe[g][j] <= bank_rd_pipe[g][j-1];
                end
            end

            // Output data assignment
            if (READ_LATENCY > 1) begin : gen_pipe_out
                assign m_axis_tdata[g*BANK_WIDTH +: BANK_WIDTH] = bank_rd_pipe[g][READ_LATENCY-2];
            end else begin : gen_direct_out
                assign m_axis_tdata[g*BANK_WIDTH +: BANK_WIDTH] = bank_rd_data[g];
            end

        end
    endgenerate

    //-------------------------------------------------------------------------
    // Bank Control Signals
    //-------------------------------------------------------------------------

    assign bank_wr_addr = wr_sample_addr;
    assign bank_rd_addr = rd_addr;
    assign bank_wr_en   = wr_sample_ready || (flush_wr && wr_active && (wr_count > 0) && !wr_sample_ready);

    //-------------------------------------------------------------------------
    // Write Gearbox: AXI -> Sample Width Conversion
    //-------------------------------------------------------------------------

    reg                          wr_draining;  // Draining accumulator after last AXI write
    wire                         wr_input_valid;

    assign wr_can_accept   = (wr_count <= (ACC_GRANULES - AXI_GRANULES));
    assign axi_wr_ready    = wr_can_accept && !rd_running && !wr_draining;
    assign wr_sample_ready = (wr_count >= OUT_GRANULES);
    assign wr_sample_data  = wr_accum[OUT_DATA_WIDTH-1:0];
    assign wr_input_valid  = axi_wr_en && axi_wr_ready;

    always @(posedge clk) begin
        if (!rst_n) begin
            wr_accum       <= {ACC_WIDTH{1'b0}};
            wr_count       <= {COUNT_WIDTH{1'b0}};
            wr_sample_addr <= {SAMPLE_ADDR_WIDTH{1'b0}};
            wr_active      <= 1'b0;
            wr_draining    <= 1'b0;
        end else begin
            // Start draining when flush is asserted
            if (flush_wr && wr_active && !wr_draining) begin
                 wr_draining <= 1'b1;
            end

            // Reset write state on address 0
            if (axi_wr_en && axi_wr_ready && (axi_wr_addr == {AXI_ADDR_WIDTH{1'b0}})) begin
                wr_accum       <= {{(ACC_WIDTH-AXI_DATA_WIDTH){1'b0}}, axi_wr_data};
                wr_count       <= AXI_GRANULES[COUNT_WIDTH-1:0];
                wr_sample_addr <= {SAMPLE_ADDR_WIDTH{1'b0}};
                wr_active      <= 1'b1;
                wr_draining    <= 1'b0;

            // Simultaneous input and output
            end else if (wr_input_valid && wr_sample_ready) begin
                wr_sample_addr <= wr_sample_addr + 1;

                // Update accumulator: shift out sample, shift in new data
                wr_accum <= {{(ACC_WIDTH-AXI_DATA_WIDTH){1'b0}}, axi_wr_data};
                wr_count <= wr_count - OUT_GRANULES[COUNT_WIDTH-1:0] + AXI_GRANULES[COUNT_WIDTH-1:0];

            // Input only
            end else if (wr_input_valid) begin
                wr_accum[wr_count*GRANULE +: AXI_DATA_WIDTH] <= axi_wr_data;
                wr_count  <= wr_count + AXI_GRANULES[COUNT_WIDTH-1:0];
                wr_active <= 1'b1;

            // Drain: output full samples
            end else if (wr_sample_ready && (wr_draining || wr_active)) begin
                wr_sample_addr <= wr_sample_addr + 1;
                wr_accum <= wr_accum >> OUT_DATA_WIDTH;
                wr_count <= wr_count - OUT_GRANULES[COUNT_WIDTH-1:0];

            // Flush: write partial sample when draining and not enough for full sample
            end else if (wr_draining && (wr_count > 0) && !wr_sample_ready) begin
                wr_sample_addr <= wr_sample_addr + 1;
                wr_count       <= {COUNT_WIDTH{1'b0}};
                wr_accum       <= {ACC_WIDTH{1'b0}};
                wr_draining    <= 1'b0;
                wr_active      <= 1'b0;

            // Done draining: clear active when count reaches zero
            end else if (wr_draining && (wr_count == 0)) begin
                wr_draining <= 1'b0;
                wr_active   <= 1'b0;
            end
        end
    end

    //-------------------------------------------------------------------------
    // Read Path: Parallel Bank Read
    //-------------------------------------------------------------------------

    integer i;
    // Busy when writing or reading
    assign busy = rd_running || wr_active || wr_draining;
    // Ready for next read when output is consumed or invalid
    wire rd_advance = !m_axis_tvalid || m_axis_tready;

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
                for (i = 0; i < READ_LATENCY; i = i + 1) begin
                    rd_valid_pipe[i+1] <= rd_valid_pipe[i];
                    rd_last_pipe[i+1]  <= rd_last_pipe[i];
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
            $error("AXI_DATA_WIDTH must be multiple of GRANULE");
        if (OUT_DATA_WIDTH % GRANULE != 0)
            $error("OUT_DATA_WIDTH must be multiple of GRANULE");
        if (READ_LATENCY < 1)
            $error("READ_LATENCY must be >= 1");

        $display("================================================");
        $display("Waveform Generator Configuration");
        $display("================================================");
        $display("  AXI Width       : %0d bits (%0d granules)", AXI_DATA_WIDTH, AXI_GRANULES);
        $display("  Output Width    : %0d bits (%0d granules)", OUT_DATA_WIDTH, OUT_GRANULES);
        $display("  Granule Size    : %0d bits", GRANULE);
        $display("  Memory Banks    : %0d x %0d-bit x %0d deep", NUM_BANKS, BANK_WIDTH, BANK_DEPTH);
        $display("  Accumulator     : %0d bits (%0d granules)", ACC_WIDTH, ACC_GRANULES);
        $display("  Read Latency    : %0d cycles", READ_LATENCY);
        $display("  RAM style       : %s", RAM_STYLE);
        $display("================================================");
    end

endmodule