// Wrapper around wizard-generated event receiver GTY block
// And tiny EVR
// evr_gty_wrapper.v wrapped as axi peripheral
// along with some frequency counters

module axil_evr_gty_wrapper #(
    parameter DEBUG = "false",
    parameter DSP_EV1 = 5,
    parameter DSP_EV2 = 6,
    parameter integer CHECK_TIMEOUT = 125000,
    parameter integer C_S_AXI_DATA_WIDTH  = 32,
    parameter integer C_S_AXI_ADDR_WIDTH  = 8
    ) (
    // user ports
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 dsp_clk CLK" *)
    input              dsp_clk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 gty_refclk_p CLK" *)
    input              gty_refclk_p,
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 gty_refclk_n CLK" *)
    input              gty_refclk_n,
    input              RX_P, RX_N,
    output             TX_P, TX_N,
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 SFP_REC_CLK_P CLK" *)
    (* X_INTERFACE_PARAMETER = "FREQ_HZ 124910000, FREQ_TOLERANCE_HZ 0" *)
    output wire        SFP_REC_CLK_P,
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 SFP_REC_CLK_N CLK" *)
    (* X_INTERFACE_PARAMETER = "FREQ_HZ 124910000, FREQ_TOLERANCE_HZ 0" *)
    output wire        SFP_REC_CLK_N,
    output wire        evr_event1,
    // user LEDs
    output wire        gty_rx_aligned_led,
    output wire        evr_event1_led,
    // used in dsp_clock
    output wire        dsp_event1,
    output wire        dsp_event2,
    output wire [63:0] dsp_live_ts,
    // axi port
    input wire                            s_axi_aclk,
    input wire                            s_axi_aresetn,
    input wire [C_S_AXI_ADDR_WIDTH-1 : 0] s_axi_awaddr,
    input wire [2 : 0]                    s_axi_awprot,
    input wire                            s_axi_awvalid,
    output wire                           s_axi_awready,
    input wire [C_S_AXI_DATA_WIDTH-1 : 0] s_axi_wdata,
    input wire [(C_S_AXI_DATA_WIDTH/8)-1 : 0] s_axi_wstrb,
    input wire                            s_axi_wvalid,
    output wire                           s_axi_wready,
    output wire [1 : 0]                   s_axi_bresp,
    output wire                           s_axi_bvalid,
    input wire                            s_axi_bready,
    input wire [C_S_AXI_ADDR_WIDTH-1 : 0] s_axi_araddr,
    input wire [2 : 0]                    s_axi_arprot,
    input wire                            s_axi_arvalid,
    output wire                           s_axi_arready,
    output wire [C_S_AXI_DATA_WIDTH-1 : 0] s_axi_rdata,
    output wire [1 : 0]                    s_axi_rresp,
    output wire                           s_axi_rvalid,
    input wire                            s_axi_rready
    );

