
`timescale 1 ns / 1 ps

	module pulser_axis_v1_0 #
	(
		// Users to add parameters here
   parameter CW = 8,             // Pulse counter width
   parameter integer STREAM_SAMPLES = 1, // Stream data width = 16*STREAM_SAMPLES
   parameter MODULATED = "false", // Set to "true" to enable DDS and CORDIC modulation
   parameter MODE_IQ = "false", // Only valid for MODULATED == "true"

		// User parameters ends
		// Do not modify the parameters beyond this line


		// Parameters of Axi Slave Bus Interface S_AXI
		parameter integer C_S_AXI_DATA_WIDTH	= 32,
		parameter integer C_S_AXI_ADDR_WIDTH	= 8
	)
	(
		// Users to add ports here
  input DAC_stream_clk,
  input evr_trig,  // EVR/Hardware Trigger
  output sw_trig_out,
  output trig_out_stream_clk,
  // AXI Stream Output
  input DAC_stream_tready,
  output [16*STREAM_SAMPLES-1:0] DAC_stream_tdata,
  output DAC_stream_tvalid,
  output pulse_en,
  // Debug outputs for ILA
  output [13:0] debug_tdata,
  output debug_tvalid,
  output debug_tready,

		// User ports ends
		// Do not modify the ports beyond this line


		// Ports of Axi Slave Bus Interface S_AXI
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
// Instantiation of Axi Bus Interface S_AXI
	pulser_axis_v1_0_S_AXI # ( 
		.CW(CW),
		.STREAM_SAMPLES(STREAM_SAMPLES),
		.MODULATED(MODULATED),
		.MODE_IQ(MODE_IQ),
		.C_S_AXI_DATA_WIDTH(C_S_AXI_DATA_WIDTH),
		.C_S_AXI_ADDR_WIDTH(C_S_AXI_ADDR_WIDTH)
	) pulser_axis_v1_0_S_AXI_inst (
		.DAC_stream_clk(DAC_stream_clk),
		.evr_trig(evr_trig),
		.sw_trig_out(sw_trig_out),
		.trig_out_stream_clk(trig_out_stream_clk),
		.DAC_stream_tready(DAC_stream_tready),
		.DAC_stream_tdata(DAC_stream_tdata),
		.DAC_stream_tvalid(DAC_stream_tvalid),
		.pulse_en(pulse_en),
		.debug_tdata(debug_tdata),
		.debug_tvalid(debug_tvalid),
		.debug_tready(debug_tready),
		.S_AXI_ACLK(s_axi_aclk),
		.S_AXI_ARESETN(s_axi_aresetn),
		.S_AXI_AWADDR(s_axi_awaddr),
		.S_AXI_AWPROT(s_axi_awprot),
		.S_AXI_AWVALID(s_axi_awvalid),
		.S_AXI_AWREADY(s_axi_awready),
		.S_AXI_WDATA(s_axi_wdata),
		.S_AXI_WSTRB(s_axi_wstrb),
		.S_AXI_WVALID(s_axi_wvalid),
		.S_AXI_WREADY(s_axi_wready),
		.S_AXI_BRESP(s_axi_bresp),
		.S_AXI_BVALID(s_axi_bvalid),
		.S_AXI_BREADY(s_axi_bready),
		.S_AXI_ARADDR(s_axi_araddr),
		.S_AXI_ARPROT(s_axi_arprot),
		.S_AXI_ARVALID(s_axi_arvalid),
		.S_AXI_ARREADY(s_axi_arready),
		.S_AXI_RDATA(s_axi_rdata),
		.S_AXI_RRESP(s_axi_rresp),
		.S_AXI_RVALID(s_axi_rvalid),
		.S_AXI_RREADY(s_axi_rready)
	);

	// Add user logic here
	// User logic ends

	endmodule
