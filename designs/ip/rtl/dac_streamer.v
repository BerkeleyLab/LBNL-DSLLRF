`timescale 1ns / 1ns

// Streams data from a BRAM to an AXIS interface.

module dac_streamer #(
    parameter integer SAMP_DW = 16,     // 16 bits data
    parameter integer SAMP_NUM = 16,    // 16 samples
    parameter integer AW = 16,          // 2**AW number of rows, total number of samples: 2**AW * DW/16
    parameter integer READ_LATENCY = 3           // Number of read cycles
) (
    (* X_INTERFACE_PARAMETER = "MASTER_TYPE BRAM_CTRL, READ_WRITE_MODE READ_ONLY" *)

    (* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 BRAM_A DIN" *)
    output wire [SAMP_DW*SAMP_NUM-1:0] bram_wdata, // Data In Bus (optional)

    (* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 BRAM_A WE" *)
    output [SAMP_DW*SAMP_NUM/8-1:0] bram_we, // Byte Enables (optional)

    (* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 BRAM_A EN" *)
    output wire bram_en, // Chip Enable Signal (optional)

    (* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 BRAM_A DOUT" *)
    input wire [SAMP_DW*SAMP_NUM-1:0] bram_rdata, // Data Out Bus (optional)

    (* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 BRAM_A ADDR" *)
    output reg [31:0] bram_addr, /// Address Signal (required)

    (* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 BRAM_A CLK" *)
    output wire bram_clk, // Clock Signal (required)

    (* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 BRAM_A RST" *)
    output wire bram_rst, // Reset Signal (required)

    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 axis_clk CLK" *)
    (* X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF m_axis, ASSOCIATED_RESET axis_aresetn" *)
    input wire axis_clk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 axis_aresetn RST" *)
    input  wire              axis_aresetn,
    output wire [SAMP_DW*SAMP_NUM-1:0]     m_axis_tdata,
    input  wire              m_axis_tready,
    output wire              m_axis_tvalid,

    // Control Input Parameters
    input wire [AW-1:0]     n_rows,
    input wire enable,
    input wire trigger  // single clock cycle pulse
);
    localparam integer DW = SAMP_DW * SAMP_NUM;
    localparam integer NBPIPE = READ_LATENCY-1;   // Number of pipeline Registers
    localparam integer NUM_COL = SAMP_DW*SAMP_NUM/8; // increment address by DW/8 bytes, or 16 samples

    wire pulse_valid;
    pulse_gen #(
        .AW(AW)
    ) pulse_gen_inst (
        .clk(axis_clk),
        .trigger(trigger),
        .high_len(n_rows),
        .pulse_out(pulse_valid)
    );

    // Assign BRAM interface signals
    assign bram_wdata = 0;
    assign bram_clk = axis_clk;
    assign bram_rst = ~axis_aresetn;
    assign bram_we = {NUM_COL{1'b0}};
    assign bram_en = pulse_valid & enable;

    // Pipeline delay for warting BRAM read latency
    reg [NBPIPE:0] tvalid_pipe = 0;
    always @(posedge axis_clk) begin
        tvalid_pipe <= {tvalid_pipe[NBPIPE-1:0], bram_en};
        bram_addr <= pulse_valid ? bram_addr + NUM_COL : 0;
    end

    // zeros are also valid data
    assign m_axis_tvalid = 1'b1;
    wire pulse_valid_pipe = tvalid_pipe[NBPIPE];
    assign m_axis_tdata  = pulse_valid_pipe ? bram_rdata : {DW{1'b0}};

endmodule
