import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles
import random
import logging
import numpy as np


class TB:
    def __init__(self, dut):
        dut._log.setLevel(logging.INFO)
        self.dut = dut
        self.SAMP_DW = dut.SAMP_DW.value
        self.SAMP_NUM = dut.SAMP_NUM.value
        self.dut.data_in_valid.setimmediatevalue(0)
        cocotb.start_soon(Clock(dut.clk, 4, units="ns").start())

    def to_signed(self, darray):
        # decode 2's complement representation to signed integer
        mask = 2**(self.SAMP_DW - 1)
        return -np.bitwise_and(darray, mask) + np.bitwise_and(darray, ~mask)

    def encode_2s_comp(self, val):
        # encode signed integer to 2's complement representation
        return int(np.binary_repr(val, width=self.SAMP_DW), 2)

    async def reset(self):
        self.dut.reset.setimmediatevalue(0)
        await ClockCycles(self.dut.clk, 2)
        for val in [1, 0]:
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

        data_out = dut.data_out.value.integer
        delta = (data_in - prev_data) // tb.SAMP_NUM

        interp_values = [
            v.signed_integer for v in dut.interp_array.value]
        tb.dut._log.info(
            f"Data pre: {prev_data:8d}, Data in: {data_in:8d}")
        tb.dut._log.info(
            f"Data out: {interp_values}")
        assert prev_data == dut.prev_data.value.signed_integer, \
            f"Expected {prev_data}, got {dut.prev_data.value.signed_integer}"
        assert data_in == dut.data_in.value.signed_integer, \
            f"Expected {data_in}, got {dut.data_in.value.signed_integer}"
        assert delta == dut.delta.value.signed_integer, \
            f"Expected {delta}, got {dut.delta.value.signed_integer}"

        # Check the expected value
        for j in range(tb.dut.SAMP_NUM.value):
            expected_value = prev_data + j * delta
            actual_value = (data_out >> (j * tb.SAMP_DW)) & 0xFFFF
            # actual_value = uint16_to_int16(actual_value)
            actual_value = tb.to_signed(actual_value)
            assert expected_value == actual_value, \
                f"Expected {expected_value}, got {actual_value}"
        prev_data = data_in
