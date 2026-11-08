"""
On-board check of the axil_wave_gen waveform generator in the ZCU208 base overlay (doc/wave_gen.md).

In the base overlay the generator output goes straight into adc_capture, and both start on the axil_rf_control
trigger, so the capture buffer must hold the written waveform bit-exactly (offset by the generator latency). Checks:

1. bulk write through ``WaveGen.wave_mem`` (numpy copy), played back and captured;
2. 16-bit and 32-bit stores in random order (partial WSTRB, any order, no flush);
3. writes while the generator plays on a fast trigger: every write returns promptly (no CPU stall);
4. write throughput.

adc_capture always accepts data (tready = 1), so the "stalled stream" case of the testbench cannot be reproduced
here; it needs the DAC path of mimo_mts_5g.

    sudo -E python3 mimo_mts/tests/test_wave_gen.py --config BASE_ZCU208
"""

import argparse
import sys
import time

import numpy as np

from mimo_mts.overlay import MimoMtsOverlay

MARKER = 0x5A5A


class WaveGenCheck:
    def __init__(self, ol, rows, clk_mhz):
        self.ol = ol
        self.wg = ol.wave_gen
        self.rc = ol.rf_control.register_map
        self.cap = ol._memdict_to_view("hier_llrf/axi_bram_ctrl_0", dtype="int16")
        self.spw = self.wg.samples_per_word
        self.rows = rows
        self.clk_hz = clk_mhz * 1e6
        self.results = []

        self.wg.trigger_mode = 1  # start on the rf_control trigger, like adc_capture
        self.wg.wave_length = rows
        self.rc.trig_sel = 0  # internal trigger
        self.rc.trig_delay = 0
        self.rc.trig_divide = 1
        self.rc.pulse_length = rows + 32  # capture rows, with room for the generator latency
        self.set_period(10e-3)

    def set_period(self, period_s):
        self.period_s = period_s
        self.rc.trig_period = int(period_s * self.clk_hz)

    def report(self, name, ok, detail=""):
        self.results.append((name, ok))
        print(f"[{'PASS' if ok else 'FAIL'}] {name}{': ' + detail if detail else ''}")

    def capture(self):
        """Fill the capture buffer with a marker, wait for the next triggers, return it as (rows, spw)."""
        n = (self.rows + 32) * self.spw
        self.cap[:n] = MARKER
        time.sleep(3 * self.period_s + 0.01)
        return np.array(self.cap[:n]).reshape(-1, self.spw)

    def check_playback(self, name, expected):
        """Compare the capture with the expected (rows, spw) waveform; the start is found from the marker rows."""
        cap = self.capture()
        written = np.flatnonzero(~np.all(cap == MARKER, axis=1))
        if written.size == 0:
            self.report(name, False, "nothing captured (trigger running?)")
            return False
        k = int(written[0])
        got = cap[k : k + self.rows]
        ok = got.shape == expected.shape and np.array_equal(got, expected)
        detail = f"{self.rows} rows from capture row {k}"
        if not ok and got.shape == expected.shape:
            bad = np.flatnonzero(np.any(got != expected, axis=1))
            detail += f"; {bad.size} rows differ, first at row {bad[0]}"
        self.report(name, ok, detail)
        return ok

    def random_waveform(self, seed):
        rng = np.random.default_rng(seed)
        return rng.integers(-32768, 32767, size=(self.rows, self.spw), dtype=np.int16)

    def test_bulk(self):
        wave = self.random_waveform(1)
        self.wg.wave_mem[: wave.size] = wave.ravel()
        self.check_playback("bulk numpy write", wave)

    def test_shuffled_stores(self):
        rng = np.random.default_rng(2)
        wave = self.random_waveform(3)
        flat = wave.ravel()
        mem16 = self.wg.wave_mem
        for i in rng.permutation(flat.size):
            mem16[i] = flat[i]
        self.check_playback("16-bit stores, random order", wave)

        wave = self.random_waveform(4)
        flat32 = wave.ravel().view(np.uint32)
        mem32 = self.wg.wave_mem[: wave.size].view(np.uint32)
        for i in rng.permutation(flat32.size):
            mem32[i] = flat32[i]
        self.check_playback("32-bit stores, random order", wave)

    def test_write_during_playback(self, seconds=2.0):
        """Rewrite the waveform continuously while it plays every 10 us; record the slowest write."""
        self.set_period(10e-6)
        wave = self.random_waveform(5)
        flat = wave.ravel()
        chunk = 256  # samples per timed write
        worst = 0.0
        n_writes = 0
        t_end = time.perf_counter() + seconds
        while time.perf_counter() < t_end:
            for start in range(0, flat.size, chunk):
                t0 = time.perf_counter()
                end = min(start + chunk, flat.size)  # the last chunk may be short
                self.wg.wave_mem[start:end] = flat[start:end]
                worst = max(worst, time.perf_counter() - t0)
                n_writes += 1
        self.set_period(10e-3)
        detail = f"{n_writes} writes of up to {2 * chunk} B, slowest {worst * 1e6:.0f} us"
        self.report("writes during playback", worst < 5e-3, detail)
        self.check_playback("waveform after writes during playback", wave)

    def test_throughput(self):
        n = self.wg.wave_mem.size
        data = np.arange(n, dtype=np.int16)
        t0 = time.perf_counter()
        self.wg.wave_mem[:] = data
        dt = time.perf_counter() - t0
        self.report("full-memory write", True, f"{2 * n} B in {dt * 1e3:.1f} ms, {2 * n / dt / 1e6:.1f} MB/s")


def main():
    parser = argparse.ArgumentParser(description="Check axil_wave_gen through the base overlay's capture loopback.")
    parser.add_argument("--config", default="BASE_ZCU208", help="overlay configuration in mimo_mts.config")
    parser.add_argument("--clk_mhz", type=float, default=100, help="clock of axil_rf_control and the generator")
    parser.add_argument("--rows", type=int, default=200, help="waveform length in output words (capture: 1024 rows)")
    args = parser.parse_args()

    ol = MimoMtsOverlay(config=args.config, download=True)
    assert hasattr(ol, "wave_gen"), "overlay has no axil_wave_gen"
    print(f"wave_gen: OUT_DATA_WIDTH {ol.wave_gen.out_data_width}, BANK_DEPTH {ol.wave_gen.bank_depth}")

    chk = WaveGenCheck(ol, args.rows, args.clk_mhz)
    chk.test_bulk()
    chk.test_shuffled_stores()
    chk.test_write_during_playback()
    chk.test_throughput()

    failed = [name for name, ok in chk.results if not ok]
    print(f"\n{len(chk.results) - len(failed)}/{len(chk.results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
