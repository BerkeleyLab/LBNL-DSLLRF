`timescale 1ns / 1ns
// true dual-port ram
module dp_bram #(
    parameter DW = 32,
    parameter AW = 6  // in bytes
) (
    input  wire clka,
    input  wire rsta,
    input  wire              ena,
    input  wire [31:0]       addra,
    input  wire [DW-1:0]     dina,
    input  wire [DW/8-1:0]   wea,
    output reg  [DW-1:0]     douta,
    input  wire clkb,
    input  wire rstb,
    input  wire              enb,
    input  wire [31:0]       addrb,
    output reg  [DW-1:0]     doutb
);

    (* ram_style = "block" *) reg [7:0] mem [0:(2**AW) - 1];
    integer i;

    // port a read / write
    always @(posedge clka) begin
        if (ena) begin
            for (i = 0; i < DW/8; i = i + 1) begin
                if (wea[i]) mem[addra + i] <= dina[i*8 +: 8];
                douta[i*8 +: 8] <= mem[addra + i];
            end
        end
    end

    // port b read
    always @(posedge clkb) begin
        if (enb) begin
            for (i = 0; i < DW/8; i = i + 1) begin
                doutb[i*8 +: 8] <= mem[addrb + i];
            end
        end
    end

endmodule
