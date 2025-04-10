`timescale 1ns / 1ps

module axis_cdc #(
    parameter integer DATA_WIDTH = 256,
    parameter integer FIFO_DEPTH = 4
) (
    // AXI Stream input interface
    input wire s_axis_aclk,
    input wire s_axis_aresetn,
    input wire [DATA_WIDTH-1:0] s_axis_tdata,
    input wire s_axis_tvalid,
    output wire s_axis_tready,

    // AXI Stream output interface
    input wire m_axis_aclk,
    input wire m_axis_aresetn,
    output wire [DATA_WIDTH-1:0] m_axis_tdata,
    output wire m_axis_tvalid,
    input wire m_axis_tready
);

    // just a simplified version of async FIFO
    axis_async_fifo #(
        .DATA_WIDTH(DATA_WIDTH),
        .KEEP_ENABLE(0),
        .DEPTH(FIFO_DEPTH),
        .LAST_ENABLE(0),
        .USER_ENABLE(0)
    ) fifo (
        .s_clk          (s_axis_aclk),
        .s_rst          (~s_axis_aresetn),
        .s_axis_tdata   (s_axis_tdata),
        .s_axis_tvalid  (s_axis_tvalid),
        .s_axis_tready  (s_axis_tready),
        .s_axis_tkeep   (0),
        .s_axis_tlast   (1'b0),
        .s_axis_tid     (8'h0),
        .s_axis_tdest   (8'h0),
        .s_axis_tuser   (1'b0),

        .m_clk          (m_axis_aclk),
        .m_rst          (~m_axis_aresetn),
        .m_axis_tdata   (m_axis_tdata),
        .m_axis_tvalid  (m_axis_tvalid),
        .m_axis_tready  (m_axis_tready),

        .s_pause_req    (1'b0),
        .m_pause_req    (1'b0)
    );

endmodule
