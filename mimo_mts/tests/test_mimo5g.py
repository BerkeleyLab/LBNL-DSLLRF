"""
On-board check of the ZCU208 mimo_mts_5g overlay with the banked waveform generator and capture (doc/wave_gen.md).

1. Digital loopback, bit-exact: hier_dac_cap (axi_wave_cap) records the 160-bit stream that the broadcaster sends to
   the DACs; it must equal the waveform written to the generator (axil_wave_gen). Covers the 4-to-5 lane mapping, the
   2:1 width converter and the capture core at the real clocks. No cables needed.
2. ADC continuity (needs DAC-to-ADC loopback cables, skip with --no-adc): a CW tone is played and each ADC capture
   (I, real samples at 5 GSPS with the NCO at 0) is phase-demodulated in short blocks. After removing a linear fit
   the phase must stay within --max-phase-deg over the whole capture; a missing or duplicated 20-sample row would
   show as a jump of 360 * f * 4 ns (288 deg at 200 MHz; invisible if f is a multiple of 250 MHz, so avoid those).
   The old capture path (256 bits at 250 MHz for an 80 Gb/s stream) was expected to lose rows on long captures.
3. Writes during playback: the waveform is rewritten for a few seconds while it plays on a fast trigger; every write
   must return promptly, and check 1 must still pass afterwards.

    sudo -E python3 mimo_mts/tests/test_mimo5g.py [--no-adc] [--f-mhz 200]
"""

import argparse
import sys
import time
from typing import Any

import numpy as np

from mimo_mts.overlay import MimoMtsOverlay

DSP_CLK_HZ = 250e6  # axil_rf_control and the generator/capture clock in mimo_mts_5g


