import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from cocotb.handle import Immediate
import random
import logging


class TB:
    def __init__(self, dut):
        dut._log.setLevel(logging.INFO)
        self.dut = dut
        self.SAMP_DW = dut.SAMP_DW.value.to_unsigned()
        self.SAMP_NUM = dut.SAMP_NUM.value.to_unsigned()
        self.dut.data_in_valid.set(Immediate(0))
        cocotb.start_soon(Clock(dut.clk, 4, unit="ns").start())

    async def reset(self):
        for val in [0, 1, 0]:
            self.dut.reset.value = val
            await RisingEdge(self.dut.clk)

    async def send_data(self):
        data_in = random.randint(-2**15, 2**15-1)
        self.dut.data_in.value = data_in
        self.dut.data_in_valid.value = 1
        await RisingEdge(self.dut.clk)
        return data_in


@cocotb.test(timeout_time=1, timeout_unit='us')
async def test(dut, length=1):
    tb = TB(dut)
    await tb.reset()

    prev_data = 0
    for i in range(10):
        data_in = await tb.send_data()
        # Wait for the interpolated data to be valid
        if not dut.data_out_valid.value:
            prev_data = data_in
            continue

        delta = (data_in - prev_data) // tb.SAMP_NUM

        interp_values = [
            v.to_signed() for v in dut.interp_array.value]
        tb.dut._log.info(
            f"Data pre: {prev_data:8d}, Data in: {data_in:8d}")
        tb.dut._log.info(
            f"Data out: {interp_values}")
        assert prev_data == dut.prev_data.value.to_signed(), \
            f"Expected {prev_data}, got {dut.prev_data.value.to_signed()}"
        assert data_in == dut.data_in.value.to_signed(), \
            f"Expected {data_in}, got {dut.data_in.value.to_signed()}"
        assert delta == dut.delta.value.to_signed(), \
            f"Expected {delta}, got {dut.delta.value.to_signed()}"

        data_out = dut.data_out.value
        dw = tb.SAMP_DW
        for j in range(tb.SAMP_NUM):
            expected_value = prev_data + j * delta
            actual_value = data_out[(j+1)*dw-1:j*dw].to_signed()
            assert expected_value == actual_value, \
                f"Expected {expected_value}, got {actual_value}"
        prev_data = data_in
