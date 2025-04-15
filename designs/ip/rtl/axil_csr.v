`timescale 1ns / 1ps

// AXI-4 Lite Control Status Register (CSR) module
// The intention is to provide a generic interface for higher level modules to instantiate
// and access control and status registers.

// Address map (e.g. N_REGS_OUT = 16):
// 0x00 - 0x3C: Control registers, 0x3C / 4 = N_REGS_OUT - 1
// 0x40 - 0x7C: Status registers,  0x7C / 4 = N_REGS_OUT + N_REGS_INP - 1
module axil_csr #(
    // Width of data bus in bits
    parameter integer DATA_WIDTH = 32,
    // Width of address bus in bits
    parameter integer ADDR_WIDTH = 8,
    // Width of wstrb(width of data bus in words)
    parameter integer AXI_WSTRB = (DATA_WIDTH/8),
    // Number of control registers
    parameter integer N_REGS_OUT = 4,
    // Number of status registers
    parameter integer N_REGS_INP = 4
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
    input wire [AXI_WSTRB-1:0] s_axi_wstrb,
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

    // IOs
    output wire [N_REGS_OUT*DATA_WIDTH-1:0] csr_out,  // flattened control registers
    input wire  [N_REGS_INP*DATA_WIDTH-1:0] csr_in    // flattened status inputs
);
    localparam integer ADDR_LSB = $clog2(AXI_WSTRB);  // 2, 4-byte aligned
    localparam integer REG_AW = $clog2(N_REGS_INP + N_REGS_OUT);
    localparam integer ADDR_CTR_REG_END = N_REGS_OUT << ADDR_LSB;
    localparam integer ADDR_STS_REG_END = (N_REGS_INP << ADDR_LSB) + ADDR_CTR_REG_END;

    // Control Registers
    reg [DATA_WIDTH-1:0] csr_regs [0:N_REGS_OUT-1];

    // AXI4LITE signals
    reg [ADDR_WIDTH-1:0] axi_awaddr;
    reg axi_awready;
    reg axi_wready;
    reg [1:0] axi_bresp;
    reg axi_bvalid;
    reg [ADDR_WIDTH-1:0] axi_araddr;
    reg axi_arready;
    reg [DATA_WIDTH-1:0] axi_rdata;
    reg [1:0] axi_rresp;
    reg axi_rvalid;

    // AXI4LITE write address channel
    assign s_axi_awready = axi_awready;
    assign s_axi_wready = axi_wready;
    assign s_axi_bresp = axi_bresp;
    assign s_axi_bvalid = axi_bvalid;

    // AXI4LITE read address channel
    assign s_axi_arready = axi_arready;
    assign s_axi_rdata = axi_rdata;
    assign s_axi_rresp = axi_rresp;
    assign s_axi_rvalid = axi_rvalid;

    // Write address channel
    always @(posedge s_axi_aclk) begin
        if (~s_axi_aresetn) begin
            axi_awready <= 1'b0;
            axi_awaddr <= 0;
        end else begin
            if (~axi_awready && s_axi_awvalid && s_axi_wvalid) begin
                axi_awready <= 1'b1;
                axi_awaddr <= s_axi_awaddr;
            end else begin
                axi_awready <= 1'b0;
            end
        end
    end

    // Write data channel
    always @(posedge s_axi_aclk) begin
        if (~s_axi_aresetn) begin
            axi_wready <= 1'b0;
        end else begin
            if (~axi_wready && s_axi_wvalid && s_axi_awvalid) begin
                axi_wready <= 1'b1;
            end else begin
                axi_wready <= 1'b0;
            end
        end
    end

    // Write response channel
    always @(posedge s_axi_aclk) begin
        if (~s_axi_aresetn) begin
            axi_bvalid <= 1'b0;
            axi_bresp <= 2'b0;
        end else begin
            if (axi_awready && s_axi_awvalid && ~axi_bvalid && axi_wready && s_axi_wvalid) begin
                axi_bvalid <= 1'b1;
                axi_bresp <= 2'b0;
            end else begin
                if (s_axi_bready && axi_bvalid) begin
                    axi_bvalid <= 1'b0;
                end
            end
        end
    end

    // Read address channel
    always @(posedge s_axi_aclk) begin
        if (~s_axi_aresetn) begin
            axi_arready <= 1'b0;
            axi_araddr <= 0;
        end else begin
            if (~axi_arready && s_axi_arvalid) begin
                axi_arready <= 1'b1;
                axi_araddr <= s_axi_araddr;
            end else begin
                axi_arready <= 1'b0;
            end
        end
    end

    // Read data channel
    always @(posedge s_axi_aclk) begin
        if (~s_axi_aresetn) begin
            axi_rvalid <= 1'b0;
            axi_rresp <= 2'b0;
        end else begin
            if (axi_arready && s_axi_arvalid && ~axi_rvalid) begin
                axi_rvalid <= 1'b1;
                axi_rresp <= 2'b0;
            end else if (axi_rvalid && s_axi_rready) begin
                axi_rvalid <= 1'b0;
            end
        end
    end

    // CSR write logic
    integer i;
    wire [REG_AW-1:0] w_reg_index = axi_awaddr[ADDR_LSB +: REG_AW];
    always @(posedge s_axi_aclk) begin
        if (~s_axi_aresetn) begin
            for (i = 0; i < N_REGS_OUT; i = i + 1) begin
                csr_regs[i] <= {DATA_WIDTH{1'b0}};
            end
        end else begin
            if (axi_awready && s_axi_awvalid && axi_wready && s_axi_wvalid) begin
                if (axi_awaddr < ADDR_CTR_REG_END) begin
                    for (i = 0; i < AXI_WSTRB; i = i + 1) begin
                        if (s_axi_wstrb[i])
                            csr_regs[w_reg_index][i*8 +: 8] <= s_axi_wdata[i*8 +: 8];
                    end
                end
            end
        end
    end

    // CSR read, and status read logic
    wire [REG_AW-1:0] r_reg_index = axi_araddr[ADDR_LSB +: REG_AW];
    wire [REG_AW-1:0] status_reg_index = r_reg_index - N_REGS_OUT;
    always @(posedge s_axi_aclk) begin
        if (~s_axi_aresetn) begin
            axi_rdata <= 0;
        end else begin
            if (axi_arready && s_axi_arvalid) begin
                if (axi_araddr < ADDR_CTR_REG_END)
                    axi_rdata <= csr_regs[r_reg_index];
                else if (axi_araddr < ADDR_STS_REG_END) begin
                    axi_rdata <= csr_in[status_reg_index * DATA_WIDTH +: DATA_WIDTH];
                end else begin
                    axi_rdata <= 32'hDEADBEEF;
                end
            end
        end
    end

    genvar k;
    generate
        for (k = 0; k < N_REGS_OUT; k = k + 1) begin : ctrl_out_assign
            assign csr_out[k*DATA_WIDTH +: DATA_WIDTH] = csr_regs[k];
        end
    endgenerate

endmodule
