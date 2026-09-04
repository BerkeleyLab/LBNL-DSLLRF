`timescale 1ns / 1ns

// Captures data from an AXIS interface to a BRAM, byte addressing.
// number of rows:          N_ROWS = 2**AW
// number of columns (byte):N_COLS = SAMP_DW * SAMP_NUM / 8
// total number of bytes:   N_BYTES = N_ROWS * N_COLS
// total number of samples: N_BYTES / (SAMP_DW / 8)
module adc_capture #(
    parameter integer SAMP_DW = 16,
    parameter integer SAMP_NUM = 16,
    parameter integer AW = 16
) (
    (* X_INTERFACE_PARAMETER = "MASTER_TYPE BRAM_CTRL, READ_WRITE_MODE WRITE_ONLY" *)

    (* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 BRAM_A DIN" *)
    output wire [SAMP_DW*SAMP_NUM-1:0] bram_wdata, // Data In Bus (optional)

    (* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 BRAM_A WE" *)
    output wire [SAMP_DW*SAMP_NUM/8-1:0] bram_we, // Byte Enables (optional)

    (* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 BRAM_A EN" *)
    output wire bram_en, // Chip Enable Signal (optional)

    (* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 BRAM_A DOUT" *)
    input wire [SAMP_DW*SAMP_NUM-1:0] bram_rdata, // Data Out Bus (optional)

    (* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 BRAM_A ADDR" *)
    output reg [31:0] bram_addr, // Address Signal (required)

    (* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 BRAM_A CLK" *)
    output wire bram_clk, // Clock Signal (required)

    (* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 BRAM_A RST" *)
    output wire bram_rst, // Reset Signal (required)

    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 axis_clk CLK" *)
    (* X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF s_axis, ASSOCIATED_RESET axis_aresetn" *)
    input wire axis_clk,

    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 axis_aresetn RST" *)
    input  wire             axis_aresetn,
    input  wire [SAMP_DW*SAMP_NUM-1:0]    s_axis_tdata,
    output wire             s_axis_tready,
    input  wire             s_axis_tvalid,

    output wire             write_done,
    // Control Input Parameters
    input wire [AW-1:0]     n_rows,
    input wire              trigger     // single clock cycle pulse
);
    localparam integer DW = SAMP_DW * SAMP_NUM;
    localparam integer N_COLS = DW / 8; // increment address by DW/8 bytes

    wire pulse_valid;
    pulse_gen #(.AW(AW)) pulse_gen_inst (
        .clk        (axis_clk),
        .trigger    (trigger),
        .high_len   (n_rows),
        .pulse_out  (pulse_valid)
    );

    // Assign BRAM interface signals
    assign bram_clk = axis_clk;
    assign bram_rst = ~axis_aresetn;
    assign bram_wdata = s_axis_tdata;
    assign bram_we = s_axis_tvalid ? {N_COLS{1'b1}} : {N_COLS{1'b0}};
    assign bram_en = pulse_valid;
    reg pulse_valid_d = 0;
    always @(posedge axis_clk) begin
        bram_addr <= pulse_valid ? bram_addr + N_COLS : 0;
        pulse_valid_d <= pulse_valid;
    end

    assign s_axis_tready = 1'b1;
    assign write_done = !pulse_valid && pulse_valid_d;

endmodule
