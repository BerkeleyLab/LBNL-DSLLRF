`timescale 1ns / 1ns

// Streams data from a BRAM to an AXIS interface.

module dac_streamer #(
    parameter integer DW = 256,     // 16 samples, 16 bits data == 32 bytes
    parameter integer AW = 12,      // 2**AW number of rows, total number of samples: 2**AW * DW/16
    parameter integer READ_LATENCY = 3           // Number of read cycles
) (
    (* X_INTERFACE_PARAMETER = "MASTER_TYPE BRAM_CTRL, READ_WRITE_MODE READ, MEM_SIZE 131072, MEM_WIDTH 256" *)

    (* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 BRAM_A DIN" *)
    output wire [DW-1:0] bram_wdata, // Data In Bus (optional)

    (* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 BRAM_A WE" *)
    output [DW/8-1:0] bram_we, // Byte Enables (optional)

    (* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 BRAM_A EN" *)
    output reg bram_en, // Chip Enable Signal (optional)

    (* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 BRAM_A DOUT" *)
    input wire [DW-1:0] bram_rdata, // Data Out Bus (optional)

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
    output wire [DW-1:0]     m_axis_tdata,
    input  wire              m_axis_tready,
    output wire              m_axis_tvalid,

    // Control Input Parameters
    input wire [AW-1:0] n_rows,
    input wire enable,
    input wire trigger
);
    localparam integer NBPIPE = READ_LATENCY - 2;   // Number of pipeline Registers
    localparam integer NUM_COL = DW/8; // increment address by DW/8 bytes, or 16 samples
    localparam integer TRIG_DELAY = 1;
    // trigger edge detection
    (* ASYNC_REG="TRUE" *) reg [2:0] trig_d = 0;
    always @(posedge axis_clk) begin
        trig_d <= {trig_d[1:0], trigger};
    end
    wire trigger_posedge = ~trig_d[2] & trig_d[1];

    // Internal signals
    reg [AW-1:0] vcnt=0;

    // Assign BRAM interface signals
    assign bram_wdata = 0;
    assign bram_clk = axis_clk;
    assign bram_rst = ~axis_aresetn;
    assign bram_we = {NUM_COL{1'b0}};

    // Pipeline delay for m_axis_tvalid, 2 cycles on top of the BRAM read latency
    reg [NBPIPE+1:0] tvalid_pipe = 0;
    // Main logic
    always @(posedge axis_clk) begin
        tvalid_pipe <= {tvalid_pipe[NBPIPE:0], enable & bram_en};

        if (~axis_aresetn) begin
            bram_en <= 0;
            bram_addr <= 0;
            vcnt <= 0;
            tvalid_pipe <= 0;
        end else begin
            if (trigger_posedge) begin
                bram_en <= 1'b1;
                bram_addr <= 0;
                vcnt <= 0;
            end else begin
                if (bram_en) begin
                    if (vcnt < n_rows-1) begin
                        bram_addr <= bram_addr + NUM_COL;
                        bram_en <= 1'b1;
                        vcnt <= vcnt + 1'b1;
                    end else begin
                        bram_en <= 0;
                    end
                end
            end
        end
    end

    // fill in zeros which is also valid data
    wire tvalid = tvalid_pipe[NBPIPE+1];
    assign m_axis_tvalid = 1'b1;
    assign m_axis_tdata  = tvalid ? bram_rdata : {DW{1'b0}};

endmodule
