"""
On-board check of the ZCU208 mimo_mts_5g overlay with the banked waveform generator and capture (doc/wave_gen.md).

1. Digital loopback, bit-exact (only in builds with hier_dac_cap, which the per-DAC build removed): the DAC copy
   capture must equal the waveform written to the generator (axil_wave_gen). Covers the 4-to-5 lane mapping, the 2:1
   width converter and the capture core at the real clocks. No cables needed.
2. ADC continuity (needs DAC-to-ADC loopback cables, skip with --no-adc): a CW tone is played and each ADC capture
   (I, real samples at 5 GSPS with the NCO at 0) is phase-demodulated in short blocks. After removing a linear fit
   the phase must stay within --max-phase-deg over the whole capture; a missing or duplicated 20-sample row would
   show as a jump of 360 * f * 4 ns (288 deg at 200 MHz; invisible if f is a multiple of 250 MHz, so avoid those).
3. With one generator per DAC (register map v2): each DAC's own tone on its ADC; CW mode with per-DAC phase steps
   and amplitude, applied at once; loop mode over a waveform shorter than the capture, continuous across the wraps.
4. Writes during playback: the waveform is rewritten for a few seconds while it plays on a fast trigger; every write
   must return promptly, and check 1 must still pass afterwards.

    sudo -E python3 mimo_mts/tests/test_mimo5g.py [--no-adc] [--f-mhz 200] [--nco]

LBL208 (analog front end with 3 GHz filters, one loopback path): RF mode with the cabled pair and the attenuators of
its path, e.g.
    sudo -E python3 mimo_mts/tests/test_mimo5g.py --config MIMO_5G_LBL208 --rf-mhz 3000 --pairs 6:7 \\
        --atten 4:0=20,4:1=2 --nco
"""

import argparse
import sys
import time
from typing import Any

import numpy as np

from mimo_mts.overlay import MimoMtsOverlay
from mimo_mts.utils.rfdc_freq import rf_to_nco

DSP_CLK_HZ = 250e6  # axil_rf_control and the generator/capture clock in mimo_mts_5g


