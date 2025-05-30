`timescale 1ns / 1ps

// This module adds two AXI Stream inputs and outputs the result on a single AXI Stream output.
// It is designed to work with 16 samples of 16 bits each, resulting in a data width of 256 bits.
// Intended for feedforward and feedback channels in a digital signal processing (DSP) application.
module axis_adder #(
    parameter integer SAMP_DW = 16,
    parameter integer SAMP_NUM = 16
) (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 axis_aclk CLK" *)
    (* X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF m_axis:s0_axis:s1_axis, ASSOCIATED_RESET axis_aresetn" *)
    input wire axis_aclk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 axis_aresetn RST" *)
    input wire axis_aresetn,

    // AXI Stream input interface 0
    input wire [SAMP_DW * SAMP_NUM-1:0] s0_axis_tdata,
    input wire s0_axis_tvalid,
    output wire s0_axis_tready,

    // AXI Stream input interface 1
    input wire [SAMP_DW * SAMP_NUM-1:0] s1_axis_tdata,
    input wire s1_axis_tvalid,
    output wire s1_axis_tready,

    // AXI Stream output interface
    output reg [SAMP_DW * SAMP_NUM-1:0] m_axis_tdata,
    output reg m_axis_tvalid,
    input wire m_axis_tready
);

    integer i=0;
    always @(posedge axis_aclk) begin
        if (!axis_aresetn) begin
            m_axis_tvalid <= 1'b0;
            m_axis_tdata <= {SAMP_DW * SAMP_NUM{1'b0}};
        end else begin
            if (s0_axis_tvalid && s1_axis_tvalid) begin
                for (i = 0; i < SAMP_NUM; i = i + 1) begin
                    m_axis_tdata[i*SAMP_DW +: SAMP_DW] <= s0_axis_tdata[i*SAMP_DW +: SAMP_DW] + s1_axis_tdata[i*SAMP_DW +: SAMP_DW];
                end
                m_axis_tvalid <= 1'b1;
            end else begin
                m_axis_tvalid <= 1'b0;
            end
        end
    end
    assign s0_axis_tready = m_axis_tready;
    assign s1_axis_tready = m_axis_tready;
endmodule
