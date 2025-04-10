module axil_evr #(
    parameter GT_TYPE = "GTY",
    parameter integer EVCODE1 = 5,
    parameter integer FCNT_WIDTH = 24,  // freq_count update rate: 100M / 2**24 = 5.96 Hz.
    parameter integer DATA_WIDTH  = 32,
    parameter integer ADDR_WIDTH  = 8
) (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 s_axi_aclk CLK" *)
    (* X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF s_axi, ASSOCIATED_RESET s_axi_aresetn" *)
    input wire s_axi_aclk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 resetn RST" *)
    input wire s_axi_aresetn,
    input wire [ADDR_WIDTH-1:0] s_axi_awaddr,
    input wire s_axi_awvalid,
    output wire s_axi_awready,
    input wire [DATA_WIDTH-1:0] s_axi_wdata,
    input wire [(DATA_WIDTH/8)-1:0] s_axi_wstrb,
    input wire s_axi_wvalid,
    output wire s_axi_wready,
    output wire [1:0] s_axi_bresp,
    output wire s_axi_bvalid,
    input wire s_axi_bready,
    input wire [ADDR_WIDTH-1:0] s_axi_araddr,
    input wire s_axi_arvalid,
    output wire s_axi_arready,
    output wire [DATA_WIDTH-1:0] s_axi_rdata,
    output wire [1:0] s_axi_rresp,
    output wire s_axi_rvalid,
    input wire s_axi_rready,

    // transceiver IOs
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 gt_refclk_p CLK" *)
    input wire         gt_refclk_p,
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 gt_refclk_n CLK" *)
    input wire         gt_refclk_n,
    input wire         gt_rxp_in,
    input wire         gt_rxn_in,
    output wire        gt_refclk_out,

    // evr_clk
    output wire        event1_evr,

    // dsp_clock
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 dsp_clk CLK" *)
    input              dsp_clk,
    output wire        event1_dsp,
    output wire [63:0] live_ts_dsp
);

    localparam integer N_REGS_OUT = 1;
    localparam integer N_REGS_INP = 8;
    // Instantiate the AXI-Lite CSR module
    wire [N_REGS_OUT*DATA_WIDTH-1:0] csr_out;
    wire [N_REGS_INP*DATA_WIDTH-1:0] csr_in;
    axil_csr #(
        .DATA_WIDTH(DATA_WIDTH),
        .ADDR_WIDTH(ADDR_WIDTH),
        .N_REGS_OUT(N_REGS_OUT),
        .N_REGS_INP(N_REGS_INP)
    ) csr_inst (
        .s_axi_aclk(s_axi_aclk),
        .s_axi_aresetn(s_axi_aresetn),
        .s_axi_awaddr(s_axi_awaddr),
        .s_axi_awvalid(s_axi_awvalid),
        .s_axi_awready(s_axi_awready),
        .s_axi_wdata(s_axi_wdata),
        .s_axi_wstrb(s_axi_wstrb),
        .s_axi_wvalid(s_axi_wvalid),
        .s_axi_wready(s_axi_wready),
        .s_axi_bresp(s_axi_bresp),
        .s_axi_bvalid(s_axi_bvalid),
        .s_axi_bready(s_axi_bready),
        .s_axi_araddr(s_axi_araddr),
        .s_axi_arvalid(s_axi_arvalid),
        .s_axi_arready(s_axi_arready),
        .s_axi_rdata(s_axi_rdata),
        .s_axi_rresp(s_axi_rresp),
        .s_axi_rvalid(s_axi_rvalid),
        .s_axi_rready(s_axi_rready),
        .csr_out(csr_out),
        .csr_in(csr_in)
    );
    // Expand the control registers
    wire [DATA_WIDTH-1:0] csr_out_regs [0:N_REGS_OUT-1];
    wire [DATA_WIDTH-1:0] csr_inp_regs [0:N_REGS_INP-1];
    generate
        genvar i;
        for (i=0; i<N_REGS_OUT; i=i+1) begin: csr_out_reg_gen
            assign csr_out_regs[i] = csr_out[i*DATA_WIDTH +: DATA_WIDTH];
        end
        for (i=0; i<N_REGS_INP; i=i+1) begin: csr_inp_reg_gen
            assign csr_in[i*DATA_WIDTH +: DATA_WIDTH] = csr_inp_regs[i];
        end
    endgenerate

    wire [31:0] gt_evr_status;
    wire [31:0] gt_rx_reset_cnt;
    wire [0:0]  evr_timestamp_valid;
    wire [15:0] evr_evcnt;
    wire [31:0] evr_live_ts_lo;
    wire [31:0] evr_live_ts_hi;
    wire [31:0] gt_ref_freq;
    wire [31:0] gt_rx_freq;
    wire [0:0]  reset_all;

    // Instantiate the Timing Event Receiver (EVR)
    wire evr_clk;
    wire [15:0] evr_chars;
    wire [1:0] evr_charisk;

    wire rx_reset_done_sys;
    wire rx_aligned_sys;
    wire cplllocked_sys;

    evr_gt_wrapper #(
        .GT_TYPE(GT_TYPE)
    ) evr_gt_wrapper (
        .gt_refclk_p        (gt_refclk_p),
        .gt_refclk_n        (gt_refclk_n),
        .gt_rxp_in          (gt_rxp_in),
        .gt_rxn_in          (gt_rxn_in),
        .gt_refclk_out      (gt_refclk_out),
        .sys_clk            (s_axi_aclk),
        .soft_reset         (reset_all),
        .rx_reset_done_sys  (rx_reset_done_sys),
        .rx_aligned_sys     (rx_aligned_sys),
        .rx_fsm_reset_cnt   (gt_rx_reset_cnt),
        .cplllocked_sys     (cplllocked_sys),
        .rx_usrclk          (evr_clk),
        .rxdata             (evr_chars),
        .rxcharisk          (evr_charisk)
    );

    wire [63:0] evr_live_ts;
    timing_core #(
        .EVCODE1(EVCODE1)
    ) timing_core (
        .evr_clk             (evr_clk),
        .evr_rxd             (evr_chars),
        .evr_rxk             (evr_charisk),
        .event1_evr          (event1_evr),
        .sys_clk             (s_axi_aclk),
        .event1_cnt_sys      (evr_evcnt),
        .ts_valid_sys        (evr_timestamp_valid),
        .live_ts_sys         (evr_live_ts),
        .dsp_clk             (dsp_clk),
        .live_ts_dsp         (live_ts_dsp),
        .event1_dsp          (event1_dsp)
    );

    freq_count #(
        .refcnt_width(FCNT_WIDTH),
        .freq_width(32)
    ) freq_count_refclk (
        .sysclk(s_axi_aclk),
        .f_in(gt_refclk_out),
        .frequency(gt_ref_freq)
    );

    freq_count #(
        .refcnt_width(FCNT_WIDTH),
        .freq_width(32)
    ) freq_count_evrclk (
        .sysclk(s_axi_aclk),
        .f_in(evr_clk),
        .frequency(gt_rx_freq)
    );

    // Map CSR registers to signals

    assign gt_evr_status = {29'h0, rx_reset_done_sys, cplllocked_sys, rx_aligned_sys};
    assign evr_live_ts_lo = evr_live_ts[31:0];
    assign evr_live_ts_hi = evr_live_ts[63:32];
    // ========================= Memory Map =================================
    // Addr     Slice     Access  Usage
    // --------------------------------
    // 0        [31:0]    RO      gt_evr_status
    // 1        [31:0]    RO      gt_rx_reset_cnt
    // 2        [0:0]     RO      evr_timestamp_valid
    // 3        [31:0]    RO      evr_evcnt
    // 4        [31:0]    RO      evr_live_ts_lo
    // 5        [31:0]    RO      evr_live_ts_hi
    // 6        [31:0]    RO      gt_ref_freq
    // 7        [31:0]    RO      gt_rx_freq
    // 8        [0:0]     WO      reset_all
    assign reset_all = csr_out_regs[0][0]; // Reset signal from CSR register
    assign csr_inp_regs[0] = gt_evr_status;
    assign csr_inp_regs[1] = gt_rx_reset_cnt;
    assign csr_inp_regs[2] = evr_timestamp_valid;
    assign csr_inp_regs[3] = evr_evcnt;
    assign csr_inp_regs[4] = evr_live_ts_lo;
    assign csr_inp_regs[5] = evr_live_ts_hi;
    assign csr_inp_regs[6] = gt_ref_freq;
    assign csr_inp_regs[7] = gt_rx_freq;

endmodule
