//-----------------------------------------------------------------------------
// Parameterized Waveform Capture
//
// Mirror of wave_gen: an AXI-Stream of ROW_WIDTH-bit rows is written into a banked_mem (port B), and the bus side reads
// it as a flat byte array in sample order (port A, the same address mapping as wave_gen), so row r holds bytes
// ROW_WIDTH/8 * r and up. With ROW_WIDTH = 320 (20 int16 samples at 250 MHz) the capture keeps up with a 5 GSPS RF-ADC
// stream (160 bits at 500 MHz, converted 2:1 in front). See doc/wave_gen.md.
//
// On trigger (ignored while capturing), the next min(n_rows, DEPTH) valid beats are written to rows 0, 1, ...; the row
// address advances only on valid beats, so gaps in tvalid do not leave holes. write_done pulses for one cycle after the
// last row; n_rows = 0 ignores the trigger. s_axis_tready is always 1 (the RFDC does not take back-pressure).
// The bus port can read (and write) at any time.
//
// One-shot mode (oneshot = 1): a trigger starts a capture only while armed; arm (a pulse) sets armed and clears
// done, the capture start clears armed, and done is set when it completes. Software arms, waits for done (or the
// write_done interrupt) and reads a buffer that cannot be overwritten meanwhile. oneshot = 0 captures on every
// trigger (the adc_capture behaviour). capture_count counts completed captures.
//-----------------------------------------------------------------------------

module wave_cap #(
    parameter AXI_DATA_WIDTH = 256,     // power of 2, <= ROW_WIDTH
    parameter ROW_WIDTH      = 320,     // multiple of GRANULE
    parameter GRANULE        = 64,
    parameter DEPTH          = 2048,    // rows; power of 2
    parameter N_ROWS_WIDTH   = 16,
    parameter RAM_STYLE      = "block"  // "ultra" or "block"
) (
    input  wire                         clk,
    input  wire                         rst_n,

    // Memory port (bus side)
    input  wire                         axi_wr_en,
    input  wire [AXI_ADDR_WIDTH-1:0]    axi_wr_addr,
    input  wire [AXI_DATA_WIDTH-1:0]    axi_wr_data,
    input  wire [AXI_DATA_WIDTH/8-1:0]  axi_wr_strb,
    input  wire                         axi_rd_en,
    input  wire [AXI_ADDR_WIDTH-1:0]    axi_rd_addr,
    output wire [AXI_DATA_WIDTH-1:0]    axi_rd_data,
    output wire                         axi_rd_valid,

    // Capture control
    input  wire                         trigger,
    input  wire [N_ROWS_WIDTH-1:0]      n_rows,
    output wire                         busy,
    output reg                          write_done,
    input  wire                         oneshot,
    input  wire                         arm,
    output reg                          armed,
    output reg                          done,
    output reg  [15:0]                  capture_count,

    // Input AXI-Stream
    input  wire [ROW_WIDTH-1:0]         s_axis_tdata,
    input  wire                         s_axis_tvalid,
    output wire                         s_axis_tready
);

    localparam integer ROW_ADDR_WIDTH = $clog2(DEPTH);
    localparam integer AXI_ADDR_WIDTH = ROW_ADDR_WIDTH + $clog2(ROW_WIDTH/8);

    assign s_axis_tready = 1'b1;

    reg                       capturing;
    reg [ROW_ADDR_WIDTH-1:0]  wr_row;
    reg [ROW_ADDR_WIDTH-1:0]  last_row;
    assign busy = capturing;

    wire wr_beat = capturing && s_axis_tvalid;

    always @(posedge clk) begin
        if (!rst_n) begin
            capturing  <= 1'b0;
            wr_row     <= {ROW_ADDR_WIDTH{1'b0}};
            last_row   <= {ROW_ADDR_WIDTH{1'b0}};
            write_done <= 1'b0;
            armed      <= 1'b0;
            done       <= 1'b0;
            capture_count <= 16'd0;
        end else begin
            write_done <= 1'b0;
            if (arm) begin
                armed <= 1'b1;
                done  <= 1'b0;
            end
            if (!capturing) begin
                if (trigger && n_rows != 0 && (!oneshot || armed)) begin
                    capturing <= 1'b1;
                    armed     <= 1'b0;
                    wr_row    <= {ROW_ADDR_WIDTH{1'b0}};
                    last_row  <= (n_rows >= DEPTH) ? {ROW_ADDR_WIDTH{1'b1}} : n_rows[ROW_ADDR_WIDTH-1:0] - 1'b1;
                end
            end else if (wr_beat) begin
                if (wr_row == last_row) begin
                    capturing  <= 1'b0;
                    write_done <= 1'b1;
                    done       <= 1'b1;
                    capture_count <= capture_count + 1'b1;
                end else begin
                    wr_row <= wr_row + 1'b1;
                end
            end
        end
    end

    banked_mem #(
        .BUS_DATA_WIDTH (AXI_DATA_WIDTH),
        .ROW_WIDTH      (ROW_WIDTH),
        .GRANULE        (GRANULE),
        .DEPTH          (DEPTH),
        .RAM_STYLE      (RAM_STYLE)
    ) u_mem (
        .clk        (clk),
        .rst_n      (rst_n),
        .a_wr_en    (axi_wr_en),
        .a_wr_addr  (axi_wr_addr),
        .a_wr_data  (axi_wr_data),
        .a_wr_strb  (axi_wr_strb),
        .a_rd_en    (axi_rd_en),
        .a_rd_addr  (axi_rd_addr),
        .a_rd_data  (axi_rd_data),
        .a_rd_valid (axi_rd_valid),
        .b_en       (wr_beat),
        .b_we       (1'b1),
        .b_addr     (wr_row),
        .b_wdata    (s_axis_tdata),
        .b_rdata    ()
    );

endmodule
