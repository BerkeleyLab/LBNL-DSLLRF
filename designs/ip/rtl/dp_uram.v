`timescale 1ns / 1ns

//  Xilinx UltraRAM True Dual Port Mode - Byte write.  This code implements
//  a parameterizable UltraRAM block with write/read on both ports in
//  No change behavior on both the ports . The behavior of this RAM is
//  when data is written, the output of RAM is unchanged w.r.t each port.
//  Only when write is inactive data corresponding to the address is
//  presented on the output port.
module dp_uram #(
    parameter AWIDTH = 12,  // Address Width
    parameter NUM_COL= 9,   // Number of columns
    parameter DWIDTH = 72,  // Data Width, (Byte * NUM_COL)
    parameter READ_LATENCY = 3, // Number of read cycles
    parameter NBPIPE = READ_LATENCY - 2    // Number of pipeline Registers
) (
    input wire clk,                     // Clock
    // Port A
    input wire [NUM_COL-1:0] wea,       // Write Enable
    input wire ena,                     // Memory Enable
    input wire [DWIDTH-1:0] dina,       // Data Input
    input wire [AWIDTH-1:0] addra,      // Address Input
    output reg [DWIDTH-1:0] douta,      // Data Output
    // Port B
    input wire [NUM_COL-1:0] web,       // Write Enable
    input wire enb,                     // Memory Enable
    input wire [DWIDTH-1:0] dinb,       // Data Input
    input wire [AWIDTH-1:0] addrb,      // Address Input
    output reg [DWIDTH-1:0] doutb       // Data Output
);

    (* ram_style = "ultra" *)
    reg [DWIDTH-1:0] mem [(1<<AWIDTH)-1:0];        // Memory Declaration

    reg [DWIDTH-1:0] memrega;
    reg [DWIDTH-1:0] mem_pipe_rega [NBPIPE-1:0];    // Pipelines for memory
    reg mem_en_pipe_rega [NBPIPE:0];                // Pipelines for memory enable

    reg [DWIDTH-1:0] memregb;
    reg [DWIDTH-1:0] mem_pipe_regb [NBPIPE-1:0];    // Pipelines for memory
    reg mem_en_pipe_regb [NBPIPE:0];                // Pipelines for memory enable
    integer i;

    // RAM : Both READ and WRITE have a latency of one
    always @ (posedge clk) begin
        if(ena) begin
            for(i = 0;i < NUM_COL; i = i + 1)
                if(wea[i]) mem[addra][i*8 +: 8] <= dina[i*8 +: 8];
            end
    end

    always @ (posedge clk) begin
        if(ena)
            if(~|wea) memrega <= mem[addra];
    end

    // The enable of the RAM goes through a pipeline to produce a
    // series of pipelined enable signals required to control the data
    // pipeline.
    always @ (posedge clk) begin
        mem_en_pipe_rega[0] <= ena;
        for (i=0; i<NBPIPE; i=i+1)
            mem_en_pipe_rega[i+1] <= mem_en_pipe_rega[i];
    end

    // RAM output data goes through a pipeline.
    always @ (posedge clk) begin
        if (mem_en_pipe_rega[0])
            mem_pipe_rega[0] <= memrega;
    end

    always @ (posedge clk) begin
        for (i = 0; i < NBPIPE-1; i = i+1)
            if (mem_en_pipe_rega[i+1])
                mem_pipe_rega[i+1] <= mem_pipe_rega[i];
    end

    always @ (posedge clk) begin
        if (mem_en_pipe_rega[NBPIPE])
            douta <= mem_pipe_rega[NBPIPE-1];
    end

    always @ (posedge clk) begin
        if(enb) begin
            for(i = 0;i<NUM_COL;i=i+1)
                if(web[i]) mem[addrb][i*8 +: 8] <= dinb[i*8 +: 8];
        end
    end

    always @ (posedge clk) begin
        if(enb)
            if(~|web) memregb <= mem[addrb];
    end

    // The enable of the RAM goes through a pipeline to produce a
    // series of pipelined enable signals required to control the data
    // pipeline.
    always @ (posedge clk) begin
        mem_en_pipe_regb[0] <= enb;
        for (i=0; i<NBPIPE; i=i+1)
            mem_en_pipe_regb[i+1] <= mem_en_pipe_regb[i];
    end

    // RAM output data goes through a pipeline.
    always @ (posedge clk) begin
        if (mem_en_pipe_regb[0]) mem_pipe_regb[0] <= memregb;
    end

    always @ (posedge clk) begin
        for (i = 0; i < NBPIPE-1; i = i+1)
            if (mem_en_pipe_regb[i+1]) mem_pipe_regb[i+1] <= mem_pipe_regb[i];
    end

    always @ (posedge clk) begin
        if (mem_en_pipe_regb[NBPIPE]) doutb <= mem_pipe_regb[NBPIPE-1];
    end

endmodule