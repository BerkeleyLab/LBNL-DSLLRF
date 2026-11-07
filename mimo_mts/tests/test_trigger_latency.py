"""
On-board check of the internal trigger after an overlay load (MR !44).

Loads an overlay, sets the internal trigger to `--period_ms`, and times the capture-done interrupts:
the first one must come within about one period of the register writes, and later ones one period
apart. Before the axil_rf_control fix the first trigger came only after the 32-bit counter wrapped:
2**32 clock cycles after the bitstream load, ~43 s at 100 MHz (base overlay, rf_control on pl_clk0)
or ~17 s at 250 MHz (dsp_clk).

    python3 mimo_mts/tests/test_trigger_latency.py --config BASE_ZCU208 --clk_mhz 100
"""

import argparse
import asyncio
import sys
import time

from mimo_mts.overlay import MimoMtsOverlay


async def irq_times(irq, n, timeout_s):
    """perf_counter() times of the next n interrupts; stops early on timeout."""
    times = []
    for _ in range(n):
        try:
            await asyncio.wait_for(irq.wait(), timeout_s)
        except asyncio.TimeoutError:
            break
        times.append(time.perf_counter())
    return times


def main():
    parser = argparse.ArgumentParser(description="Time the internal trigger after an overlay load.")
    parser.add_argument("--config", default="BASE_ZCU208", help="overlay configuration in mimo_mts.config")
    parser.add_argument("--clk_mhz", type=float, default=100, help="axil_rf_control clock (base: 100, ALS: 250)")
    parser.add_argument("--period_ms", type=float, default=100, help="internal trigger period")
    parser.add_argument("-n", type=int, default=5, help="number of triggers to time")
    parser.add_argument("--timeout_s", type=float, default=60, help="give up waiting for the first trigger")
    args = parser.parse_args()

    period_s = args.period_ms / 1e3
    t0 = time.perf_counter()
    ol = MimoMtsOverlay(config=args.config, download=True)
    t_loaded = time.perf_counter()
    assert hasattr(ol, "write_done_irq"), f"{args.config}: no capture-done interrupt found"

    rm = ol.rf_control.register_map
    rm.trig_delay = 0
    rm.trig_divide = 1
    rm.pulse_length = 0xFFF
    rm.trig_period = round(period_s * args.clk_mhz * 1e6)
    rm.trig_sel = 0  # internal trigger
    t_set = time.perf_counter()
    print(f"overlay load {t_loaded - t0:.2f} s; trigger set {t_set - t_loaded:.3f} s later")
    print(f"trig_period = {int(rm.trig_period)} cycles at {args.clk_mhz} MHz = {args.period_ms} ms")

    # PYNQ registers the interrupt's UIO file with asyncio.get_event_loop() when the overlay loads,
    # so wait on that default loop; asyncio.run() would create a new loop that never sees the IRQ.
    loop = asyncio.get_event_loop()
    times = loop.run_until_complete(irq_times(ol.write_done_irq, args.n, max(args.timeout_s, 3 * period_s)))
    if not times:
        wrap_s = 2**32 / (args.clk_mhz * 1e6)
        print(f"FAIL: no trigger within {args.timeout_s:.0f} s (old RTL: first trigger ~{wrap_s:.0f} s after load)")
        return 1

    first = times[0] - t_set
    intervals = [b - a for a, b in zip(times, times[1:], strict=False)]
    print(f"first trigger {first * 1e3:.1f} ms after setting the period ({(times[0] - t_loaded):.2f} s after load)")
    print("intervals [ms]:", ", ".join(f"{dt * 1e3:.1f}" for dt in intervals))

    # Generous margins for Linux interrupt latency in Python
    ok_first = first <= period_s * 1.5 + 0.05
    ok_count = len(times) == args.n
    ok_intervals = all(abs(dt - period_s) <= 0.2 * period_s + 0.01 for dt in intervals)
    ok = ok_first and ok_count and ok_intervals
    print("PASS" if ok else f"FAIL: first={ok_first} count={ok_count} intervals={ok_intervals}")
    ol.free()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