wire gty_refclk, gty_refclk_o2;
IBUFDS_GTE4 #(.REFCLK_HROW_CK_SEL(2'b00))
evr_gty_refclkBuf(.I(gty_refclk_p),
                  .IB(gty_refclk_n),
                  .CEB(1'b0),
                  .O(gty_refclk),
                  .ODIV2(gty_refclk_o2));
wire gty_refclk_buf;
BUFG_GT debug_buf (.I(gty_refclk_o2),
                   .O(gty_refclk_buf));

wire  gty_tx_clk, evr_clk;
wire [31:0] gty_evr_status;
wire [31:0] gty_rx_reset_cnt;
wire reset_all, rx_slide_req;
wire [15:0] evr_evcnt;
wire [0:0]  evr_timestamp_valid;
wire [0:0]  evr_live_pps_marker;
wire [0:0]  evr_live_hb_marker;
wire [0:0]  dsp_event1, dsp_event2;
wire [63:0] evr_live_ts;
evr_gty_wrapper #(
  .DEBUG("false"),
  .DSP_EV1(DSP_EV1),
  .DSP_EV2(DSP_EV2),
  .CHECK_TIMEOUT(CHECK_TIMEOUT)
  ) evr_gty_wrapper (
    .sys_clk             (s_axi_aclk),
    // in s_axi_aclk
    .gty_evr_status      (gty_evr_status),
    .gty_rx_reset_cnt    (gty_rx_reset_cnt),
    // should be async
    .reset_all           (reset_all),
    // XXX in evr_clk (unused for now)
    .rx_slide_req        (rx_slide_req),
    //
    .gty_refclk          (gty_refclk),
    .RX_N                (RX_N),
    .RX_P                (RX_P),
    .TX_N                (TX_N),
    .TX_P                (TX_P),
    .gty_tx_clk          (gty_tx_clk),
    .SFP_REC_CLK_P       (SFP_REC_CLK_P),
    .SFP_REC_CLK_N       (SFP_REC_CLK_N),
    .evr_clk             (evr_clk),
    // in s_axi_aclk, for readout and cross-check only
    .evr_timestamp_valid (evr_timestamp_valid),
    .evr_live_ts         (evr_live_ts),
    .evr_evcnt           (evr_evcnt),
    // used for checking determisitic latency
    .evr_event1          (evr_event1),  // in evr_clk

    .dsp_clk             (dsp_clk),
    .dsp_live_ts         (dsp_live_ts),  // in dsp_clk
    // unused: these markers cannot be seen without stretching
    .dsp_pps_marker      (evr_live_pps_marker),  // in dsp_clk
    .dsp_hb_marker       (evr_live_hb_marker),  // in dsp_clk
    .dsp_event1          (dsp_event1),  // in dsp_clk
    .dsp_event2          (dsp_event2)  // in dsp_clk
);
/*
// to see it on the scope
OBUF #(
   .SLEW("FAST")
) OBUF_EVR_FB_CLK (
   .O(evr_event1),
   .I(evr_clk)
);
*/

// User LEDs
assign evr_event1_led = evr_event1;
assign gty_rx_aligned_led = gty_evr_status[5];

wire [31:0] gty_ref_freq;
freq_count #(
  .glitch_thresh(2),
  .refcnt_width(24),
  .freq_width(32),
  .initv(0)
) freq_count_si570 (
  .sysclk(s_axi_aclk),  // input (known reference clock)
  .f_in(gty_refclk_buf),  // input (unknown clock)
  .frequency(gty_ref_freq) // output [freq_width-1:0]
);

wire [31:0] gty_rx_freq;
freq_count #(
  .glitch_thresh(2),
  .refcnt_width(24),
  .freq_width(32),
  .initv(0)
) freq_count_rxclk (
  .sysclk(s_axi_aclk),  // input (known reference clock)
  .f_in(evr_clk),  // input (unknown clock)
  .frequency(gty_rx_freq) // output [freq_width-1:0]
);
// already in s_axi_aclk
wire [31:0] evr_live_ts_lo = evr_live_ts[31:0];
wire [31:0] evr_live_ts_hi = evr_live_ts[63:32];

// ========================= Memory Map =================================
// Addr     Slice     Access  Usage
// --------------------------------
// 0        [31:0]    RO      gty_evr_status
// 1        [31:0]    RO      gty_rx_reset_cnt
// 2        [0:0]     RO      evr_timestamp_valid
// 3        [15:0]    RO      evr_evcnt
// 4        [31:0]    RO      evr_live_ts_lo
// 5        [31:0]    RO      evr_live_ts_hi
// 6        [31:0]    RO      gty_ref_freq
// 7        [31:0]    RO      gty_rx_freq
// 8        [0:0]     WO      reset_all
// 9        [0:0]     WO      rx_slide_req

// Number of Host-Accessible Registers = (1<<HA_REG_AW) = 16
localparam integer HA_REG_AW = 4; // 16 registers