class Mimo5gCheck:
    def __init__(self, ol, f_hz, amplitude, rf_hz=None, pairs=None, band_hz=100e6):
        """
        f_hz: test tone frequency (direct mode: the DAC output frequency; RF mode: offset from rf_hz at baseband).
        rf_hz: RF mode (e.g. the LBL208 front end with its 3 GHz filters): DAC and ADC NCOs at rf_hz, captures analysed
            as complex I/Q within +-band_hz of it. None: direct mode (DAC n -> ADC n cables, real samples, NCOs at 0).
        pairs: [(dac, adc), ...] cabled loopback paths; default DAC n -> ADC n for all channels.
        """
        self.ol = ol
        self.wg = ol.wave_gen
        self.gens = getattr(ol, "wave_gens", [ol.wave_gen])
        self.rc = ol.rf_control.register_map
        self.fs = ol.adc_sampling_rate
        self.f_hz = f_hz
        self.amplitude = amplitude
        self.rf_hz = rf_hz
        self.band_hz = band_hz
        n = min(len(getattr(ol, "wave_gens", [ol.wave_gen])), ol.board.n_adcs)
        self.pairs = pairs if pairs is not None else [(k, k) for k in range(n)]
        self.results = []
        if rf_hz is not None:
            self.set_rf("adc", rf_hz)
            self.set_rf("dac", rf_hz)

        self.rc.trig_sel = 0  # internal trigger
        self.rc.trig_delay = 0
        self.rc.trig_divide = 1
        self.rc.dac_enable = 1
        self.rc.pulse_length = 0xFFFF  # capture rows; axi_wave_cap clamps to its DEPTH (2048)
        for wg in self.gens:
            wg.trigger_mode = 1  # start on the rf_control trigger, like the captures
            wg.wave_length = 0  # play the whole memory (BANK_DEPTH rows)
        self.set_period(0.1)

    def set_rf(self, conv, rf_hz):
        """Set all DAC or ADC mixers to an RF frequency (NCO frequency and Nyquist zone from rfdc_freq)."""
        fs = self.ol.dac_sampling_rate if conv == "dac" else self.ol.adc_sampling_rate
        nco, zone = rf_to_nco(rf_hz / 1e6, fs / 1e6, conv)
        getattr(self.ol, f"set_{conv}_mixer")(freq_mhz=nco, nyquist=zone)

    def dac_offset(self, offset_hz):
        """DAC mixers at the test frequency for a constant-I/Q (NCO) tone: offset_hz (direct) or rf_hz + offset_hz."""
        if self.rf_hz is None:
            self.ol.set_dac_mixer(freq_mhz=offset_hz / 1e6)
        else:
            self.set_rf("dac", self.rf_hz + offset_hz)

    def signal(self, i_buf, q_buf, adc):
        """ADC samples to analyse: I (real, direct mode) or I + jQ (complex baseband, RF mode)."""
        if self.rf_hz is None:
            return i_buf[adc].astype(float)
        return i_buf[adc].astype(float) + 1j * q_buf[adc].astype(float)

    def capture_signals(self):
        i_buf, q_buf = self.capture()
        return {adc: self.signal(i_buf, q_buf, adc) for _, adc in self.pairs}

    def path_name(self, dac, adc):
        return f"ADC{adc}" if dac == adc else f"DAC{dac} -> ADC{adc}"

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
        self._write_all(iq)
        return iq

    def write_dc(self):
        """Constant I/Q for --nco mode: the DAC NCO makes the tone, so a stale or repeated beat changes nothing."""
        iq = np.zeros(self.wg.wave_mem.size, dtype=np.int16)
        iq[0::2] = int(self.amplitude * (2**15 - 1))
        self._write_all(iq)
        return iq

    def write_random(self, seed):
        """Random int16 words: unlike a tone, every 20-word row is unique, so an offset error cannot hide."""
        iq = np.random.default_rng(seed).integers(-32768, 32767, size=self.wg.wave_mem.size, dtype=np.int16)
        self._write_all(iq)
        return iq

    def _write_all(self, iq):
        for wg in self.gens:
            wg.wave_mem[:] = iq

    def wait_captures(self):
        time.sleep(3 * self.period_s + 0.05)

    def capture(self):
        """
        ADC I/Q of one capture. With the capture CSRs (one-shot mode) the captures are armed, waited for and held while
        they are read, so the next trigger cannot overwrite a buffer half read (a torn read shows as a phase step when
        the tone phase differs between triggers, e.g. a free-running loop). Free-running mode is restored afterwards.
        """
        if getattr(self.ol, "_capture_csrs", None):
            self.ol.capture_oneshot = True
            self.ol.arm_captures()
            done = self.ol.wait_captures(timeout_s=10 * self.period_s + 0.5)
            bufs = self.ol.capture_adc_iq_buf()
            self.ol.capture_oneshot = False
            if not done:
                raise RuntimeError("captures not done after arming (no trigger?)")
            return bufs
        return self.ol.capture_adc_iq_buf()

    def check_dac_capture(self, name, written):
        """The DAC capture must be a contiguous slice of the written stream (bit-exact)."""
        if self.ol.dac_capture is None:
            print(f"  (skipped: {name}; no DAC copy capture in this overlay)")
            return True
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
        sigs = self.capture_signals()
        for dac, ch in self.pairs:
            x = sigs[ch]
            n = x.size
            name = self.path_name(dac, ch)
            # skip the loopback latency: start where the tone is present
            env = np.abs(x)
            on = np.flatnonzero(env > 0.3 * env.max())
            if on.size == 0 or env.max() < 200:
                self.report(f"{name} continuity{label}", False, f"no tone (peak {env.max():.0f} LSB); cable?")
                continue
            x = x[on[0] + block :]
            # frequency from the FFT peak, refined by the demodulated phase slope
            f0 = tone_freq(x, self.fs, self.band_hz)
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
            self.report(f"{name} continuity{label}", ok, detail)

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


