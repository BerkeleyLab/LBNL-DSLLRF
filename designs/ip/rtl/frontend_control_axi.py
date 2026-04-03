"""
Attach multiple SPI controllers to an exposed AXI bus.
To be used in the Vivado IP integrator to control the RFSOC frontend.
"""
from sys import argv
from litex.gen import Record, run_simulation
from litex.soc.interconnect.csr import CSRField, CSRStatus, CSRStorage
from litex_obsidian.axi_ip_template.axi_ip_template import AxiIpSoc
from litex.soc.cores.spi.spi_mmap import SPIMaster


class SpiCsr(SPIMaster):
    def __init__(self, pads, sys_clk_freq, data_width=32):
        """Hook up the LiteX soc.cores.spi.spi_mmap.SPIMaster to registers.
        We can't use soc.cores.spi.spi_master here because we need to switch CPOL at runtime"""
        SPIMaster.__init__(self, pads, data_width, sys_clk_freq)
        self.control = CSRStorage(
            fields=[
                CSRField("cs", size=1, offset=0, description="Inverted value of the CS_N pin"),
                CSRField("loopback", size=1, offset=3, description="Enable loopback mode"),
                CSRField("mode", size=2, offset=4, description="SPI mode, bit 1 is CPOL, bit 0 is CPHA"),
                CSRField("length", size=8, offset=8, description="Number of bits to transfer"),
                CSRField("clk_divider", size=16, offset=16, reset=2, description="Clock divider, min: 2, even!"),
            ]
        )
        self.status = CSRStatus(description="1 when the transfer is finished")
        self.sdo = CSRStorage(data_width, description="Write to start transfer")
        self.sdi = CSRStatus(data_width, description="Contains received word after a transfer")
        self.comb += [
            self.loopback.eq(self.control.fields.loopback),
            self.clk_divider.eq(self.control.fields.clk_divider),
            self.mode.eq(self.control.fields.mode),
            self.length.eq(self.control.fields.length),
            self.start.eq(self.sdo.re),
            self.status.status.eq(self.done),
            self.mosi.eq(self.sdo.storage),
            self.sdi.status.eq(self.miso),
            self.cs.eq(self.control.fields.cs),
        ]


class FrontendControlAxi(AxiIpSoc):
    def __init__(self, N=8):
        """Hook up N SpiCsrs to a common AXI bus"""
        AxiIpSoc.__init__(self, 100e6, csr_paging=0x400)
        for i in range(N):
            name = f"spi{i}"
            pads = Record([("clk", 1), ("cs_n", 1), ("mosi", 1), ("miso", 1)], name=name)
            spi = SpiCsr(pads, sys_clk_freq=self.sys_clk_freq)
            setattr(self, name, spi)
            self.all_ios.update(pads.flatten())


# -----------------------------------------------
#  Testbench / .vcd demo
# -----------------------------------------------
def do_tx(dut: SpiCsr, val, div=2, mode=0, length=8, loopback=False):
    """Do one SPI transfer. Use as inspiration for the firmware / driver code"""
    yield from dut.control.write((div << 16) | (length << 8) | (mode << 4) | (loopback << 3) | 0b1)
    yield from dut.sdo.write(val << (32 - length))  # Need to left-align
    while (yield from dut.status.read()) == 0:
        pass
    yield from dut.control.write((div << 16) | (length << 8) | (mode << 4) | (loopback << 3) | 0b0)
    return (yield from dut.sdi.read())


def dut_gen(dut: SpiCsr):
    # Demo the 4 SPI modes. Manually check the timing of the waveform in the .vcd file.
    for mode in range(4):
        for _ in range(16):
            yield
        rx = yield from do_tx(dut, 0x13, 4, mode=mode)
        assert rx == 0
        for _ in range(16):
            yield

    # Loopback test
    for mode in range(2):
        rx = yield from do_tx(dut, 0x12345678, 4, mode, 32, True)
        print(f"Mode: {mode}, RX: 0x{rx:08x}")
        assert rx == 0x12345678


# -----------------------------------------------
#  Command line interface
# -----------------------------------------------
if __name__ == "__main__":
    # Instantiate AXI SoC
    soc = FrontendControlAxi()

    if "sim" in argv:
        # Simulate only 1 of the 8 SpiCsr modules
        tb = dut_gen(soc.spi0)
        run_simulation(soc.spi0, tb, vcd_name=soc.out_name + ".vcd")
        print("wrote", soc.out_name + ".vcd")
    else:
        soc.generate_verilog()