// local parameter for addressing 32 bit / 64 bit C_S_AXI_DATA_WIDTH
// ADDR_LSB is used for addressing 32/64 bit registers/memories
// ADDR_LSB = 2 for 32 bits (n downto 2)
// ADDR_LSB = 3 for 64 bits (n downto 3)
localparam integer ADDR_LSB = (C_S_AXI_DATA_WIDTH/32) + 1;
// =================== Host-Accessible Registers ========================
// Note that they are implemented as a RAM for convenience/portability, but in
// general will not synthesize to block ram due to continuous access of individual
// elements.
localparam integer NUM_HA_REGS = (1 << HA_REG_AW);
reg [C_S_AXI_DATA_WIDTH-1:0] ha_ram [0:NUM_HA_REGS-1];
reg [NUM_HA_REGS-1:0] ha_strobes=0;
integer byte_index;
reg aw_en=1;

// ====================== AXI4LITE signals ==============================
reg [C_S_AXI_ADDR_WIDTH-1:0] axi_awaddr=0, axi_araddr=0;
reg [C_S_AXI_DATA_WIDTH-1:0] axi_rdata=0;
reg axi_awready=1'b0, axi_wready=1'b0, axi_bvalid=1'b0, axi_arready=1'b0, axi_rvalid=1'b0;
reg [1:0] axi_bresp=0, axi_rresp=0;

assign reset_all = ha_ram[8][0];
assign rx_slide_req = ha_ram[9][0];