def tone_freq(x, fs, band_hz=100e6):
    """Frequency of the strongest tone: real x (direct mode) above DC, or complex x within +-band_hz, away from DC."""
    if np.iscomplexobj(x):
        spec = np.abs(np.fft.fft(x * np.hanning(x.size)))
        f = np.fft.fftfreq(x.size, 1 / fs)
        spec[(np.abs(f) > band_hz) | (np.abs(f) < 0.5e6)] = 0  # the R2C sum-frequency image and the ADC offset
        return f[int(np.argmax(spec))]
    spec = np.abs(np.fft.rfft(x * np.hanning(x.size)))
    spec[:10] = 0
    return np.argmax(spec) * fs / x.size


def adc_tone(x, fs, f_hint=None, band_hz=100e6):
    """(frequency, complex amplitude) of the strongest tone of a capture (or at f_hint); x real or complex."""
    if f_hint is None:
        f_hint = tone_freq(x, fs, band_hz)
    n = np.arange(x.size)
    scale = 1 if np.iscomplexobj(x) else 2
    return f_hint, scale * np.mean(x * np.exp(-2j * np.pi * f_hint * n / fs))


def check_per_dac_tones(chk, f0_mhz=100.0, step_mhz=25.0):
    """
    Each DAC plays its own tone (f0 + n*step; RF mode: offsets from the RF frequency); the ADC of every cabled pair
    must see its DAC's frequency (an inverted spectrum in RF mode shows it at minus that offset, also accepted).
    """
    ol, gens = chk.ol, chk.gens
    n = gens[0].wave_mem.size // 2
    t = np.arange(n) / (ol.dac_sampling_rate / 2)
    for ch in range(len(gens)):
        c = chk.amplitude * 32767 * np.exp(2j * np.pi * (f0_mhz + step_mhz * ch) * 1e6 * t)
        ol.write_dac_iq_buf_ch(ch, c.real, c.imag)
    chk.wait_captures()
    sigs = chk.capture_signals()
    for dac, adc in chk.pairs:
        f, a = adc_tone(sigs[adc][2000:], chk.fs, band_hz=chk.band_hz)
        want = (f0_mhz + step_mhz * dac) * 1e6
        ok = abs(abs(f) - want) < 1e6 and abs(a) > 500
        chk.report(
            f"DAC{dac} -> ADC{adc} own waveform",
            ok,
            f"{f / 1e6:.2f} MHz (expected {'+-' if chk.rf_hz else ''}{want / 1e6:.0f}), |a| {abs(a):.0f}",
        )


def check_cw(chk, f_mhz=200.0, step_deg=30.0, tol_deg=1.0):
    """
    CW mode: all DACs CW from the NCO (direct: at f_mhz; RF mode: f_mhz off the RF frequency). Applying per-DAC phase
    steps n*step_deg at once must move the phase of DAC n's ADC by n*step_deg (RF mode: by -n*step_deg if the
    frequency plan inverts the spectrum, which the check detects); halving the amplitude must halve the ADC amplitude.
    """
    ol, gens = chk.ol, chk.gens
    chk.dac_offset(f_mhz * 1e6)
    hint = f_mhz * 1e6 if chk.rf_hz is None else None

    def setup(amp, phases):
        for ch, wg in enumerate(gens):
            wg.mode = 2
            wg.set_cw_amp_phase(amp, phases[ch])
        ol.apply_dac_settings()
        chk.wait_captures()
        sigs = chk.capture_signals()
        return {adc: adc_tone(sigs[adc][2000:], chk.fs, hint, chk.band_hz)[1] for _, adc in chk.pairs}

    def wrap(x):
        return (x + 180) % 360 - 180

    base = setup(0.5, [0.0] * len(gens))
    modes = [wg.active_mode for wg in gens]
    chk.report("CW mode active on all DACs", all(m == 2 for m in modes), f"active modes {modes}")
    stepped = setup(0.5, [step_deg * ch for ch in range(len(gens))])
    meas = {adc: np.degrees(np.angle(stepped[adc] / base[adc])) for _, adc in chk.pairs}
    sign = 1
    if chk.rf_hz is not None:  # pick the sign that fits (spectrum inversion in the frequency plan)
        cost = {s: sum(abs(wrap(meas[a] - s * step_deg * d)) for d, a in chk.pairs) for s in (1, -1)}
        sign = min(cost, key=lambda s: cost[s])
        if sign < 0:
            print("  (spectrum inverted in RF mode: phase steps measured with opposite sign)")
    for dac, adc in chk.pairs:
        want = wrap(sign * step_deg * dac)
        err = wrap(meas[adc] - want)
        chk.report(
            f"DAC{dac} CW phase step on ADC{adc}",
            abs(err) < tol_deg,
            f"{meas[adc]:+.2f} deg (commanded {want:+.1f}, error {err:+.2f})",
        )
    half = setup(0.25, [step_deg * ch for ch in range(len(gens))])
    ratios = [abs(half[adc]) / abs(stepped[adc]) for _, adc in chk.pairs]
    chk.report(
        "CW amplitude halves", all(abs(r - 0.5) < 0.02 for r in ratios), f"ratios {np.round(ratios, 3).tolist()}"
    )
    for wg in gens:  # back to single playback
        wg.mode = 0
    ol.apply_dac_settings()
    chk.dac_offset(0.0)


