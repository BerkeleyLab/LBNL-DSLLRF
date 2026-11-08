//-----------------------------------------------------------------------------
// AXI4 slave front end for a memory port (banked_mem port A, via wave_gen / wave_cap)
//
// Behaves like a memory, as axi_bram_ctrl does: INCR, FIXED and WRAP bursts, narrow transfers and WSTRB are
// supported, and reads return the stored data. One transaction is processed at a time (writes first); write beats go
// to the memory port at one per clock, read beats wait for the memory port's read latency. All responses are OKAY.
// The slave never waits on anything but the memory port, so the PS cannot hang on it. See doc/wave_gen.md.
//-----------------------------------------------------------------------------

module axi4_mem_port #(
    parameter AXI_DATA_WIDTH   = 256,
    parameter AXI_ADDR_WIDTH   = 18,
    parameter AXI_ID_WIDTH     = 4
) (
    input  wire                           clk,
    input  wire                           rst_n,

    // AXI4 Write Address Channel
    input  wire [AXI_ID_WIDTH-1:0]        s_axi_awid,
    input  wire [AXI_ADDR_WIDTH-1:0]      s_axi_awaddr,
    input  wire [7:0]                     s_axi_awlen,
    input  wire [2:0]                     s_axi_awsize,
    input  wire [1:0]                     s_axi_awburst,
    input  wire                           s_axi_awvalid,
    output wire                           s_axi_awready,

    // AXI4 Write Data Channel
    input  wire [AXI_DATA_WIDTH-1:0]      s_axi_wdata,
    input  wire [AXI_DATA_WIDTH/8-1:0]    s_axi_wstrb,
    input  wire                           s_axi_wlast,
    input  wire                           s_axi_wvalid,
    output wire                           s_axi_wready,

    // AXI4 Write Response Channel
    output wire [AXI_ID_WIDTH-1:0]        s_axi_bid,
    output wire [1:0]                     s_axi_bresp,
    output wire                           s_axi_bvalid,
    input  wire                           s_axi_bready,

    // AXI4 Read Address Channel
    input  wire [AXI_ID_WIDTH-1:0]        s_axi_arid,
    input  wire [AXI_ADDR_WIDTH-1:0]      s_axi_araddr,
    input  wire [7:0]                     s_axi_arlen,
    input  wire [2:0]                     s_axi_arsize,
    input  wire [1:0]                     s_axi_arburst,
    input  wire                           s_axi_arvalid,
    output wire                           s_axi_arready,

    // AXI4 Read Data Channel
    output wire [AXI_ID_WIDTH-1:0]        s_axi_rid,
    output wire [AXI_DATA_WIDTH-1:0]      s_axi_rdata,
    output wire [1:0]                     s_axi_rresp,
    output wire                           s_axi_rlast,
    output wire                           s_axi_rvalid,
    input  wire                           s_axi_rready,

    // Memory port
    output wire                           mem_wr_en,
    output wire [AXI_ADDR_WIDTH-1:0]      mem_wr_addr,
    output wire [AXI_DATA_WIDTH-1:0]      mem_wr_data,
    output wire [AXI_DATA_WIDTH/8-1:0]    mem_wr_strb,
    output wire                           mem_rd_en,
    output wire [AXI_ADDR_WIDTH-1:0]      mem_rd_addr,
    input  wire [AXI_DATA_WIDTH-1:0]      mem_rd_data,
    input  wire                           mem_rd_valid
);

    //-------------------------------------------------------------------------
    // Transaction state machine
    //-------------------------------------------------------------------------

    localparam [2:0] ST_IDLE    = 3'd0;
    localparam [2:0] ST_WDATA   = 3'd1;
    localparam [2:0] ST_WRESP   = 3'd2;
    localparam [2:0] ST_RISSUE  = 3'd3;
    localparam [2:0] ST_RWAIT   = 3'd4;
    localparam [2:0] ST_RDATA   = 3'd5;

    reg [2:0]                   state;
    reg [AXI_ID_WIDTH-1:0]      t_id;
    reg [AXI_ADDR_WIDTH-1:0]    t_addr;
    reg [7:0]                   t_len;
    reg [7:0]                   t_count;
    reg [2:0]                   t_size;
    reg [1:0]                   t_burst;
    reg [AXI_DATA_WIDTH-1:0]    r_data;

    // Address of the next beat (AXI4 A3.4.1): INCR/WRAP step from the size-aligned address; WRAP stays inside the
    // (len+1) * 2**size aligned window; FIXED repeats the address.
    function automatic [AXI_ADDR_WIDTH-1:0] next_addr;
        input [AXI_ADDR_WIDTH-1:0] addr;
        input [2:0]                size;
        input [1:0]                burst;
        input [7:0]                len;
        reg   [AXI_ADDR_WIDTH-1:0] incr, aligned, wrap_mask;
        begin
            incr      = {{(AXI_ADDR_WIDTH-1){1'b0}}, 1'b1} << size;
            aligned   = addr & ~(incr - 1'b1);
            wrap_mask = ({{(AXI_ADDR_WIDTH-9){1'b0}}, ({1'b0, len} + 9'd1)} << size) - 1'b1;
            case (burst)
                2'b01:   next_addr = aligned + incr;                                            // INCR
                2'b10:   next_addr = (addr & ~wrap_mask) | ((aligned + incr) & wrap_mask);     // WRAP
                default: next_addr = addr;                                                      // FIXED
            endcase
        end
    endfunction

    wire aw_take = (state == ST_IDLE) && s_axi_awvalid;
    wire ar_take = (state == ST_IDLE) && !s_axi_awvalid && s_axi_arvalid;
    wire w_beat  = (state == ST_WDATA) && s_axi_wvalid;
    wire w_last  = (t_count == t_len);
    wire r_beat  = (state == ST_RDATA) && s_axi_rready;
    wire r_last  = (t_count == t_len);

    assign s_axi_awready = (state == ST_IDLE);
    assign s_axi_wready  = (state == ST_WDATA);
    assign s_axi_bid     = t_id;
    assign s_axi_bresp   = 2'b00;  // OKAY
    assign s_axi_bvalid  = (state == ST_WRESP);

    assign s_axi_arready = (state == ST_IDLE) && !s_axi_awvalid;
    assign s_axi_rid     = t_id;
    assign s_axi_rdata   = r_data;
    assign s_axi_rresp   = 2'b00;  // OKAY
    assign s_axi_rlast   = (state == ST_RDATA) && r_last;
    assign s_axi_rvalid  = (state == ST_RDATA);

    always @(posedge clk) begin
        if (!rst_n) begin
            state   <= ST_IDLE;
            t_id    <= {AXI_ID_WIDTH{1'b0}};
            t_addr  <= {AXI_ADDR_WIDTH{1'b0}};
            t_len   <= 8'd0;
            t_count <= 8'd0;
            t_size  <= 3'd0;
            t_burst <= 2'd0;
            r_data  <= {AXI_DATA_WIDTH{1'b0}};
        end else begin
            case (state)
                ST_IDLE: begin
                    t_count <= 8'd0;
                    if (aw_take) begin
                        state   <= ST_WDATA;
                        t_id    <= s_axi_awid;
                        t_addr  <= s_axi_awaddr;
                        t_len   <= s_axi_awlen;
                        t_size  <= s_axi_awsize;
                        t_burst <= s_axi_awburst;
                    end else if (ar_take) begin
                        state   <= ST_RISSUE;
                        t_id    <= s_axi_arid;
                        t_addr  <= s_axi_araddr;
                        t_len   <= s_axi_arlen;
                        t_size  <= s_axi_arsize;
                        t_burst <= s_axi_arburst;
                    end
                end

                ST_WDATA: begin
                    if (w_beat) begin
                        t_addr  <= next_addr(t_addr, t_size, t_burst, t_len);
                        t_count <= t_count + 8'd1;
                        if (w_last) state <= ST_WRESP;   // WLAST is not needed: AWLEN defines the burst
                    end
                end

                ST_WRESP: begin
                    if (s_axi_bready) state <= ST_IDLE;
                end

                ST_RISSUE: state <= ST_RWAIT;

                ST_RWAIT: begin
                    if (mem_rd_valid) begin
                        r_data <= mem_rd_data;
                        state  <= ST_RDATA;
                    end
                end

                ST_RDATA: begin
                    if (r_beat) begin
                        if (r_last) begin
                            state <= ST_IDLE;
                        end else begin
                            t_addr  <= next_addr(t_addr, t_size, t_burst, t_len);
                            t_count <= t_count + 8'd1;
                            state   <= ST_RISSUE;
                        end
                    end
                end

                default: state <= ST_IDLE;
            endcase
        end
    end


    assign mem_wr_en   = w_beat;
    assign mem_wr_addr = t_addr;
    assign mem_wr_data = s_axi_wdata;
    assign mem_wr_strb = s_axi_wstrb;
    assign mem_rd_en   = (state == ST_RISSUE);
    assign mem_rd_addr = t_addr;

endmodule
