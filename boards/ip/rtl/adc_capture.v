`timescale 1ns / 1ns

// Captures data from an AXIS interface to a BRAM.

module adc_capture #(
    parameter integer DW = 256,        // 16 samples, 16 bits data == 32 bytes
    parameter integer AW = 12          // 2**AW number of rows, total number of samples: 2**AW * DW/16
) (
    (* X_INTERFACE_PARAMETER = "MASTER_TYPE BRAM_CTRL, READ_WRITE_MODE WRITE, MEM_SIZE 131072, MEM_WIDTH 256" *)

    (* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 BRAM_A DIN" *)
    output wire [DW-1:0] bram_wdata, // Data In Bus (optional)

    (* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 BRAM_A WE" *)
    output wire [DW/8-1:0] bram_we, // Byte Enables (optional)

    (* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 BRAM_A EN" *)
    output reg bram_en, // Chip Enable Signal (optional)

    (* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 BRAM_A DOUT" *)
    input wire [DW-1:0] bram_rdata, // Data Out Bus (optional)

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
    input  wire [DW-1:0]    s_axis_tdata,
    output wire             s_axis_tready,
    input  wire             s_axis_tvalid,

    // Control Input Parameters
    input wire [AW-1:0]     n_rows,
    input wire              trigger
);
    localparam integer NUM_COL = DW/8; // increment address by DW/8 bytes, or 16 samples

    // trigger edge detection
    (* ASYNC_REG="TRUE" *) reg [2:0] trig_d = 0;
    always @(posedge axis_clk) begin
        trig_d <= {trig_d[1:0], trigger};
    end
    wire trigger_posedge = ~trig_d[2] & trig_d[1];

    assign bram_clk = axis_clk;
    assign bram_rst = ~axis_aresetn;
    assign s_axis_tready = 1'b1;

    // Internal signals
    reg [AW-1:0] vcnt=0;

    //BRAM Port B address control
    always @(posedge axis_clk) begin
        if (~axis_aresetn) begin
            bram_addr <= 0;
            // bram_we   <= 0;
            bram_en   <= 0;
        end else begin
            if (trigger_posedge) begin
                bram_addr <= 0;
                bram_en   <= 1'b1;
                vcnt <= 0;
            end else begin
                if (bram_en && s_axis_tvalid) begin
                    if (vcnt < n_rows-1) begin
                        bram_addr <= bram_addr + NUM_COL;
                        bram_en   <= 1'b1;
                        vcnt <= vcnt + 1'b1;
                    end else begin
                        bram_en <= 1'b0;
                        vcnt <= 0;
                    end
                end
            end
        end
    end
    assign bram_wdata = s_axis_tdata;
    assign bram_we = s_axis_tvalid ? {NUM_COL{1'b1}} : {NUM_COL{1'b0}};
endmodule