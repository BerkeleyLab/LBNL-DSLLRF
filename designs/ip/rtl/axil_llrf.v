`timescale 1ns / 1ps

module axil_llrf #(
    // Width of data bus in bits
    parameter integer AXI_DW = 32,
    // Width of address bus in bits
    parameter integer AXI_AW = 8,
    parameter integer SAMP_DW = 16,
    parameter integer S_AXIS_SAMP_NUM = 16,
    parameter integer S_AXIS_DW = SAMP_DW * S_AXIS_SAMP_NUM,
    parameter integer M_AXIS_SAMP_NUM = 16,
    parameter integer M_AXIS_DW = SAMP_DW * M_AXIS_SAMP_NUM,
    parameter integer KW = 18,          // Width of dsp signals
    parameter integer EW = 12           // error width
) (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 clk CLK" *)
    (* X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF s_axi:m_axis:s0_axis:s1_axis, ASSOCIATED_RESET s_axi_aresetn" *)
    input wire clk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 resetn RST" *)
    input wire s_axi_aresetn,

    input wire [AXI_AW-1:0] s_axi_awaddr,
    input wire s_axi_awvalid,
    output wire s_axi_awready,
    input wire [AXI_DW-1:0] s_axi_wdata,
    input wire [(AXI_DW/8)-1:0] s_axi_wstrb,
    input wire s_axi_wvalid,
    output wire s_axi_wready,
    output wire [1:0] s_axi_bresp,
    output wire s_axi_bvalid,
    input wire s_axi_bready,
    input wire [AXI_AW-1:0] s_axi_araddr,
    input wire s_axi_arvalid,
    output wire s_axi_arready,
    output wire [AXI_DW-1:0] s_axi_rdata,
    output wire [1:0] s_axi_rresp,
    output wire s_axi_rvalid,
    input wire s_axi_rready,

    // AXI Stream input interface for feedback channel, base band, I
    input wire [S_AXIS_DW-1:0] s0_axis_tdata,
    input wire s0_axis_tvalid,
    output wire s0_axis_tready,

    // AXI Stream input interface for feedback channel, base band, Q
    input wire [S_AXIS_DW-1:0] s1_axis_tdata,
    input wire s1_axis_tvalid,
    output wire s1_axis_tready,

    // AXI Stream output interface for feedback channel
    output wire [M_AXIS_DW-1:0] m_axis_tdata,
    output wire m_axis_tvalid,
    input wire m_axis_tready,

    // IOs
    output wire trigger_out,
    output wire rf_permit_out,
    output wire pulse_enable_out,
    output wire [15:0] pulse_length,
    input wire  ext_trigger_in,
    input wire  evr_trigger_in,
    input wire  rf_permit_in
);

    // Internal signals
    wire dsp_reset;
    wire dac_enable;
    wire amp_loop_enable;
    wire amp_loop_reset;
    wire signed [KW-1:0] amp_loop_setpoint;
    wire signed [KW-1:0] amp_loop_kp;
    wire signed [KW-1:0] amp_loop_ki;
    wire phs_loop_enable;
    wire phs_loop_reset;
    wire signed [KW-1:0] phs_loop_setpoint;
    wire signed [KW-1:0] phs_loop_kp;
    wire signed [KW-1:0] phs_loop_ki;
    wire signed [KW-1:0] amp_measured;
    wire signed [KW-1:0] phs_measured;
    wire signed [EW-1:0] amp_loop_err;
    wire signed [EW-1:0] phs_loop_err;

    axil_rf_control #(
        .DATA_WIDTH(AXI_DW),
        .ADDR_WIDTH(AXI_AW),
        .KW(KW)
    ) rf_control (
        .s_axi_aclk(clk),
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
        .dsp_reset(dsp_reset),
        .trigger_out(trigger_out),
        .rf_permit_out(rf_permit_out),
        .pulse_enable(pulse_enable_out),
        .dac_enable(dac_enable),
        .pulse_length(pulse_length),
        .amp_loop_enable(amp_loop_enable),
        .amp_loop_reset(amp_loop_reset),
        .amp_loop_setpoint(amp_loop_setpoint),
        .amp_loop_kp(amp_loop_kp),
        .amp_loop_ki(amp_loop_ki),
        .phs_loop_enable(phs_loop_enable),
        .phs_loop_reset(phs_loop_reset),
        .phs_loop_setpoint(phs_loop_setpoint),
        .phs_loop_kp(phs_loop_kp),
        .phs_loop_ki(phs_loop_ki),
        .amp_measured(amp_measured),
        .phs_measured(phs_measured),
        .amp_loop_err(amp_loop_err),
        .phs_loop_err(phs_loop_err),
        .ext_trigger_in(ext_trigger_in),
        .evr_trigger_in(evr_trigger_in),
        .rf_permit_in(rf_permit_in)
    );

    llrf_dsp #(
        .SAMP_DW(SAMP_DW),
        .S_AXIS_SAMP_NUM(S_AXIS_SAMP_NUM),
        .M_AXIS_SAMP_NUM(M_AXIS_SAMP_NUM),
        .KW(KW),
        .EW(EW)
    ) llrf_dsp (
        .clk(clk),
        .dsp_reset(dsp_reset),
        .trigger(trigger_out),
        .rf_permit(rf_permit_out),
        .pulse_enable(pulse_enable_out),
        .pulse_length(pulse_length),
        .amp_loop_enable(amp_loop_enable),
        .amp_loop_reset(amp_loop_reset),
        .amp_loop_setpoint(amp_loop_setpoint),
        .amp_loop_kp(amp_loop_kp),
        .amp_loop_ki(amp_loop_ki),
        .phs_loop_enable(phs_loop_enable),
        .phs_loop_reset(phs_loop_reset),
        .phs_loop_setpoint(phs_loop_setpoint),
        .phs_loop_kp(phs_loop_kp),
        .phs_loop_ki(phs_loop_ki),
        .amp_measured(amp_measured),
        .phs_measured(phs_measured),
        .amp_loop_err(amp_loop_err),
        .phs_loop_err(phs_loop_err),
        .s0_axis_tdata(s0_axis_tdata),
        .s0_axis_tvalid(s0_axis_tvalid),
        .s0_axis_tready(s0_axis_tready),
        .s1_axis_tdata(s1_axis_tdata),
        .s1_axis_tvalid(s1_axis_tvalid),
        .s1_axis_tready(s1_axis_tready),
        .m_axis_tdata(m_axis_tdata),
        .m_axis_tvalid(m_axis_tvalid),
        .m_axis_tready(m_axis_tready)
    );

endmodule