class Mimo5gCheck:
    def __init__(self, ol, f_hz, amplitude):
        self.ol = ol
        self.wg = ol.wave_gen
        self.rc = ol.rf_control.register_map
        self.fs = ol.adc_sampling_rate
        self.f_hz = f_hz
        self.amplitude = amplitude
        self.results = []

        self.rc.trig_sel = 0  # internal trigger
        self.rc.trig_delay = 0
        self.rc.trig_divide = 1
        self.rc.dac_enable = 1
        self.rc.pulse_length = 0xFFFF  # capture rows; axi_wave_cap clamps to its DEPTH (2048)
        self.wg.trigger_mode = 1  # start on the rf_control trigger, like the captures
        self.wg.wave_length = 0  # play the whole memory (BANK_DEPTH rows)
        self.set_period(0.1)

    def set_period(self, period_s):
        self.period_s = period_s
        self.rc.trig_period = int(period_s * DSP_CLK_HZ)

    def report(self, name, ok, detail=""):
        self.results.append((name, ok))
        print(f"[{'PASS' if ok else 'FAIL'}] {name}{': ' + detail if detail else ''}")

    def tone(self, phase0=0.0):
        """Complex CW tone over the whole generator memory (I/Q interleaved, complex rate fs/2)."""
        n = self.wg.wave_mem.size // 2
        t = np.arange(n) / (self.ol.dac_sampling_rate / 2)
        return self.amplitude * (2**15 - 1) * np.exp(1j * (2 * np.pi * self.f_hz * t + phase0))

    def write_tone(self, phase0=0.0):
        c = self.tone(phase0)
        iq = np.empty(2 * c.size, dtype=np.int16)
        iq[0::2] = np.round(c.real)
        iq[1::2] = np.round(c.imag)
        self.wg.wave_mem[:] = iq
        return iq

    def write_dc(self):
        """Constant I/Q for --nco mode: the DAC NCO makes the tone, so a stale or repeated beat changes nothing."""
        iq = np.zeros(self.wg.wave_mem.size, dtype=np.int16)
        iq[0::2] = int(self.amplitude * (2**15 - 1))
        self.wg.wave_mem[:] = iq
        return iq

    def write_random(self, seed):
        """Random int16 words: unlike a tone, every 20-word row is unique, so an offset error cannot hide."""
        iq = np.random.default_rng(seed).integers(-32768, 32767, size=self.wg.wave_mem.size, dtype=np.int16)
        self.wg.wave_mem[:] = iq
        return iq

    def wait_captures(self):
        time.sleep(3 * self.period_s + 0.05)

    def check_dac_capture(self, name, written):
        """The DAC capture must be a contiguous slice of the written stream (bit-exact)."""
        cap = np.array(self.ol.dac_capture)
        # locate the first 20 captured int16 words in the written stream (I/Q pairs, so even offsets; expected 0)
        head = cap[:20]
        offsets = [k for k in range(0, written.size - cap.size + 1, 2) if np.array_equal(written[k : k + 20], head)]
        if not offsets:
            self.report(name, False, "start of the capture not found in the written waveform")
            return False
        k = offsets[0]
        ok = np.array_equal(cap, written[k : k + cap.size])
        detail = f"{cap.size} int16 words from written offset {k} ({k // 20} rows)"
        if not ok:
            bad = np.flatnonzero(cap != written[k : k + cap.size])
            detail += f"; {bad.size} words differ, first at {bad[0]}"
        self.report(name, ok, detail)
        return ok

    def check_adc_continuity(self, max_phase_deg, block=200, label=""):
        i_buf, _ = self.ol.capture_adc_iq_buf()
        n = i_buf.shape[1]
        for ch in range(i_buf.shape[0]):
            x = i_buf[ch].astype(float)
            # skip the loopback latency: start where the tone is present
            env = np.abs(x)
            on = np.flatnonzero(env > 0.3 * env.max())
            if on.size == 0 or env.max() < 200:
                self.report(f"ADC{ch} continuity{label}", False, f"no tone (peak {env.max():.0f} LSB); cable?")
                continue
            x = x[on[0] + block :]
            # frequency from the FFT peak, refined by the demodulated phase slope
            spec = np.abs(np.fft.rfft(x * np.hanning(x.size)))
            f0 = np.argmax(spec) * self.fs / x.size
            idx = np.arange(x.size)
            z = x * np.exp(-2j * np.pi * f0 * idx / self.fs)
            nb = x.size // block
            zb = z[: nb * block].reshape(nb, block).mean(axis=1)
            ph = np.unwrap(np.angle(zb))
            fit = np.polyval(np.polyfit(np.arange(nb), ph, 1), np.arange(nb))
            resid = np.degrees(ph - fit)
            amp = np.abs(zb)
            ok = np.max(np.abs(resid)) < max_phase_deg and amp.min() > 0.8 * np.median(amp)
            # largest block-to-block phase step and where it is (ns from the start of the capture)
            dstep = np.diff(resid)
            j = int(np.argmax(np.abs(dstep)))
            t_step_ns = (on[0] + block + (j + 1) * block) / self.fs * 1e9
            detail = (
                f"{x.size} of {n} samples, f {f0 / 1e6:.2f} MHz, phase residual max {np.max(np.abs(resid)):.2f} deg "
                f"(rms {np.std(resid):.2f}), amplitude min/median {amp.min() / np.median(amp):.3f}, "
                f"largest step {dstep[j]:+.1f} deg at {t_step_ns:.0f} ns (tone from {on[0] / self.fs * 1e9:.0f} ns)"
            )
            self.report(f"ADC{ch} continuity{label}", ok, detail)

    def test_writes_during_playback(self, seconds=2.0, chunk=4096):
        self.set_period(20e-6)  # 16.4 us playback every 20 us
        worst = 0.0
        n_writes = 0
        t_end = time.perf_counter() + seconds
        iq = np.random.default_rng(7).integers(-32768, 32767, size=self.wg.wave_mem.size, dtype=np.int16)
        while time.perf_counter() < t_end:
            for start in range(0, iq.size, chunk):
                end = min(start + chunk, iq.size)
                t0 = time.perf_counter()
                self.wg.wave_mem[start:end] = iq[start:end]
                worst = max(worst, time.perf_counter() - t0)
                n_writes += 1
        self.set_period(0.1)
        print(f"  after the loop: wave_gen busy = {self.wg.busy}")
        detail = f"{n_writes} writes of up to {2 * chunk} B, slowest {worst * 1e6:.0f} us"
        self.report("writes during playback", worst < 20e-3, detail)
        self.wait_captures()
        self.check_dac_capture("DAC capture after writes during playback", iq)
        print(f"  wave_gen busy = {self.wg.busy}; writing a new random waveform")
        fresh = self.write_random(seed=11)
        self.wait_captures()
        self.check_dac_capture("DAC capture of a new waveform after the loop", fresh)


def poll_busy(wg, when, seconds=1.0):
    """Sample wave_gen busy as fast as possible: fraction of time busy and playback starts (0 -> 1) per second.
    Expected with a 0.1 s trigger and a 16.4 us playback: about 10 starts/s and busy ~0.02 % of the time."""
    n = busy_n = starts = 0
    prev = 0
    t_end = time.perf_counter() + seconds
    while time.perf_counter() < t_end:
        b = int(wg.register_map.status) & 1
        busy_n += b
        starts += int(b and not prev)
        prev = b
        n += 1
    print(f"  busy poll {when}: {n} samples, busy {100 * busy_n / n:.2f} %, {starts / seconds:.1f} playback starts/s")


