`timescale 1ns / 1ns

module dac_streamer_tb;

    // Parameters
    parameter int SAMP_DW = 16;
    parameter int SAMP_NUM = 16;
    parameter int DW = SAMP_DW * SAMP_NUM;
    parameter int AW = 5;
    parameter int READ_LATENCY = 3;        // number of cycles for ram read
    parameter int NUM_ROW = 10;   // number of rows per trigger
    parameter int NUM_COL = DW/8;      // number of bytes per word (32 bytes for 16 samples)
    parameter int AW_WORD = $clog2(NUM_COL);

    // Signals
    logic axis_clk;
    logic axis_aresetn;
    logic enable;
    logic trigger;

    logic [DW-1:0] bram_dac_wdata;
    logic [DW/8-1:0] bram_dac_we;
    logic bram_dac_en;
    logic [DW-1:0] bram_dac_rdata;
    logic [31:0] bram_dac_addr;
    logic bram_dac_clk;
    logic bram_dac_rst;

    logic [DW-1:0] axis_tdata;
    logic axis_tready;
    logic axis_tvalid;
    logic [AW-1:0] bram_dac_addr_word;
    logic [AW-1:0] dac_n_rows = NUM_ROW;
    assign bram_dac_addr_word = bram_dac_addr >> AW_WORD;

    // Instantiate the dac_streamer
    dac_streamer #(
        .SAMP_DW(SAMP_DW), .SAMP_NUM(SAMP_NUM),
        .AW(AW), .READ_LATENCY(READ_LATENCY)
    ) dac_inst (
        .bram_wdata     (bram_dac_wdata),
        .bram_we        (bram_dac_we),
        .bram_en        (bram_dac_en),
        .bram_rdata     (bram_dac_rdata),
        .bram_addr      (bram_dac_addr),
        .bram_clk       (bram_dac_clk),
        .bram_rst       (bram_dac_rst),
        .axis_clk,
        .axis_aresetn,
        .m_axis_tdata   (axis_tdata),
        .m_axis_tready  (axis_tready),
        .m_axis_tvalid  (axis_tvalid),
        .n_rows         (dac_n_rows),
        .enable         (1'b1),
        .trigger
    );

    dp_uram #(
        .DWIDTH(DW), .AWIDTH(AW), .READ_LATENCY(READ_LATENCY)
    ) dp_bram_dac (
        .clk       (bram_dac_clk),
        .ena       (1'b0),
        .addra     ({AW{1'b0}}),
        .wea       ({NUM_COL{1'b0}}),
        .dina      ({DW{1'b0}}),
        .enb       (bram_dac_en),
        .web       (bram_dac_we),
        .dinb      (bram_dac_wdata),
        .doutb     (bram_dac_rdata),
        .addrb     (bram_dac_addr_word)
    );

    // Initialize test pattern
    initial begin
        for (int i = 0; i < 2**dp_bram_dac.AWIDTH-1; i++) begin
            for (int j = 0; j < NUM_COL; j++) begin
                dp_bram_dac.mem[i][j*8 +: 8] = i << 4 | j & 4'hF;
            end
        end
        #1200;
        $error("Simulation timeout");
        $stop;
    end

    // Instantiate the ADC Capture
    // write to adc bram from axis
    logic [DW-1:0] bram_adc_wdata;
    logic [DW/8-1:0] bram_adc_we;
    logic bram_adc_en;
    logic [DW-1:0] bram_adc_rdata;
    logic [31:0] bram_adc_addr;
    logic bram_adc_clk;
    logic bram_adc_rst;
    logic [AW-1:0] bram_adc_addr_word;
    // Additional latency for complete read and verification.
    // In reality, the adc_nrows = NUM_ROW, and delayed samples will be dropped.
    logic [AW-1:0] adc_nrows = NUM_ROW + READ_LATENCY;
    assign bram_adc_addr_word = bram_adc_addr >> AW_WORD;

    adc_capture #(
        .SAMP_DW(SAMP_DW), .SAMP_NUM(SAMP_NUM), .AW(AW)
    ) adc_inst (
        .bram_wdata     (bram_adc_wdata),   // output
        .bram_we        (bram_adc_we),      // output
        .bram_en        (bram_adc_en),      // output
        .bram_rdata     (bram_adc_rdata),   // input
        .bram_addr      (bram_adc_addr),    // output
        .bram_clk       (bram_adc_clk),     // output
        .bram_rst       (bram_adc_rst),     // output
        .axis_clk,
        .axis_aresetn,
        .s_axis_tdata   (axis_tdata),
        .s_axis_tready  (axis_tready),
        .s_axis_tvalid  (axis_tvalid),
        .n_rows         (adc_nrows),
        .trigger
    );

    dp_uram #(
        .DWIDTH(DW), .AWIDTH(AW), .READ_LATENCY(READ_LATENCY)
    ) dp_bram_adc (
        .clk       (bram_adc_clk),
        .ena       (1'b0),
        .addra     ({AW{1'b0}}),
        .wea       ({NUM_COL{1'b0}}),
        .dina      ({DW{1'b0}}),
        .enb       (bram_adc_en),
        .web       (bram_adc_we),
        .dinb      (bram_adc_wdata),
        .doutb     (bram_adc_rdata),
        .addrb     (bram_adc_addr_word)
    );

    // Clock generation
    initial begin
        axis_clk = 0;
        forever #2 axis_clk = ~axis_clk; // 250 MHz clock
    end

    // Task to trigger the streaming
    task trigger_streaming;
        begin
            @ (posedge axis_clk);
            $display("Time: %g ns, Triggered the streaming...", $time);
            trigger = 1;
            @ (posedge axis_clk);
            trigger = 0;
        end
    endtask

    task verify_memory_content;
        int j;
        begin
            @ (negedge bram_adc_en);
            @ (posedge axis_clk);
            $display("Time: %g ns, Memory content verification started...", $time);
            // Verification for checking the memory content of dp_bram_adc against dp_bram_dac
            for (int i = 0; i < NUM_ROW; i++) begin
                j = i + READ_LATENCY;
                // $display("dp_bram_dac.mem[%02d]: %h\ndp_bram_adc.mem[%02d]: %h,",
                //         i, dp_bram_dac.mem[i], j, dp_bram_adc.mem[j]);
                if (dp_bram_dac.mem[i] !== dp_bram_adc.mem[j]) begin
                    $error(
                        "Memory content mismatch at address %0d: expected %h, got %h",
                        i, dp_bram_dac.mem[i], dp_bram_adc.mem[j]);
                    $stop;
                end
            end

            $display("Time: %g ns, Memory content verification passed.", $time);
        end
    endtask

    int j;
    // Test sequence
    initial begin
        // Initialize signals
        axis_aresetn = 0;
        trigger = 0;

        // Reset
        repeat (2) @(posedge axis_clk);
        axis_aresetn = 1;

        repeat (3) begin
            // Trigger the streaming
            trigger_streaming();

            verify_memory_content();
        end

        $finish;
    end

    // Dump waveforms
    initial begin
        $dumpfile("dac_streamer_tb.vcd");
        $dumpvars(0, dac_streamer_tb);
    end

    always @(posedge axis_clk) begin
        if (axis_tvalid && axis_tready && dac_inst.pulse_valid_pipe) begin
            $display("Time: %g ns, AXIS TDATA: %h", $time, axis_tdata);
        end
    end

endmodule
