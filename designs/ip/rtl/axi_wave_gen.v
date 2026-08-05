//-----------------------------------------------------------------------------
// Wrapper with full AXI4 write interface and AXI-Stream output
//-----------------------------------------------------------------------------

module axi_wave_gen #(
    parameter AXI_DATA_WIDTH   = 256,
    parameter AXI_ADDR_WIDTH   = 18,
    parameter AXI_ID_WIDTH     = 4,
    parameter OUT_DATA_WIDTH   = 320,
    parameter GRANULE          = 64,
    parameter BANK_DEPTH       = 4096,
    parameter READ_LATENCY     = 3,
    parameter RAM_STYLE        = "ultra"
) (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 clk CLK" *)
    (* X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF s_axi:m_axis, ASSOCIATED_RESET rst_n" *)
    input  wire                           clk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 rst_n RST" *)
    (* X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *)
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

    // AXI4 Read Address Channel (stub - no read support)
    input  wire [AXI_ID_WIDTH-1:0]        s_axi_arid,
    input  wire [AXI_ADDR_WIDTH-1:0]      s_axi_araddr,
    input  wire [7:0]                     s_axi_arlen,
    input  wire [2:0]                     s_axi_arsize,
    input  wire [1:0]                     s_axi_arburst,
    input  wire                           s_axi_arvalid,
    output wire                           s_axi_arready,

    // AXI4 Read Data Channel (stub)
    output wire [AXI_ID_WIDTH-1:0]        s_axi_rid,
    output wire [AXI_DATA_WIDTH-1:0]      s_axi_rdata,
    output wire [1:0]                     s_axi_rresp,
    output wire                           s_axi_rlast,
    output wire                           s_axi_rvalid,
    input  wire                           s_axi_rready,

    // Control Interface
    input  wire                           ctrl_trigger,
    input  wire [$clog2(BANK_DEPTH)-1:0]  ctrl_wave_length,
    input  wire                           ctrl_flush,
    output wire                           ctrl_busy,

    // AXI-Stream Master Output
    output wire [OUT_DATA_WIDTH-1:0]      m_axis_tdata,
    output wire                           m_axis_tvalid,
    output wire                           m_axis_tlast,
    input  wire                           m_axis_tready
);

    //-------------------------------------------------------------------------
    // Derived Parameters
    //-------------------------------------------------------------------------

    localparam SAMPLE_ADDR_WIDTH = $clog2(BANK_DEPTH);
    localparam AXI_BYTES         = AXI_DATA_WIDTH / 8;

    //-------------------------------------------------------------------------
    // AXI Write State Machine
    //-------------------------------------------------------------------------

    localparam [1:0] WR_IDLE     = 2'b00;
    localparam [1:0] WR_DATA     = 2'b01;
    localparam [1:0] WR_RESP     = 2'b10;

    reg [1:0]                   wr_state;
    reg [AXI_ID_WIDTH-1:0]      wr_id;
    reg [AXI_ADDR_WIDTH-1:0]    wr_addr;
    reg [7:0]                   wr_len;
    reg [7:0]                   wr_count;
    reg [2:0]                   wr_size;
    reg [1:0]                   wr_burst;

    // Internal write interface to waveform generator
    wire                        int_wr_en;
    wire [AXI_ADDR_WIDTH-1:0]   int_wr_addr;
    wire [AXI_DATA_WIDTH-1:0]   int_wr_data;
    wire [AXI_DATA_WIDTH/8-1:0] int_wr_strb;
    wire                        int_wr_ready;

    // AXI Write Channel Outputs
    assign s_axi_awready = (wr_state == WR_IDLE);
    assign s_axi_wready  = (wr_state == WR_DATA) && int_wr_ready;
    assign s_axi_bid     = wr_id;
    assign s_axi_bresp   = 2'b00;  // OKAY
    assign s_axi_bvalid  = (wr_state == WR_RESP);

    // Read channel stub (no read support)
    assign s_axi_arready = 1'b0;
    assign s_axi_rid     = {AXI_ID_WIDTH{1'b0}};
    assign s_axi_rdata   = {AXI_DATA_WIDTH{1'b0}};
    assign s_axi_rresp   = 2'b00;
    assign s_axi_rlast   = 1'b0;
    assign s_axi_rvalid  = 1'b0;

    // Internal write signals
    assign int_wr_en   = (wr_state == WR_DATA) && s_axi_wvalid && int_wr_ready;
    assign int_wr_addr = wr_addr;
    assign int_wr_data = s_axi_wdata;
    assign int_wr_strb = s_axi_wstrb;

    // Calculate address increment based on burst type and size
    function automatic [AXI_ADDR_WIDTH-1:0] next_addr;
        input [AXI_ADDR_WIDTH-1:0] addr;
        input [2:0] size;
        input [1:0] burst;
        begin
            case (burst)
                2'b00: next_addr = addr;                           // FIXED
                2'b01: next_addr = addr + (1 << size);             // INCR
                2'b10: next_addr = addr + (1 << size);             // WRAP (simplified)
                default: next_addr = addr;
            endcase
        end
    endfunction

    // Write state machine
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            wr_state <= WR_IDLE;
            wr_id    <= {AXI_ID_WIDTH{1'b0}};
            wr_addr  <= {AXI_ADDR_WIDTH{1'b0}};
            wr_len   <= 8'd0;
            wr_count <= 8'd0;
            wr_size  <= 3'd0;
            wr_burst <= 2'd0;
        end else begin
            case (wr_state)
                WR_IDLE: begin
                    if (s_axi_awvalid && s_axi_awready) begin
                        wr_state <= WR_DATA;
                        wr_id    <= s_axi_awid;
                        wr_addr  <= s_axi_awaddr;
                        wr_len   <= s_axi_awlen;
                        wr_count <= 8'd0;
                        wr_size  <= s_axi_awsize;
                        wr_burst <= s_axi_awburst;
                    end
                end

                WR_DATA: begin
                    if (s_axi_wvalid && s_axi_wready) begin
                        wr_addr  <= next_addr(wr_addr, wr_size, wr_burst);
                        wr_count <= wr_count + 1;

                        if (s_axi_wlast || (wr_count == wr_len)) begin
                            wr_state <= WR_RESP;
                        end
                    end
                end

                WR_RESP: begin
                    if (s_axi_bvalid && s_axi_bready) begin
                        wr_state <= WR_IDLE;
                    end
                end

                default: wr_state <= WR_IDLE;
            endcase
        end
    end

    //-------------------------------------------------------------------------
    // Waveform Generator Instance
    //-------------------------------------------------------------------------

    wave_gen #(
        .AXI_DATA_WIDTH (AXI_DATA_WIDTH),
        .OUT_DATA_WIDTH (OUT_DATA_WIDTH),
        .GRANULE        (GRANULE),
        .BANK_DEPTH     (BANK_DEPTH),
        .READ_LATENCY   (READ_LATENCY),
        .RAM_STYLE      (RAM_STYLE)
    ) u_wave_gen (
        .clk            (clk),
        .rst_n          (rst_n),

        .axi_wr_en      (int_wr_en),
        .axi_wr_addr    (int_wr_addr),
        .axi_wr_data    (int_wr_data),
        .axi_wr_strb    (int_wr_strb),
        .axi_wr_ready   (int_wr_ready),

        .trigger        (ctrl_trigger),
        .wave_length    (ctrl_wave_length),
        .flush_wr       (ctrl_flush),
        .busy           (ctrl_busy),

        .m_axis_tdata   (m_axis_tdata),
        .m_axis_tvalid  (m_axis_tvalid),
        .m_axis_tlast   (m_axis_tlast),
        .m_axis_tready  (m_axis_tready)
    );

endmodule