`timescale 1 ns / 1 ps

/* An AXI peripheral to readback some of these diagnostic ports
 */

module diag_readback #(
  // USER Parameters
  parameter DWIDTH = 256,
  // AXI4LITE Parameters
  parameter integer C_S_AXI_DATA_WIDTH  = 32,
  parameter integer C_S_AXI_ADDR_WIDTH  = 8
)(
  // USER Ports
  input [7:0] trigger_counter,
  input [7:0] rollover_counter,
  input [7:0] tvalid_counter,
  input [DWIDTH-1:0] first_tdata,
  input [DWIDTH-1:0] last_tdata,
  // AXI4LITE Ports
  input wire  s_axi_aclk,
  input wire  s_axi_aresetn,
  input wire [C_S_AXI_ADDR_WIDTH-1 : 0] s_axi_awaddr,
  input wire [2 : 0] s_axi_awprot,
  input wire  s_axi_awvalid,
  output wire  s_axi_awready,
  input wire [C_S_AXI_DATA_WIDTH-1 : 0] s_axi_wdata,
  input wire [(C_S_AXI_DATA_WIDTH/8)-1 : 0] s_axi_wstrb,
  input wire  s_axi_wvalid,
  output wire  s_axi_wready,
  output wire [1 : 0] s_axi_bresp,
  output wire  s_axi_bvalid,
  input wire  s_axi_bready,
  input wire [C_S_AXI_ADDR_WIDTH-1 : 0] s_axi_araddr,
  input wire [2 : 0] s_axi_arprot,
  input wire  s_axi_arvalid,
  output wire  s_axi_arready,
  output wire [C_S_AXI_DATA_WIDTH-1 : 0] s_axi_rdata,
  output wire [1 : 0] s_axi_rresp,
  output wire  s_axi_rvalid,
  input wire  s_axi_rready
);

// Number of Host-Accessible Registers = (1<<HA_REG_AW) = 8
localparam integer HA_REG_AW = 5; // clog2(2*(DWIDTH/32) + 2) = 18 registers; need 5 bits

// local parameter for addressing 32 bit / 64 bit C_S_AXI_DATA_WIDTH
// ADDR_LSB is used for addressing 32/64 bit registers/memories
// ADDR_LSB = 2 for 32 bits (n downto 2)
// ADDR_LSB = 3 for 64 bits (n downto 3)
localparam integer ADDR_LSB = (C_S_AXI_DATA_WIDTH/32) + 1;

// =================== Host-Accessible Registers ========================
// Note that they are implemented as a RAM for convenience/portability, but in
// general will not synthesize to block ram due to continuous access of individual
// elements.
localparam integer NUM_HA_REGS = (1 << HA_REG_AW);
//reg [C_S_AXI_DATA_WIDTH-1:0] ha_ram [0:NUM_HA_REGS-1];
//reg [NUM_HA_REGS-1:0] ha_strobes=0;
integer byte_index;

// Need to cross the ref_clk->axi_clk boundary
// Let's just lazily cross this domain and consume extra resources
reg [DWIDTH-1:0] first_tdata_ms=0, first_tdata_axi=0;
reg [DWIDTH-1:0] last_tdata_ms=0, last_tdata_axi=0;
reg [7:0] trigger_counter_ms=0, trigger_counter_axi=0;
reg [7:0] rollover_counter_ms=0, rollover_counter_axi=0;
reg [7:0] tvalid_counter_ms=0, tvalid_counter_axi=0;

always @(posedge s_axi_aclk) begin
  first_tdata_ms <= first_tdata;
  first_tdata_axi <= first_tdata_ms;

  last_tdata_ms <= last_tdata;
  last_tdata_axi <= last_tdata_ms;

  trigger_counter_ms <= trigger_counter;
  trigger_counter_axi <= trigger_counter_ms;

  rollover_counter_ms <= rollover_counter;
  rollover_counter_axi <= rollover_counter_ms;

  tvalid_counter_ms <= tvalid_counter;
  tvalid_counter_axi <= tvalid_counter_ms;

end

localparam [HA_REG_AW-1:0] NSLICES = DWIDTH/32;

// ========================= Memory Map =================================
// Addr     Slice     Access  Usage
// --------------------------------
// 0        [31:0]    RO      first_tdata[31:0]
// 1        [31:0]    RO      first_tdata[63:32]
// 2        [31:0]    RO      first_tdata[95:64]
// 3        [31:0]    RO      first_tdata[127:96]
// 4        [31:0]    RO      first_tdata[159:128]
// 5        [31:0]    RO      first_tdata[191:160]
// 6        [31:0]    RO      first_tdata[223:192]
// 7        [31:0]    RO      first_tdata[255:224]
// 8        [31:0]    RO      last_tdata[31:0]
// 9        [31:0]    RO      last_tdata[63:32]
// 10       [31:0]    RO      last_tdata[95:64]
// 11       [31:0]    RO      last_tdata[127:96]
// 12       [31:0]    RO      last_tdata[159:128]
// 13       [31:0]    RO      last_tdata[191:160]
// 14       [31:0]    RO      last_tdata[223:192]
// 15       [31:0]    RO      last_tdata[255:224]
// 16       [7:0]     RO      trigger_counter
// 17       [7:0]     RO      rollover_counter
// 18       [7:0]     RO      tvalid_counter

// ====================== AXI4LITE signals ==============================
reg [C_S_AXI_ADDR_WIDTH-1:0] axi_awaddr=0, axi_araddr=0;
reg [C_S_AXI_DATA_WIDTH-1:0] axi_rdata=0;
reg axi_awready=1'b0, axi_wready=1'b0, axi_bvalid=1'b0, axi_arready=1'b0, axi_rvalid=1'b0;
reg [1:0] axi_bresp=0, axi_rresp=0;
reg aw_en;

// ========================= Bus Writes =================================
/*
wire ha_reg_wren = axi_wready && s_axi_wvalid && axi_awready && s_axi_awvalid;
integer nreg;
wire [HA_REG_AW-1:0] w_reg_sel = axi_awaddr[ADDR_LSB+HA_REG_AW-1:ADDR_LSB];
always @(posedge s_axi_aclk) begin
  ha_strobes <= 0;
  if (s_axi_aresetn == 1'b0) begin
    for (nreg = 0; nreg<NUM_HA_REGS; nreg=nreg+1) begin
      ha_ram[nreg] <= 0;
    end
  end else begin
    if (ha_reg_wren) begin
      // Respective byte enables are asserted as per write strobes
      case (w_reg_sel)
        // USER: Address-specific clobbering of default write behavior
        default: begin
          for ( byte_index = 0; byte_index <= (C_S_AXI_DATA_WIDTH/8)-1; byte_index = byte_index+1 ) begin
            if ( s_axi_wstrb[byte_index] == 1 ) begin
              // Respective byte enables are asserted as per write strobes 
              // Peripheral register 7
              ha_ram[w_reg_sel][(byte_index*8) +: 8] <= s_axi_wdata[(byte_index*8) +: 8];
              ha_strobes[w_reg_sel] <= 1'b1;
            end
          end
        end
      endcase
    end
  end
end
*/

// ========================== Bus Reads =================================
// Peripheral register read enable is asserted when valid address is available
// and the peripheral is ready to accept the read address.
wire [HA_REG_AW-1:0] r_reg_sel = axi_araddr[ADDR_LSB+HA_REG_AW-1:ADDR_LSB];
wire ha_reg_rden = axi_arready & s_axi_arvalid & ~axi_rvalid;
// Note: reg_data_out is actually combinational (i.e. wire), but using always @(*) case statement
reg [C_S_AXI_DATA_WIDTH-1:0] reg_data_out;
always @(*) begin
  if (r_reg_sel < NSLICES) begin
    reg_data_out = first_tdata_axi[32*(r_reg_sel+1)-1-:32];
  end else if (r_reg_sel < 2*NSLICES) begin
    reg_data_out = last_tdata_axi[32*(r_reg_sel+1)-1-:32];
  end else if (r_reg_sel == 16) begin
    reg_data_out = {24'h000000, trigger_counter_axi};
  end else if (r_reg_sel == 17) begin
    reg_data_out = {24'h000000, rollover_counter_axi};
  end else if (r_reg_sel == 18) begin
    reg_data_out = {24'h000000, tvalid_counter_axi};
  end
  /*
  case (r_reg_sel)
    // USER: Address-specific clobbering of default read behavior
    0: reg_data_out = frequency_axi;
    default : reg_data_out = ha_ram[r_reg_sel];
  endcase
  */
end

always @(posedge s_axi_aclk) begin
  if (s_axi_aresetn == 1'b0) begin
    axi_rdata  <= 0;
  end else begin
    // When there is a valid read address (s_axi_arvalid) with
    // acceptance of read address by the peripheral (axi_arready),
    // output the read dada 
    if (ha_reg_rden) begin
      axi_rdata <= reg_data_out;  // register read data
    end
  end
end

// ============== AXI-4 Lite Bus Protocol Implementation ================
// I/O Connections assignments
assign s_axi_awready  = axi_awready;
assign s_axi_wready  = axi_wready;
assign s_axi_bresp  = axi_bresp;
assign s_axi_bvalid  = axi_bvalid;
assign s_axi_arready  = axi_arready;
assign s_axi_rdata  = axi_rdata;
assign s_axi_rresp  = axi_rresp;
assign s_axi_rvalid  = axi_rvalid;

always @(posedge s_axi_aclk) begin
  if (s_axi_aresetn == 1'b0) begin
    axi_awready <= 1'b0;
    aw_en       <= 1'b1;
    axi_awaddr  <= 0;
    axi_wready  <= 1'b0;
    axi_bvalid  <= 0;
    axi_bresp   <= 2'b0;
    axi_arready <= 1'b0;
    axi_araddr  <= 0;
    axi_rvalid  <= 0;
    axi_rresp   <= 0;
  end else begin

    // Implement axi_awready generation
    if (~axi_awready && s_axi_awvalid && s_axi_wvalid && aw_en) begin
      // peripheral is ready to accept write address when
      // there is a valid write address and write data
      // on the write address and data bus. This design
      // expects no outstanding transactions.
      axi_awready <= 1'b1;
      aw_en <= 1'b0;
    end else if (s_axi_bready && axi_bvalid) begin
      aw_en <= 1'b1;
      axi_awready <= 1'b0;
    end else begin
      axi_awready <= 1'b0;
    end

    // Implement axi_awaddr generation
    if (~axi_awready && s_axi_awvalid && s_axi_wvalid && aw_en) begin
      // Write Address latching
      axi_awaddr <= s_axi_awaddr;
    end

    // Implement axi_wready generation
    if (~axi_wready && s_axi_wvalid && s_axi_awvalid && aw_en ) begin
      // peripheral is ready to accept write data when
      // there is a valid write address and write data
      // on the write address and data bus. This design
      // expects no outstanding transactions.
      axi_wready <= 1'b1;
    end else begin
      axi_wready <= 1'b0;
    end

    // Implement write response logic generation
    if (axi_awready && s_axi_awvalid && ~axi_bvalid && axi_wready && s_axi_wvalid) begin
      // indicates a valid write response is available
      axi_bvalid <= 1'b1;
      axi_bresp  <= 2'b0; // 'OKAY' response
    end else begin
      if (s_axi_bready && axi_bvalid) begin
        //check if bready is asserted while bvalid is high) 
        //(there is a possibility that bready is always asserted high)
        axi_bvalid <= 1'b0;
      end
    end

    // Implement axi_arready generation
    if (~axi_arready && s_axi_arvalid) begin
      // indicates that the peripheral has acceped the valid read address
      axi_arready <= 1'b1;
      // Read address latching
      axi_araddr  <= s_axi_araddr;
    end else begin
      axi_arready <= 1'b0;
    end

    // Implement axi_rvalid generation
    if (axi_arready && s_axi_arvalid && ~axi_rvalid) begin
      // Valid read data is available at the read data bus
      axi_rvalid <= 1'b1;
      axi_rresp  <= 2'b0; // 'OKAY' response
    end else if (axi_rvalid && s_axi_rready) begin
      // Read data is accepted by the master
      axi_rvalid <= 1'b0;
    end

  end
end

endmodule
