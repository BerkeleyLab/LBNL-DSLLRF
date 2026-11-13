"""
Expose the AXI interface of the ui_board_hard core, so it can be used in the Vivado IP integrator
"""

from litex_obsidian.axi_ip_template.axi_ip_template import AxiIpSoc
from litex_obsidian.peripherals.ui_board_hard import UiBoardHard


class UiBoardHardAxi(AxiIpSoc):
    def __init__(self):
        AxiIpSoc.__init__(self, 100e6, csr_paging=0x2000)
        self.ui = UiBoardHard(sys_clk_freq=self.sys_clk_freq, spi_clk_freq=5e6, legacy=True)
        self.all_ios.update(self.ui.pads.flatten())


if __name__ == "__main__":
    # Instantiate LiteX SoC
    soc = UiBoardHardAxi()
    soc.generate_verilog()