// ========================= Bus Writes =================================
wire ha_reg_wren = axi_wready && s_axi_wvalid && axi_awready && s_axi_awvalid;
integer nreg;
wire [HA_REG_AW-1:0] w_reg_sel = axi_awaddr[ADDR_LSB+HA_REG_AW-1:ADDR_LSB];
always @(posedge s_axi_aclk) begin
  ha_strobes <= 0;
  if (s_axi_aresetn == 1'b0) begin
    for (nreg = 0; nreg<NUM_HA_REGS; nreg=nreg+1) begin
      ha_ram[nreg] <= 0;
    end
  end else begin
    if (ha_reg_wren) begin
      // Respective byte enables are asserted as per write strobes
      case (w_reg_sel)
        default: begin
          for ( byte_index = 0; byte_index <= (C_S_AXI_DATA_WIDTH/8)-1; byte_index = byte_index+1 ) begin
            if ( s_axi_wstrb[byte_index] == 1 ) begin
              // Respective byte enables are asserted as per write strobes
              // Peripheral register 7
              ha_ram[w_reg_sel][(byte_index*8) +: 8] <= s_axi_wdata[(byte_index*8) +: 8];
              ha_strobes[w_reg_sel] <= 1'b1;
            end
          end
        end
      endcase
    end
  end
end

// ========================== Bus Reads =================================
// Peripheral register read enable is asserted when valid address is available
// and the peripheral is ready to accept the read address.
wire [HA_REG_AW-1:0] r_reg_sel = axi_araddr[ADDR_LSB+HA_REG_AW-1:ADDR_LSB];
wire ha_reg_rden = axi_arready & s_axi_arvalid & ~axi_rvalid;
// Note: reg_data_out is actually combinational (i.e. wire), but using always @(*) case statement
reg [C_S_AXI_DATA_WIDTH-1:0] reg_data_out=0;
always @(*) begin
  case (r_reg_sel)
    // USER: Address-specific clobbering of default read behavior
    0: reg_data_out = gty_evr_status;
    1: reg_data_out = gty_rx_reset_cnt;
    2: reg_data_out = evr_timestamp_valid;
    3: reg_data_out = evr_evcnt;
    4: reg_data_out = evr_live_ts_lo;
    5: reg_data_out = evr_live_ts_hi;
    6: reg_data_out = gty_ref_freq;
    7: reg_data_out = gty_rx_freq;
    default : reg_data_out = ha_ram[r_reg_sel];
  endcase
end

always @(posedge s_axi_aclk) begin
  if (s_axi_aresetn == 1'b0) begin
    axi_rdata  <= 0;
  end else begin
    // When there is a valid read address (s_axi_arvalid) with
    // acceptance of read address by the peripheral (axi_arready),
    // output the read dada
    if (ha_reg_rden) begin
      axi_rdata <= reg_data_out;  // register read data
    end
  end
end

// ============== AXI-4 Lite Bus Protocol Implementation ================
// I/O Connections assignments
assign s_axi_awready  = axi_awready;
assign s_axi_wready  = axi_wready;
assign s_axi_bresp  = axi_bresp;
assign s_axi_bvalid  = axi_bvalid;
assign s_axi_arready  = axi_arready;
assign s_axi_rdata  = axi_rdata;
assign s_axi_rresp  = axi_rresp;
assign s_axi_rvalid  = axi_rvalid;

always @(posedge s_axi_aclk) begin
  if (s_axi_aresetn == 1'b0) begin
    axi_awready <= 1'b0;
    aw_en       <= 1'b1;
    axi_awaddr  <= 0;
    axi_wready  <= 1'b0;
    axi_bvalid  <= 0;
    axi_bresp   <= 2'b0;
    axi_arready <= 1'b0;
    axi_araddr  <= 0;
    axi_rvalid  <= 0;
    axi_rresp   <= 0;
  end else begin

    // Implement axi_awready generation
    if (~axi_awready && s_axi_awvalid && s_axi_wvalid && aw_en) begin
      // peripheral is ready to accept write address when
      // there is a valid write address and write data
      // on the write address and data bus. This design
      // expects no outstanding transactions.
      axi_awready <= 1'b1;
      aw_en <= 1'b0;
    end else if (s_axi_bready && axi_bvalid) begin
      aw_en <= 1'b1;
      axi_awready <= 1'b0;
    end else begin
      axi_awready <= 1'b0;
    end

    // Implement axi_awaddr generation
    if (~axi_awready && s_axi_awvalid && s_axi_wvalid && aw_en) begin
      // Write Address latching
      axi_awaddr <= s_axi_awaddr;
    end

    // Implement axi_wready generation
    if (~axi_wready && s_axi_wvalid && s_axi_awvalid && aw_en ) begin
      // peripheral is ready to accept write data when
      // there is a valid write address and write data
      // on the write address and data bus. This design
      // expects no outstanding transactions.
      axi_wready <= 1'b1;
    end else begin
      axi_wready <= 1'b0;
    end

    // Implement write response logic generation
    if (axi_awready && s_axi_awvalid && ~axi_bvalid && axi_wready && s_axi_wvalid) begin
      // indicates a valid write response is available
      axi_bvalid <= 1'b1;
      axi_bresp  <= 2'b0; // 'OKAY' response
    end else begin
      if (s_axi_bready && axi_bvalid) begin
        //check if bready is asserted while bvalid is high)
        //(there is a possibility that bready is always asserted high)
        axi_bvalid <= 1'b0;
      end
    end

    // Implement axi_arready generation
    if (~axi_arready && s_axi_arvalid) begin
      // indicates that the peripheral has acceped the valid read address
      axi_arready <= 1'b1;
      // Read address latching
      axi_araddr  <= s_axi_araddr;
    end else begin
      axi_arready <= 1'b0;
    end

    // Implement axi_rvalid generation
    if (axi_arready && s_axi_arvalid && ~axi_rvalid) begin
      // Valid read data is available at the read data bus
      axi_rvalid <= 1'b1;
      axi_rresp  <= 2'b0; // 'OKAY' response
    end else if (axi_rvalid && s_axi_rready) begin
      // Read data is accepted by the master
      axi_rvalid <= 1'b0;
    end

  end
end

endmodule
