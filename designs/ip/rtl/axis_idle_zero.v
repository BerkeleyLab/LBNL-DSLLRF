`timescale 1ns / 1ps
//-----------------------------------------------------------------------------
// Zero-fill at an RF-DAC input. The RF-DAC converts one word every cycle and ignores tvalid, so a cycle without a
// valid beat would repeat the last word: a waveform generator that stops sending would leave the DAC at its last
// sample. This stage outputs the input word when it is valid and zero otherwise, registered, with tvalid always
// high (one cycle of latency). Place it between the last AXI-Stream stage and the RFDC s_axis port, so the FIFOs in
// front of it see the generator's gaps and stay empty between playbacks (see wave_gen.v, doc/wave_gen.md).
//-----------------------------------------------------------------------------

module axis_idle_zero #(
    parameter integer DATA_WIDTH = 160
) (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 aclk CLK" *)
    (* X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF s_axis:m_axis, ASSOCIATED_RESET aresetn" *)
    input  wire                  aclk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 aresetn RST" *)
    (* X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *)
    input  wire                  aresetn,

    input  wire [DATA_WIDTH-1:0] s_axis_tdata,
    input  wire                  s_axis_tvalid,
    output wire                  s_axis_tready,

    output reg  [DATA_WIDTH-1:0] m_axis_tdata,
    output wire                  m_axis_tvalid,
    input  wire                  m_axis_tready
);
    assign s_axis_tready = m_axis_tready;
    assign m_axis_tvalid = 1'b1;

    always @(posedge aclk) begin
        if (!aresetn)
            m_axis_tdata <= {DATA_WIDTH{1'b0}};
        else if (m_axis_tready)
            m_axis_tdata <= s_axis_tvalid ? s_axis_tdata : {DATA_WIDTH{1'b0}};
    end
endmodule