def check_loop(chk, rows=1024, f_mhz=200.0, max_phase_deg=5.0):
    """
    Loop mode: a waveform of `rows` rows (4.1 us at 1024), with a whole number of tone cycles, played in loop mode must
    fill the whole 8.2 us ADC capture with no phase jump at the wraps; single playback of the same length would leave
    the second half of the capture empty. Back in single mode, playback must stop.
    """
    ol, gens = chk.ol, chk.gens
    fs_complex = ol.dac_sampling_rate / 2
    t_loop = rows * (gens[0].out_data_width // 32) / fs_complex
    f_hz = round(f_mhz * 1e6 * t_loop) / t_loop
    t = np.arange(gens[0].wave_mem.size // 2) / fs_complex
    c = chk.amplitude * 32767 * np.exp(2j * np.pi * f_hz * t)
    iq = np.empty(2 * c.size, dtype=np.int16)
    iq[0::2] = np.round(c.real)
    iq[1::2] = np.round(c.imag)
    chk._write_all(iq)
    for wg in gens:
        wg.wave_length = rows
    time.sleep(0.001)  # a loop keeps the length latched at its trigger: let any single pass of the old length finish
    for wg in gens:
        wg.mode = 1
    ol.apply_dac_settings()
    chk.wait_captures()
    modes = [wg.active_mode for wg in gens]
    busy = [int(wg.busy) for wg in gens]
    chk.report(
        "loop mode active and playing on all DACs",
        all(m == 1 for m in modes) and all(busy),
        f"active modes {modes}, busy {busy}",
    )
    chk.check_adc_continuity(
        max_phase_deg, label=f" (loop mode, {rows} rows = {t_loop * 1e6:.3f} us, {f_hz / 1e6:.4f} MHz)"
    )
    for wg in gens:
        wg.mode = 0
    ol.apply_dac_settings()
    time.sleep(0.01)  # the current pass ends within t_loop; a 0.1 s trigger then plays it once (busy 4e-5 of the time)
    busy = [int(wg.busy) for wg in gens]
    chk.report("playback stops after leaving loop mode", not any(busy), f"busy {busy}")
    for wg in gens:
        wg.wave_length = 0


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
    Needs a bitstream with the axil_wave_gen debug status (bit 1 tready, bit 2 playback row valid, bits 16+
    play_row) and the axi_wave_cap CSR. Prints how often tready is high and a playback row is on the stream, how often
    the playing row jumps back (restarts) or stays put, and the capture counters one second apart (expected: one
    capture per trigger).
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
        f"  stream poll {when}: {n} samples, tready {100 * rdy / n:.1f} %, playing {100 * vld / n:.1f} %, "
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
    parser.add_argument("--config", default="MIMO_5G_ZCU208", help="overlay config (LBL208: MIMO_5G_LBL208)")
    parser.add_argument(
        "--f-mhz", type=float, default=None, help="test tone (default 200 MHz; RF mode: offset from --rf-mhz, 5 MHz)"
    )
    parser.add_argument("--amplitude", type=float, default=0.5, help="tone amplitude, fraction of full scale")
    parser.add_argument("--max-phase-deg", type=float, default=5.0, help="ADC phase residual limit")
    parser.add_argument("--no-adc", action="store_true", help="skip the ADC check (no loopback cables)")
    parser.add_argument("--repeat", type=int, default=1, help="repeat the ADC capture check")
    parser.add_argument(
        "--nco", action="store_true", help="also check with constant I/Q and the DAC NCO making the tone"
    )
    parser.add_argument(
        "--rf-mhz",
        type=float,
        default=None,
        help="RF mode: DAC and ADC NCOs at this RF frequency, complex baseband analysis (LBL208 front end: 3000)",
    )
    parser.add_argument(
        "--pairs", default=None, help="cabled loopback paths DAC:ADC, e.g. 6:7 or 0:0,1:1 (default DAC n -> ADC n)"
    )
    parser.add_argument(
        "--atten",
        default=None,
        help="LBL208 front-end attenuators slice:index=dB, e.g. 4:0=20,4:1=2 (others keep 31.5 dB from the load)",
    )
    parser.add_argument(
        "--rx-atten-db",
        type=float,
        default=None,
        help="LBL208: set all RX front-end attenuators (0-31.5 dB; the overlay load sets 31.5)",
    )
    args = parser.parse_args()

    ol = MimoMtsOverlay(config=args.config, download=True)
    assert hasattr(ol, "wave_gen"), "overlay has no waveform generator"
    gens = getattr(ol, "wave_gens", [ol.wave_gen])
    print(
        f"wave_gen: {len(gens)} x {ol.wave_gen.out_data_width}-bit rows x {ol.wave_gen.bank_depth} "
        f"(register map version 0x{getattr(ol.wave_gen, 'version', 0):x}); captures: {ol.adc_bufs[0].size} int16 per "
        f"stream; DAC copy capture: {'yes' if ol.dac_capture is not None else 'no'}"
    )

    if args.rx_atten_db is not None:
        ffe = getattr(ol, "ffe", None)
        if ffe is None:
            print("  (--rx-atten-db ignored: no analog front end in this overlay)")
        else:
            print(f"  RX attenuators of slices {ffe.set_rx_attenuation(args.rx_atten_db)} set to {args.rx_atten_db} dB")
    if args.atten:
        ffe = getattr(ol, "ffe", None)
        if ffe is None:
            print("  (--atten ignored: no analog front end in this overlay)")
        else:
            for item in args.atten.split(","):
                key, db = item.split("=")
                s_id, k = (int(v) for v in key.split(":"))
                ffe.slices[s_id].attenuators[k].set_db(float(db))
                print(f"  front-end slice {s_id} attenuator {k} set to {float(db)} dB")
    pairs = None
    if args.pairs:
        pairs = [tuple(int(v) for v in p.split(":")) for p in args.pairs.split(",")]
    rf_hz = None if args.rf_mhz is None else args.rf_mhz * 1e6
    f_mhz = args.f_mhz if args.f_mhz is not None else (200.0 if rf_hz is None else 5.0)
    chk = Mimo5gCheck(ol, f_mhz * 1e6, args.amplitude, rf_hz=rf_hz, pairs=pairs)
    print(
        f"  {'RF mode at ' + str(args.rf_mhz) + ' MHz' if rf_hz else 'direct mode'}, tone {f_mhz} MHz, "
        f"pairs (DAC, ADC) {chk.pairs}"
    )
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
            chk.dac_offset(f_mhz * 1e6)
            for r in range(args.repeat):
                chk.wait_captures()
                chk.check_adc_continuity(args.max_phase_deg, label=f" (tone from DAC NCO, run {r + 1})")
            chk.dac_offset(0.0)
        if len(gens) > 1:
            if rf_hz is None:
                check_per_dac_tones(chk)
            else:
                check_per_dac_tones(chk, f0_mhz=4.0, step_mhz=4.0)
        if getattr(ol.wave_gen, "version", 0):
            check_cw(chk, f_mhz=200.0 if rf_hz is None else 3.0)
            check_loop(chk, f_mhz=f_mhz, max_phase_deg=args.max_phase_deg)
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
