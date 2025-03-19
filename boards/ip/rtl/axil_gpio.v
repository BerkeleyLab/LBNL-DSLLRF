`timescale 1ns / 1ps

module axil_gpio #(
    parameter integer C_S_AXI_DATA_WIDTH = 32,
    parameter integer C_S_AXI_ADDR_WIDTH = 6
) (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 s_axi_aclk CLK" *)
    (* X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF s_axi, ASSOCIATED_RESET s_axi_aresetn" *)
    input wire s_axi_aclk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 resetn RST" *)
    input wire s_axi_aresetn,

    input wire [C_S_AXI_ADDR_WIDTH-1:0] s_axi_awaddr,
    input wire s_axi_awvalid,
    output wire s_axi_awready,
    input wire [C_S_AXI_DATA_WIDTH-1:0] s_axi_wdata,
    input wire [(C_S_AXI_DATA_WIDTH/8)-1:0] s_axi_wstrb,
    input wire s_axi_wvalid,
    output wire s_axi_wready,
    output wire [1:0] s_axi_bresp,
    output wire s_axi_bvalid,
    input wire s_axi_bready,
    input wire [C_S_AXI_ADDR_WIDTH-1:0] s_axi_araddr,
    input wire s_axi_arvalid,
    output wire s_axi_arready,
    output wire [C_S_AXI_DATA_WIDTH-1:0] s_axi_rdata,
    output wire [1:0] s_axi_rresp,
    output wire s_axi_rvalid,
    input wire s_axi_rready,

    // GPIO interface
    output wire [C_S_AXI_DATA_WIDTH-1:0] gpio_out0,
    output wire [C_S_AXI_DATA_WIDTH-1:0] gpio_out1,
    input wire [C_S_AXI_DATA_WIDTH-1:0] gpio_inp
);

    // Internal signals
    wire [2*C_S_AXI_DATA_WIDTH-1:0] csr_out;
    wire [C_S_AXI_DATA_WIDTH-1:0] csr_in;

    // Instantiate the AXI-Lite CSR module
    axil_csr #(
        .DATA_WIDTH(C_S_AXI_DATA_WIDTH),
        .ADDR_WIDTH(C_S_AXI_ADDR_WIDTH),
        .N_REGS_OUT(2),
        .N_REGS_INP(1)
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

    // Connect GPIO outputs to CSR outputs
    assign gpio_out0 = csr_out[31:0];
    assign gpio_out1 = csr_out[63:32];

    // Connect GPIO input to CSR input
    assign csr_in = gpio_inp;

endmodule
