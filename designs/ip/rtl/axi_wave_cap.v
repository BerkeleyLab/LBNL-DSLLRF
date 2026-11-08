//-----------------------------------------------------------------------------
// Waveform capture with a full AXI4 slave: axi4_mem_port in front of wave_cap.
//
// Drop-in for adc_capture + blk_mem_gen + axi_bram_ctrl in the receiver hierarchies: the same axis_clk/axis_aresetn,
// s_axis, trigger, n_rows and write_done ports, and an AXI4 memory slave (on axis_clk) that reads the capture as a flat
// int16 array in sample order. See doc/wave_gen.md.
//
// Control/status register (32 bits) in the last beat of the AXI window, at byte offset 2**AXI_ADDR_WIDTH - 32
// (0x1FFE0 for the default 128 KiB window), above the capture memory:
//   bit 0      oneshot  (R/W, reset 0 = capture on every trigger)
//   bit 1      write 1: arm (one capture on the next trigger); read: armed
//   bit 2      done     (R, set when an armed capture completes, cleared by arm)
//   bits 31:16 capture_count (R, completed captures, wraps)
//-----------------------------------------------------------------------------

module axi_wave_cap #(
    parameter AXI_DATA_WIDTH = 256,
    parameter AXI_ADDR_WIDTH = 17,
    parameter AXI_ID_WIDTH   = 4,
    parameter ROW_WIDTH      = 320,
    parameter GRANULE        = 64,
    parameter DEPTH          = 2048,
    parameter N_ROWS_WIDTH   = 16,
    parameter RAM_STYLE      = "block"
) (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 axis_clk CLK" *)
    (* X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF s_axis:s_axi, ASSOCIATED_RESET axis_aresetn" *)
    input  wire                           axis_clk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 axis_aresetn RST" *)
    (* X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *)
    input  wire                           axis_aresetn,

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

    // Input AXI-Stream
    input  wire [ROW_WIDTH-1:0]           s_axis_tdata,
    input  wire                           s_axis_tvalid,
    output wire                           s_axis_tready,

    // Capture control (as adc_capture)
    input  wire                           trigger,     // single clock cycle pulse
    input  wire [N_ROWS_WIDTH-1:0]        n_rows,
    output wire                           write_done
);

    localparam CORE_ADDR_WIDTH = $clog2(DEPTH) + $clog2(ROW_WIDTH/8);
    localparam BEAT_LSB        = $clog2(AXI_DATA_WIDTH/8);
    localparam [AXI_ADDR_WIDTH-1:0] CSR_ADDR = {AXI_ADDR_WIDTH{1'b1}} << BEAT_LSB;   // last beat of the window

    wire                        mem_wr_en, mem_rd_en, mem_rd_valid;
    wire [AXI_ADDR_WIDTH-1:0]   mem_wr_addr, mem_rd_addr;
    wire [AXI_DATA_WIDTH-1:0]   mem_wr_data, mem_rd_data;
    wire [AXI_DATA_WIDTH/8-1:0] mem_wr_strb;

    axi4_mem_port #(
        .AXI_DATA_WIDTH (AXI_DATA_WIDTH),
        .AXI_ADDR_WIDTH (AXI_ADDR_WIDTH),
        .AXI_ID_WIDTH   (AXI_ID_WIDTH)
    ) u_axi (
        .clk(axis_clk), .rst_n(axis_aresetn),
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

    wire                        core_rd_valid;
    wire [AXI_DATA_WIDTH-1:0]   core_rd_data;
    wire csr_wr = mem_wr_en && (mem_wr_addr[AXI_ADDR_WIDTH-1:BEAT_LSB] == CSR_ADDR[AXI_ADDR_WIDTH-1:BEAT_LSB]);
    wire csr_rd = mem_rd_en && (mem_rd_addr[AXI_ADDR_WIDTH-1:BEAT_LSB] == CSR_ADDR[AXI_ADDR_WIDTH-1:BEAT_LSB]);

    reg         oneshot;
    reg         arm;
    reg         csr_rd_valid;
    wire        armed, done;
    wire [15:0] capture_count;

    always @(posedge axis_clk) begin
        if (!axis_aresetn) begin
            oneshot      <= 1'b0;
            arm          <= 1'b0;
            csr_rd_valid <= 1'b0;
        end else begin
            arm          <= csr_wr && mem_wr_strb[0] && mem_wr_data[1];
            csr_rd_valid <= csr_rd;
            if (csr_wr && mem_wr_strb[0]) oneshot <= mem_wr_data[0];
        end
    end

    assign mem_rd_valid = core_rd_valid || csr_rd_valid;
    assign mem_rd_data  = csr_rd_valid ? {{(AXI_DATA_WIDTH-32){1'b0}}, capture_count, 13'b0, done, armed, oneshot}
                                       : core_rd_data;

    wave_cap #(
        .AXI_DATA_WIDTH (AXI_DATA_WIDTH),
        .ROW_WIDTH      (ROW_WIDTH),
        .GRANULE        (GRANULE),
        .DEPTH          (DEPTH),
        .N_ROWS_WIDTH   (N_ROWS_WIDTH),
        .RAM_STYLE      (RAM_STYLE)
    ) u_wave_cap (
        .clk            (axis_clk),
        .rst_n          (axis_aresetn),
        .axi_wr_en      (mem_wr_en && !csr_wr),
        .axi_wr_addr    (mem_wr_addr[CORE_ADDR_WIDTH-1:0]),
        .axi_wr_data    (mem_wr_data),
        .axi_wr_strb    (mem_wr_strb),
        .axi_rd_en      (mem_rd_en && !csr_rd),
        .axi_rd_addr    (mem_rd_addr[CORE_ADDR_WIDTH-1:0]),
        .axi_rd_data    (core_rd_data),
        .axi_rd_valid   (core_rd_valid),
        .trigger        (trigger),
        .n_rows         (n_rows),
        .busy           (),
        .write_done     (write_done),
        .oneshot        (oneshot),
        .arm            (arm),
        .armed          (armed),
        .done           (done),
        .capture_count  (capture_count),
        .s_axis_tdata   (s_axis_tdata),
        .s_axis_tvalid  (s_axis_tvalid),
        .s_axis_tready  (s_axis_tready)
    );

    initial begin
        if (AXI_ADDR_WIDTH < CORE_ADDR_WIDTH)
            $error("AXI_ADDR_WIDTH must cover the capture memory (%0d bits)", CORE_ADDR_WIDTH);
    end

endmodule
