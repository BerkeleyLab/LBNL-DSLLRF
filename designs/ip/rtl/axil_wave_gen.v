`timescale 1ns / 1ps

//-----------------------------------------------------------------------------
// AXI4-Lite Wrapper for Waveform Generator
// Provides AXI4-Lite control/status register interface to wave_gen module
//
// Total Samples Calculation:
//   Samples per cycle = OUT_DATA_WIDTH / 16 (bits per sample)
//   Total samples     = BANK_DEPTH * (OUT_DATA_WIDTH / 16)
//
// AXI4-Lite Address Width Calculation:
//   Registers use indices 0, 1, 2. Waveform memory starts at index 3.
//   Base Address Offset = 3 * (C_S_AXI_DATA_WIDTH / 8)
//   Memory Range = BANK_DEPTH * (OUT_DATA_WIDTH / 8) bytes
//   Minimum C_S_AXI_ADDR_WIDTH = $clog2(Base Offset + Memory Range)
//-----------------------------------------------------------------------------

module axil_wave_gen #(
    parameter integer C_S_AXI_DATA_WIDTH = 64,
    parameter integer C_S_AXI_ADDR_WIDTH = 18,
    parameter integer OUT_DATA_WIDTH     = 320,
    parameter integer GRANULE            = 64,
    parameter integer BANK_DEPTH         = 4096,
    parameter integer READ_LATENCY       = 3,
    parameter RAM_STYLE                  = "ultra"
) (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 s_axi_aclk CLK" *)
    (* X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF s_axi, ASSOCIATED_RESET s_axi_aresetn" *)
    input wire s_axi_aclk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 resetn RST" *)
    input wire s_axi_aresetn,

    // AXI4-Lite Write Address Channel
    input wire [C_S_AXI_ADDR_WIDTH-1:0] s_axi_awaddr,
    input wire s_axi_awvalid,
    output wire s_axi_awready,

    // AXI4-Lite Write Data Channel
    input wire [C_S_AXI_DATA_WIDTH-1:0] s_axi_wdata,
    input wire [(C_S_AXI_DATA_WIDTH/8)-1:0] s_axi_wstrb,
    input wire s_axi_wvalid,
    output wire s_axi_wready,

    // AXI4-Lite Write Response Channel
    output wire [1:0] s_axi_bresp,
    output wire s_axi_bvalid,
    input wire s_axi_bready,

    // AXI4-Lite Read Address Channel
    input wire [C_S_AXI_ADDR_WIDTH-1:0] s_axi_araddr,
    input wire s_axi_arvalid,
    output wire s_axi_arready,

    // AXI4-Lite Read Data Channel
    output wire [C_S_AXI_DATA_WIDTH-1:0] s_axi_rdata,
    output wire [1:0] s_axi_rresp,
    output wire s_axi_rvalid,
    input wire s_axi_rready,

    // AXI-Stream Master Output
    output wire [OUT_DATA_WIDTH-1:0] m_axis_tdata,
    output wire m_axis_tvalid,
    output wire m_axis_tlast,
    input wire m_axis_tready,

    // External Trigger
    input wire trigger
);

    //-------------------------------------------------------------------------
    // Parameters and Derived Values
    //-------------------------------------------------------------------------

    localparam integer AXI_DATA_WIDTH = C_S_AXI_DATA_WIDTH;
    localparam integer ADDR_LSB = $clog2((C_S_AXI_DATA_WIDTH/8));
    localparam integer SAMPLE_ADDR_WIDTH = $clog2(BANK_DEPTH);
    localparam integer AXI_ADDR_WIDTH = SAMPLE_ADDR_WIDTH + $clog2(OUT_DATA_WIDTH/8);

    // Register address map (each register occupies one AXI-data-width
    // aligned word, i.e. register index = addr[ADDR_LSB +: 2]):
    // index 0: Control Register (trigger, flush)
    // index 1: Wave Length Register
    // index 2: Status Register (busy)
    // index 3 and above: Waveform data memory (write-only)
    localparam [1:0] ADDR_CTRL   = 2'h0;
    localparam [1:0] ADDR_LENGTH = 2'h1;
    localparam [1:0] ADDR_STATUS = 2'h2;
    localparam integer WAVEFORM_BASE_ADDR = 3 << ADDR_LSB;  // register index 3

    //-------------------------------------------------------------------------
    // Write State Machine States
    //-------------------------------------------------------------------------
    // WR_IDLE : waiting for both address and data phases to complete
    // WR_PROC : address+data captured; for waveform writes wait for wave_gen
    //           to accept (int_wr_ready); for control writes this state is
    //           skipped in the same cycle the write is performed
    // WR_RESP : drive bvalid/bresp until master asserts bready

    localparam [1:0] WR_IDLE = 2'b00;
    localparam [1:0] WR_PROC = 2'b01;
    localparam [1:0] WR_RESP = 2'b10;

    //-------------------------------------------------------------------------
    // Internal Signals
    //-------------------------------------------------------------------------

    reg [1:0] wr_state;

    // Latched write address/data (captured independently, AXI4-Lite allows
    // address and data channels to complete in any order)
    reg wr_addr_valid;
    reg wr_data_valid;
    reg [C_S_AXI_ADDR_WIDTH-1:0] wr_addr;
    reg [C_S_AXI_DATA_WIDTH-1:0] wr_data;
    reg [(C_S_AXI_DATA_WIDTH/8)-1:0] wr_strb;

    // AXI4-Lite write/read control
    reg axi_awready;
    reg axi_wready;
    reg [1:0] axi_bresp;
    reg axi_bvalid;

    reg [C_S_AXI_ADDR_WIDTH-1:0] axi_araddr;
    reg axi_arready;
    reg [C_S_AXI_DATA_WIDTH-1:0] axi_rdata;
    reg [1:0] axi_rresp;
    reg axi_rvalid;

    // Control registers
    reg ctrl_trigger;
    reg ctrl_trigger_mode;
    reg [SAMPLE_ADDR_WIDTH-1:0] ctrl_wave_length;
    reg ctrl_flush;
    wire ctrl_busy;

    // Write interface to wave_gen
    wire int_wr_en;
    wire [AXI_ADDR_WIDTH-1:0] int_wr_addr;
    wire [AXI_DATA_WIDTH-1:0] int_wr_data;
    wire [(AXI_DATA_WIDTH/8)-1:0] int_wr_strb;
    wire int_wr_ready;

    //-------------------------------------------------------------------------
    // AXI4-Lite Output Assignments
    //-------------------------------------------------------------------------

    assign s_axi_awready = axi_awready;
    assign s_axi_wready = axi_wready;
    assign s_axi_bresp = axi_bresp;
    assign s_axi_bvalid = axi_bvalid;

    assign s_axi_arready = axi_arready;
    assign s_axi_rdata = axi_rdata;
    assign s_axi_rresp = axi_rresp;
    assign s_axi_rvalid = axi_rvalid;

    //-------------------------------------------------------------------------
    // Write Address Channel: latch independently of data channel/state
    //-------------------------------------------------------------------------

    always @(posedge s_axi_aclk) begin
        if (~s_axi_aresetn) begin
            axi_awready <= 1'b0;
            wr_addr_valid <= 1'b0;
            wr_addr <= {C_S_AXI_ADDR_WIDTH{1'b0}};
        end else begin
            axi_awready <= 1'b0;

            // Accept a new address only while none is currently latched
            // (i.e. we are not in the middle of processing a transaction)
            if (~wr_addr_valid && s_axi_awvalid) begin
                axi_awready <= 1'b1;
                wr_addr_valid <= 1'b1;
                wr_addr <= s_axi_awaddr;
            end

            // Release the latch once the transaction fully completes
            if (wr_state == WR_RESP && axi_bvalid && s_axi_bready) begin
                wr_addr_valid <= 1'b0;
            end
        end
    end

    //-------------------------------------------------------------------------
    // Write Data Channel: latch independently of address channel/state
    //-------------------------------------------------------------------------

    always @(posedge s_axi_aclk) begin
        if (~s_axi_aresetn) begin
            axi_wready <= 1'b0;
            wr_data_valid <= 1'b0;
            wr_data <= {C_S_AXI_DATA_WIDTH{1'b0}};
            wr_strb <= {(C_S_AXI_DATA_WIDTH/8){1'b0}};
        end else begin
            axi_wready <= 1'b0;

            // Accept new data only while none is currently latched
            if (~wr_data_valid && s_axi_wvalid) begin
                axi_wready <= 1'b1;
                wr_data_valid <= 1'b1;
                wr_data <= s_axi_wdata;
                wr_strb <= s_axi_wstrb;
            end

            // Release the latch once the transaction fully completes
            if (wr_state == WR_RESP && axi_bvalid && s_axi_bready) begin
                wr_data_valid <= 1'b0;
            end
        end
    end

    //-------------------------------------------------------------------------
    // Determine if the latched write targets waveform memory or a register
    //-------------------------------------------------------------------------

    wire wr_is_waveform = (wr_addr >= WAVEFORM_BASE_ADDR);

    //-------------------------------------------------------------------------
    // Main Write State Machine
    //-------------------------------------------------------------------------

    always @(posedge s_axi_aclk) begin
        if (~s_axi_aresetn) begin
            wr_state <= WR_IDLE;
            axi_bvalid <= 1'b0;
            axi_bresp <= 2'b0;
        end else begin
            case (wr_state)
                WR_IDLE: begin
                    // Both address and data phases must have completed
                    if (wr_addr_valid && wr_data_valid) begin
                        if (wr_is_waveform) begin
                            // Waveform write must wait for wave_gen to accept
                            wr_state <= WR_PROC;
                        end else begin
                            // Control register write completes immediately
                            wr_state <= WR_RESP;
                        end
                    end
                end

                WR_PROC: begin
                    // int_wr_en is asserted combinationally while in this
                    // state; move on once wave_gen accepts the write
                    if (int_wr_en && int_wr_ready) begin
                        wr_state <= WR_RESP;
                    end
                end

                WR_RESP: begin
                    if (~axi_bvalid) begin
                        axi_bvalid <= 1'b1;
                        axi_bresp <= 2'b00;  // OKAY
                    end else if (s_axi_bready) begin
                        axi_bvalid <= 1'b0;
                        wr_state <= WR_IDLE;
                    end
                end

                default: wr_state <= WR_IDLE;
            endcase
        end
    end

    //-------------------------------------------------------------------------
    // Internal Write Interface to wave_gen
    //-------------------------------------------------------------------------

    assign int_wr_en = (wr_state == WR_PROC);
    assign int_wr_addr = (wr_addr - WAVEFORM_BASE_ADDR);
    assign int_wr_data = wr_data;
    assign int_wr_strb = wr_strb;

    //-------------------------------------------------------------------------
    // AXI4-Lite Read Address Channel
    //-------------------------------------------------------------------------

    always @(posedge s_axi_aclk) begin
        if (~s_axi_aresetn) begin
            axi_arready <= 1'b0;
            axi_araddr <= {C_S_AXI_ADDR_WIDTH{1'b0}};
        end else begin
            if (~axi_arready && s_axi_arvalid) begin
                axi_arready <= 1'b1;
                axi_araddr <= s_axi_araddr;
            end else begin
                axi_arready <= 1'b0;
            end
        end
    end

    //-------------------------------------------------------------------------
    // AXI4-Lite Read Data Channel
    //-------------------------------------------------------------------------

    always @(posedge s_axi_aclk) begin
        if (~s_axi_aresetn) begin
            axi_rvalid <= 1'b0;
            axi_rresp <= 2'b0;
            axi_rdata <= {C_S_AXI_DATA_WIDTH{1'b0}};
        end else begin
            if (axi_arready && s_axi_arvalid && ~axi_rvalid) begin
                axi_rvalid <= 1'b1;
                axi_rresp <= 2'b0;  // OKAY response

                // Decode address and read appropriate register
                case (axi_araddr[ADDR_LSB+:2])
                    ADDR_CTRL: begin
                        axi_rdata <= {{C_S_AXI_DATA_WIDTH-3{1'b0}}, ctrl_trigger_mode, ctrl_flush, ctrl_trigger};
                    end
                    ADDR_LENGTH: begin
                        axi_rdata <= {{C_S_AXI_DATA_WIDTH-SAMPLE_ADDR_WIDTH{1'b0}}, ctrl_wave_length};
                    end
                    ADDR_STATUS: begin
                        axi_rdata <= {{C_S_AXI_DATA_WIDTH-1{1'b0}}, ctrl_busy};
                    end
                    default: begin
                        axi_rdata <= {C_S_AXI_DATA_WIDTH{1'b0}};
                    end
                endcase
            end else begin
                if (s_axi_rready && axi_rvalid) begin
                    axi_rvalid <= 1'b0;
                end
            end
        end
    end

    //-------------------------------------------------------------------------
    // Control Register Write Logic
    //-------------------------------------------------------------------------

    always @(posedge s_axi_aclk) begin
        if (~s_axi_aresetn) begin
            ctrl_trigger <= 1'b0;
            ctrl_trigger_mode <= 1'b0;
            ctrl_wave_length <= {SAMPLE_ADDR_WIDTH{1'b0}};
            ctrl_flush <= 1'b0;
        end else begin
            // Auto-clear trigger and flush after one cycle
            ctrl_trigger <= 1'b0;
            ctrl_flush <= 1'b0;

            // Perform the register write exactly once, on the cycle the
            // state machine decides this is a control-register write
            // (i.e. transitioning from WR_IDLE directly into WR_RESP)
            if (wr_state == WR_IDLE && wr_addr_valid && wr_data_valid && ~wr_is_waveform) begin
                case (wr_addr[ADDR_LSB+:2])
                    ADDR_CTRL: begin
                        // Bit 0: trigger, Bit 1: flush, Bit 2: trigger_mode
                        if (wr_strb[0]) begin
                            ctrl_trigger <= wr_data[0];
                            ctrl_flush <= wr_data[1];
                            ctrl_trigger_mode <= wr_data[2];
                        end
                    end
                    ADDR_LENGTH: begin
                        // Wave length register
                        if (wr_strb[0]) begin
                            ctrl_wave_length <= wr_data[SAMPLE_ADDR_WIDTH-1:0];
                        end
                    end
                    default: begin
                        // Status register is read-only
                    end
                endcase
            end
        end
    end

    //-------------------------------------------------------------------------
    // Waveform Generator Instance
    //-------------------------------------------------------------------------

    wave_gen #(
        .AXI_DATA_WIDTH(C_S_AXI_DATA_WIDTH),
        .OUT_DATA_WIDTH(OUT_DATA_WIDTH),
        .GRANULE(GRANULE),
        .BANK_DEPTH(BANK_DEPTH),
        .READ_LATENCY(READ_LATENCY),
        .RAM_STYLE(RAM_STYLE)
    ) u_wave_gen (
        .clk(s_axi_aclk),
        .rst_n(s_axi_aresetn),

        // Write interface from AXI-Lite
        .axi_wr_en(int_wr_en),
        .axi_wr_addr(int_wr_addr),
        .axi_wr_data(int_wr_data),
        .axi_wr_strb(int_wr_strb),
        .axi_wr_ready(int_wr_ready),

        // Control interface
        .trigger(ctrl_trigger_mode ? trigger : ctrl_trigger),
        .wave_length(ctrl_wave_length),
        .flush_wr(ctrl_flush),
        .busy(ctrl_busy),

        // Output AXI-Stream
        .m_axis_tdata(m_axis_tdata),
        .m_axis_tvalid(m_axis_tvalid),
        .m_axis_tlast(m_axis_tlast),
        .m_axis_tready(m_axis_tready)
    );

    //-------------------------------------------------------------------------
    // Parameter Validation
    //-------------------------------------------------------------------------
    initial begin
        // The address width must be sufficient to cover both registers and waveform memory
        // Max address is roughly WAVEFORM_BASE_ADDR + (BANK_DEPTH * OUT_DATA_WIDTH / 8)
        if ((1 << C_S_AXI_ADDR_WIDTH) < (WAVEFORM_BASE_ADDR + (BANK_DEPTH * OUT_DATA_WIDTH / 8))) begin
            $error("C_S_AXI_ADDR_WIDTH (%0d) is too small for BANK_DEPTH (%0d) and OUT_DATA_WIDTH (%0d). Minimum required is %0d.",
                C_S_AXI_ADDR_WIDTH, BANK_DEPTH, OUT_DATA_WIDTH,
                $clog2(WAVEFORM_BASE_ADDR + (BANK_DEPTH * OUT_DATA_WIDTH / 8)));
        end

        $display("================================================");
        $display("AXI4-Lite Waveform Generator Wrapper");
        $display("================================================");
        $display("  Control Width   : %0d bits", C_S_AXI_DATA_WIDTH);
        $display("  Address Width   : %0d bits", C_S_AXI_ADDR_WIDTH);
        $display("  Output Width    : %0d bits", OUT_DATA_WIDTH);
        $display("  Samples Available: %0d (16-bit)", BANK_DEPTH * (OUT_DATA_WIDTH / 16));
        $display("================================================");
    end

endmodule