def poll_stream(ol, when, seconds=1.0):
    """
    Needs a bitstream with the axil_wave_gen debug status (bit 1 tready, bit 2 tvalid, bits 16+ play_row) and the
    axi_wave_cap CSR. Prints how often tready/tvalid are high, how often the playing row jumps back (restarts) or
    stays put, and the capture counters one second apart (expected: one capture per trigger).
    """
    wg = ol.wave_gen
    n = rdy = vld = back = same = 0
    prev_row = None
    rows = set()
    try:
        counts0 = [c for *_, c in ol.capture_status()]
    except RuntimeError:
        counts0 = None
    t_end = time.perf_counter() + seconds
    while time.perf_counter() < t_end:
        st = int(wg.register_map.status)
        row = (st >> 16) & 0xFFFF
        rdy += (st >> 1) & 1
        vld += (st >> 2) & 1
        if prev_row is not None:
            back += int(row < prev_row)
            same += int(row == prev_row)
        rows.add(row)
        prev_row = row
        n += 1
    print(
        f"  stream poll {when}: {n} samples, tready {100 * rdy / n:.1f} %, tvalid {100 * vld / n:.1f} %, "
        f"row jumps back {back / seconds:.0f}/s, row unchanged {100 * same / max(n - 1, 1):.1f} %, "
        f"{len(rows)} distinct rows, last row {prev_row}"
    )
    if counts0 is not None:
        counts1 = [c for *_, c in ol.capture_status()]
        rates = sorted({(c1 - c0) % 65536 for c0, c1 in zip(counts0, counts1, strict=True)})
        print(f"  captures per {seconds:.0f} s (all axi_wave_cap): {rates}")


def print_dac_status(ol, when):
    """RFDC DAC block status (FIFO flags) and interrupt status, to see whether a DAC stopped taking data."""
    print(f"  RFDC DAC status {when}:")
    for t, tile in enumerate(ol.rfdc.dac_tiles):
        for b, blk in enumerate(tile.blocks):
            try:
                st = blk.BlockStatus
            except Exception:  # block not enabled
                continue
            line = f"    DAC tile {t} block {b}: " + ", ".join(
                f"{k}={st[k]}" for k in ("DataPathClocksStatus", "IsFIFOFlagsEnabled", "IsFIFOFlagsAsserted") if k in st
            )
            for name in ("IntrStatus", "GetIntrStatus"):
                attr = getattr(blk, name, None)
                if attr is not None:
                    try:
                        val: Any = attr() if callable(attr) else attr
                        line += f", {name}=0x{int(val):08x}"
                    except Exception as e:
                        line += f", {name}: {e}"
            print(line)


def main():
    parser = argparse.ArgumentParser(description="Check mimo_mts_5g: generator, banked captures, ADC continuity.")
    parser.add_argument("--config", default="MIMO5G_ZCU208", help="overlay configuration in mimo_mts.config")
    parser.add_argument("--f-mhz", type=float, default=200.0, help="CW tone frequency")
    parser.add_argument("--amplitude", type=float, default=0.5, help="tone amplitude, fraction of full scale")
    parser.add_argument("--max-phase-deg", type=float, default=5.0, help="ADC phase residual limit")
    parser.add_argument("--no-adc", action="store_true", help="skip the ADC check (no loopback cables)")
    parser.add_argument("--repeat", type=int, default=1, help="repeat the ADC capture check")
    parser.add_argument(
        "--nco", action="store_true", help="also check with constant I/Q and the DAC NCO making the tone"
    )
    args = parser.parse_args()

    ol = MimoMtsOverlay(config=args.config, download=True)
    assert hasattr(ol, "wave_gen") and ol.dac_capture is not None, "overlay lacks wave_gen or the DAC capture"
    print(
        f"wave_gen: {ol.wave_gen.out_data_width}-bit rows x {ol.wave_gen.bank_depth}; "
        f"captures: {ol.adc_bufs[0].size} int16 per stream, DAC capture {ol.dac_capture.size}"
    )

    chk = Mimo5gCheck(ol, args.f_mhz * 1e6, args.amplitude)
    print_dac_status(ol, "at start")
    poll_busy(chk.wg, "at start")
    poll_stream(ol, "at start")
    written = chk.write_random(seed=1)
    chk.wait_captures()
    chk.check_dac_capture("DAC capture equals the written waveform", written)
    if not args.no_adc:
        chk.write_tone()
        for r in range(args.repeat):
            chk.wait_captures()
            chk.check_adc_continuity(args.max_phase_deg, label=f" (tone from wave_gen, run {r + 1})")
        if args.nco:
            chk.write_dc()
            ol.set_dac_mixer(freq_mhz=args.f_mhz)
            for r in range(args.repeat):
                chk.wait_captures()
                chk.check_adc_continuity(args.max_phase_deg, label=f" (tone from DAC NCO, run {r + 1})")
            ol.set_dac_mixer(freq_mhz=0)
        print_dac_status(ol, "after the tone checks")
    chk.test_writes_during_playback()
    print_dac_status(ol, f"after the write loop (wave_gen busy = {chk.wg.busy})")
    poll_busy(chk.wg, "after the write loop")
    poll_stream(ol, "after the write loop")

    failed = [name for name, ok in chk.results if not ok]
    print(f"\n{len(chk.results) - len(failed)}/{len(chk.results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
