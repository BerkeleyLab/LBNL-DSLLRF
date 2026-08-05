import logging
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles
from cocotbext.axi import AxiLiteBus, AxiLiteMaster
from cocotb.handle import Immediate


class TB:
    def __init__(self, dut):
        dut._log.setLevel(logging.WARNING)
        self.log = dut._log
        self.dut = dut
        self.n_regs_out = self._get_param('N_REGS_OUT')
        self.n_regs_inp = self._get_param('N_REGS_INP')
        self.addr_width = self._get_param('ADDR_WIDTH')
        self.reg_aw = self._get_param('REG_AW')
        dut._log.info(f"Found {self.n_regs_out} control registers and "
                      f"{self.n_regs_inp} status registers.")
        assert self.n_regs_out > 0, "N_REGS_OUT must be > 0"
        assert self.n_regs_inp > 0, "N_REGS_INP must be > 0"
        assert (self.addr_width >= (self.reg_aw + 2)), \
            (f"ADDR_WIDTH:{self.addr_width} must be "
             f"at least REG_AW:{self.reg_aw} + 2")
        cocotb.start_soon(Clock(dut.s_axi_aclk, 4, unit="ns").start())

        self.axil_master = AxiLiteMaster(
            AxiLiteBus.from_prefix(dut, "s_axi"),
            dut.s_axi_aclk, dut.s_axi_aresetn,
            reset_active_level=False)

    def _get_param(self, name):
        return int(getattr(self.dut, name).value)

    async def cycle_reset(self):
        self.dut.s_axi_aresetn.set(Immediate(1))
        await ClockCycles(self.dut.s_axi_aclk, 2)
        for v in [0, 1]:
            self.dut.s_axi_aresetn.value = v
            await RisingEdge(self.dut.s_axi_aclk)


@cocotb.test(timeout_time=1, timeout_unit='us')
async def test_write(dut):
    tb = TB(dut)
    await tb.cycle_reset()
    for i in range(tb.n_regs_out):
        addr = i * 4  # Control registers mapped at 0x00, 0x04, etc.
        data = 0xDEAD0000 | i  # Create test data unique per register.
        # Write data (convert integer to 4 little-endian bytes)
        await tb.axil_master.write(addr, data.to_bytes(4, byteorder="little"))
        # Read back the same register
        read_resp = await tb.axil_master.read(addr, 4)
        read_val = int.from_bytes(read_resp.data, byteorder="little")
        assert read_val == data, \
            f"Control reg {i}: expected 0x{data:08X}, got 0x{read_val:08X}"

    # Check that the flattened output bus 'csr_out' reflects the written values.
    # csr_out is 16 x 32-bit wide, with register 0 in bits [31:0],
    # register 1 in bits [63:32], etc.
    control_flat = int(dut.csr_out.value)
    for i in range(tb.n_regs_out):
        reg_val = (control_flat >> (i * 32)) & 0xFFFFFFFF
        expected = (0xDEAD0000 | i)
        assert reg_val == expected, \
            f"csr_out[{i}]: expected 0x{expected:08X}, got 0x{reg_val:08X}"


@cocotb.test(timeout_time=1, timeout_unit='us')
async def test_read(dut):
    tb = TB(dut)
    await tb.cycle_reset()
    # Prepare a list of 16 32-bit status values.
    status_vals = [0x100 + i for i in range(tb.n_regs_inp)]
    # Flatten into a single integer.
    # Bits [31:0] correspond to status register 0, [63:32] to register 1, etc.
    status_flat = 0
    for i, val in enumerate(status_vals):
        status_flat |= (val & 0xFFFFFFFF) << (i * 32)
    dut.csr_in.value = status_flat

    # Wait one clock cycle for the new status to propagate.
    await RisingEdge(dut.s_axi_aclk)
    # Status registers are mapped from N_REGS to 2*N_REGS.
    for i in range(tb.n_regs_inp):
        addr = (tb.n_regs_out + i) * 4
        read_resp = await tb.axil_master.read(addr, 4)
        read_val = int.from_bytes(read_resp.data, byteorder="little")
        expected = status_vals[i]
        assert read_val == expected, \
            f"Status reg {i}: expected 0x{expected:08X}, got 0x{read_val:08X}"
