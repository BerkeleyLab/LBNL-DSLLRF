//-----------------------------------------------------------------------------
// Wrapper with a full AXI4 slave (memory-mapped waveform buffer) and AXI-Stream output
//
// axi4_mem_port (AXI4 memory slave: bursts, narrow transfers, WSTRB, reads) in front of wave_gen. The slave never
// waits on playback, so the PS cannot hang on it. See doc/wave_gen.md.
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

    // Control Interface
    input  wire                           ctrl_trigger,
    input  wire [$clog2(BANK_DEPTH)-1:0]  ctrl_wave_length,
    output wire                           ctrl_busy,

    // AXI-Stream Master Output
    output wire [OUT_DATA_WIDTH-1:0]      m_axis_tdata,
    output wire                           m_axis_tvalid,
    output wire                           m_axis_tlast,
    input  wire                           m_axis_tready
);

    localparam CORE_ADDR_WIDTH = $clog2(BANK_DEPTH) + $clog2(OUT_DATA_WIDTH/8);

    wire                        mem_wr_en, mem_rd_en, mem_rd_valid;
    wire [AXI_ADDR_WIDTH-1:0]   mem_wr_addr, mem_rd_addr;
    wire [AXI_DATA_WIDTH-1:0]   mem_wr_data, mem_rd_data;
    wire [AXI_DATA_WIDTH/8-1:0] mem_wr_strb;

    axi4_mem_port #(
        .AXI_DATA_WIDTH (AXI_DATA_WIDTH),
        .AXI_ADDR_WIDTH (AXI_ADDR_WIDTH),
        .AXI_ID_WIDTH   (AXI_ID_WIDTH)
    ) u_axi (
        .clk(clk), .rst_n(rst_n),
        .s_axi_awid(s_axi_awid), .s_axi_awaddr(s_axi_awaddr), .s_axi_awlen(s_axi_awlen), .s_axi_awsize(s_axi_awsize),
        .s_axi_awburst(s_axi_awburst), .s_axi_awvalid(s_axi_awvalid), .s_axi_awready(s_axi_awready),
        .s_axi_wdata(s_axi_wdata), .s_axi_wstrb(s_axi_wstrb), .s_axi_wlast(s_axi_wlast), .s_axi_wvalid(s_axi_wvalid),
        .s_axi_wready(s_axi_wready),
        .s_axi_bid(s_axi_bid), .s_axi_bresp(s_axi_bresp), .s_axi_bvalid(s_axi_bvalid), .s_axi_bready(s_axi_bready),
        .s_axi_arid(s_axi_arid), .s_axi_araddr(s_axi_araddr), .s_axi_arlen(s_axi_arlen), .s_axi_arsize(s_axi_arsize),
        .s_axi_arburst(s_axi_arburst), .s_axi_arvalid(s_axi_arvalid), .s_axi_arready(s_axi_arready),
        .s_axi_rid(s_axi_rid), .s_axi_rdata(s_axi_rdata), .s_axi_rresp(s_axi_rresp), .s_axi_rlast(s_axi_rlast),
        .s_axi_rvalid(s_axi_rvalid), .s_axi_rready(s_axi_rready),
        .mem_wr_en(mem_wr_en), .mem_wr_addr(mem_wr_addr), .mem_wr_data(mem_wr_data), .mem_wr_strb(mem_wr_strb),
        .mem_rd_en(mem_rd_en), .mem_rd_addr(mem_rd_addr), .mem_rd_data(mem_rd_data), .mem_rd_valid(mem_rd_valid)
    );

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
        .axi_wr_en      (mem_wr_en),
        .axi_wr_addr    (mem_wr_addr[CORE_ADDR_WIDTH-1:0]),
        .axi_wr_data    (mem_wr_data),
        .axi_wr_strb    (mem_wr_strb),
        .axi_wr_ready   (),
        .axi_rd_en      (mem_rd_en),
        .axi_rd_addr    (mem_rd_addr[CORE_ADDR_WIDTH-1:0]),
        .axi_rd_data    (mem_rd_data),
        .axi_rd_valid   (mem_rd_valid),
        .trigger        (ctrl_trigger),
        .wave_length    (ctrl_wave_length),
        .busy           (ctrl_busy),
        .play_row       (),
        .play_valid     (),
        .mode_next      (2'd0),
        .cw_iq_next     (32'd0),
        .apply          (1'b0),
        .mode           (),
        .m_axis_tdata   (m_axis_tdata),
        .m_axis_tvalid  (m_axis_tvalid),
        .m_axis_tlast   (m_axis_tlast),
        .m_axis_tready  (m_axis_tready)
    );

    initial begin
        if (AXI_ADDR_WIDTH < CORE_ADDR_WIDTH)
            $error("AXI_ADDR_WIDTH must cover the waveform memory (%0d bits)", CORE_ADDR_WIDTH);
    end

endmodule
