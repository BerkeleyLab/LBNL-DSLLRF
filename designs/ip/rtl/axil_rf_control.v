`timescale 1ns / 1ps

module axil_rf_control #(
    // Width of data bus in bits
    parameter integer DATA_WIDTH = 32,
    // Width of address bus in bits
    parameter integer ADDR_WIDTH = 8
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

    // IOs
    output wire trigger_out,
    output wire dac_enable_out,
    output wire [11:0] pulse_length_out,
    input wire  ext_trigger_in,
    input wire  evr_trigger_in,
    input wire  rf_permit_in,
    input wire [31:0] debug_in
);

    localparam integer N_REGS_OUT = 6;
    localparam integer N_REGS_INP = 2;

    // Internal signals
    wire [N_REGS_OUT*DATA_WIDTH-1:0] csr_out;
    wire [N_REGS_INP*DATA_WIDTH-1:0] csr_in;

    // Instantiate the AXI-Lite CSR module
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

    // Map CSR registers to signals
    wire [1:0] trig_sel;
    wire [31:0] trig_period;
    wire [15:0] trig_delay;
    wire [15:0] trig_divide;
    wire dac_enable;
    wire rf_permit_in_dsp;

    assign trig_sel         = csr_out_regs[0][1:0];
    assign trig_period      = csr_out_regs[1];
    assign trig_delay       = csr_out_regs[2][15:0];
    assign trig_divide      = csr_out_regs[3][15:0];
    assign pulse_length_out = csr_out_regs[4][11:0];
    assign dac_enable       = csr_out_regs[5][0];
    assign csr_inp_regs[0]  = {31'h0, rf_permit_in_dsp};
    assign csr_inp_regs[1]  = debug_in;

    // Clock and reset
    wire dsp_clk = s_axi_aclk;
    wire dsp_reset = ~s_axi_aresetn;

    // Internal trigger source
    reg [31:0] int_trig_cnt=0;
    wire int_trig;
    assign int_trig = (int_trig_cnt == trig_period - 1);
    always @(posedge dsp_clk) begin
        int_trig_cnt <= (dsp_reset || int_trig) ? 0 : int_trig_cnt + 1'b1;
    end

    // cdc and edge detection
    wire evr_trig_edge;
    wire ext_trig_edge;
    sig_cdc_edge evr_trig_edge_inst (
        .clk(dsp_clk),
        .sig_in(evr_trigger_in),
        .edge_out(evr_trig_edge)
    );
    sig_cdc_edge ext_trig_edge_inst (
        .clk(dsp_clk),
        .sig_in(ext_trigger_in),
        .edge_out(ext_trig_edge)
    );
    sig_cdc_edge rf_permit_edge_inst (
        .clk(dsp_clk),
        .sig_in(rf_permit_in),
        .sig_out(rf_permit_in_dsp)
    );

    // Trigger source multiplexer
    localparam [1:0] TRIG_SEL_INT = 2'b00;
    localparam [1:0] TRIG_SEL_EVR = 2'b01;
    localparam [1:0] TRIG_SEL_EXT = 2'b10;
    reg trigger_int=0;
    always @* begin
        case (trig_sel)
            TRIG_SEL_INT: trigger_int = int_trig;
            TRIG_SEL_EVR: trigger_int = evr_trig_edge;
            TRIG_SEL_EXT: trigger_int = ext_trig_edge;
            default: trigger_int = 1'b0;
        endcase
    end

    // Trigger delay and divide
    trigger #(
        .DW(16)
    ) trigger_inst (
        .clk(dsp_clk),
        .reset(dsp_reset),
        .trig_in(trigger_int),
        .delay(trig_delay),
        .divide(trig_divide),
        .trig_out(trigger_out)
    );

    // DAC enable
    assign dac_enable_out = dac_enable && rf_permit_in_dsp;

endmodule

// generate a trigger signal with a delay and divide
module trigger #(
    parameter DW=16
) (
    input   clk,
    input   reset,
    input   trig_in,
    input   [DW-1:0] delay,
    input   [DW-1:0] divide,
    output  trig_out
);

    reg [DW-1:0] cnt=0;
    reg [DW-1:0] div_cnt=0;

    wire div_val=(div_cnt==divide);
    reg div_val1=0, reset1=0;
    wire div_out = div_val & !div_val1;

    always @(posedge clk) begin
        if (reset | reset1) begin
            cnt <= 0;
            div_cnt <= 0;
        end else begin
            cnt <= div_out ? 0 : cnt + 1'b1;
            div_cnt <= div_val ? 0 : div_cnt + trig_in;
        end
        div_val1 <= div_val;
        reset1 <= reset;
    end
    assign trig_out = (cnt==delay);

endmodule

module sig_cdc_edge (
    input clk,
    input sig_in,
    output sig_out,
    output edge_out
);

    (* ASYNC_REG="TRUE" *) reg [2:0] sig_d = 0;
    always @(posedge clk) begin
        sig_d <= {sig_d[1:0], sig_in};
    end
    assign sig_out = sig_d[1];
    assign edge_out = ~sig_d[2] & sig_d[1];
endmodule