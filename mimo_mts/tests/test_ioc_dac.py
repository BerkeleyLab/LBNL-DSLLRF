"""
Check the DAC PVs of a running IOC through Channel Access, with a DAC n -> ADC n loopback cable on every channel
(as on the ZCU208 test setup). Runs on any host that reaches the IOC; needs pyepics (a project dependency).

Checks are chosen from the PVs the IOC has:
- every IOC with `DAC:IWF` (shared waveform): a 1 us pulse written to all DACs arrives on every ADC, with the
  same width and start on all channels;
- every IOC: capture reads are not torn at a fast trigger (1 ms), with the ADC mixer slightly off the DAC mixer so
  each capture starts at a different phase (development plan item 11);
- every IOC: rf_control:dac_enable bit 0 silences all DACs (on mimo_mts_5g bitstreams from plan item 14 on);
- IOCs with one waveform generator per DAC (`DAC{n}:mode`, `DAC:apply`, e.g. mimo-5g-zcu208-ioc):
  1. mode and CW values are staged: no effect until `DAC:apply`, then `DAC{n}:mode:RBV` follows;
  2. a CW phase / amplitude step on one DAC moves only its ADC (+90 deg, half amplitude);
  3. per-DAC phases 45 deg * n on one apply;
  4. NCO phase repeatability (informational): per-ADC phase change after setting the mixers to 0 and back;
  5. per-DAC waveform: a 1 us pulse on one DAC only;
  6. loop mode: the free-running loop moves the pulse between captures; single mode keeps it in place.
With --no-loopback only the PV-level checks run (staging and mode readbacks).

The DAC and ADC mixers are set to --rf-mhz, so each ADC sees its DAC at baseband in DSP:ADC{n}:AWF / PWF; phases
and amplitudes are compared with a baseline (cable and NCO phases differ per channel). The test sets
rf_control:dac_enable bit 0 (the IOCs boot with the DACs disabled); the IOC state (DAC enable, mixers, modes, CW
values, lengths, shared waveform) is restored at the end, also after a failure.

    python3 mimo_mts/tests/test_ioc_dac.py [--prefix MIMO_5G_ZCU208] [--rf-mhz 200] [--channel 3] [--no-loopback]
"""

import argparse
import sys
import time
from typing import Any

import numpy as np


def _import_epics() -> Any:
    try:
        import epics  # pyright: ignore[reportMissingImports]
    except ImportError:
        epics = None
    if not hasattr(epics, "PV"):  # also catches the repository's epics/ folder (Phoebus screens) found instead
        sys.exit("test_ioc_dac.py needs pyepics: pip install pyepics")
    return epics


def wrap_deg(x):
    return (np.asarray(x) + 180) % 360 - 180


class IocDacCheck:
    def __init__(self, prefix, settle_s=1.5, timeout_s=5.0):
        self.epics: Any = _import_epics()  # pyepics (not the repository's epics/ screens folder)
        self.prefix = prefix
        self.settle_s = settle_s
        self.timeout_s = timeout_s
        self.results = []
        self._pvs = {}
        self.t_dsp = np.zeros(0)  # DSP:TWF, read in main()

    # --- Channel Access helpers ---
    def pv(self, name):
        if name not in self._pvs:
            self._pvs[name] = self.epics.PV(f"{self.prefix}:{name}", connection_timeout=self.timeout_s, form="time")
        return self._pvs[name]

    def exists(self, name):
        return self.pv(name).wait_for_connection(timeout=self.timeout_s)

    def get(self, name, as_string=False):
        value = self.pv(name).get(timeout=self.timeout_s, as_string=as_string, use_monitor=False)
        if value is None:
            raise RuntimeError(f"{self.prefix}:{name}: no value (IOC running? prefix right?)")
        return value

    def put(self, name, value):
        if not self.pv(name).put(value, wait=True, timeout=self.timeout_s):
            raise RuntimeError(f"{self.prefix}:{name}: put timed out")

    def waveform_time(self):
        """Server timestamp of the last DSP:ADC0:AWF update."""
        pv = self.pv("DSP:ADC0:AWF")
        pv.get(timeout=self.timeout_s, use_monitor=False)
        return pv.timestamp

    def settle(self, n=1):
        """
        Wait for fresh captures after a change (the IOC triggers every 0.5 s by default), and check that the IOC is
        still updating the ADC waveforms: a stalled capture loop would otherwise make every later check read old data.
        """
        before = self.waveform_time()
        time.sleep(n * self.settle_s)
        if self.waveform_time() == before:
            time.sleep(2 * self.settle_s)  # one more chance (slow trigger)
            if self.waveform_time() == before:
                raise RuntimeError(f"ADC waveforms not updating since {time.ctime(before)}: IOC capture loop stalled?")

    def report(self, name, ok, detail=""):
        self.results.append((name, ok))
        print(f"[{'PASS' if ok else 'FAIL'}] {name}{': ' + detail if detail else ''}")

    def info(self, text):
        print(f"  {text}")

    # --- measurements from the decimated ADC waveforms ---
    def count_channels(self, fmt, n_max=16):
        n = 0
        while n < n_max and self.exists(fmt.format(n)):
            n += 1
        return n

    def adc_wave(self, ch):
        """Complex baseband of ADC ch (DSP:ADC{ch}:AWF / PWF) and its time axis in ns."""
        a = np.asarray(self.get(f"DSP:ADC{ch}:AWF"), dtype=float)
        p = np.asarray(self.get(f"DSP:ADC{ch}:PWF"), dtype=float)
        n = min(a.size, p.size, self.t_dsp.size)
        return self.t_dsp[:n], a[:n] * np.exp(1j * np.radians(p[:n]))

    def phasors(self, chans, t0_ns=400.0):
        """Mean complex amplitude of each ADC after t0_ns (CW: the whole capture after the loopback latency)."""
        out = []
        for ch in chans:
            t, z = self.adc_wave(ch)
            out.append(z[t >= t0_ns].mean())
        return np.array(out)

    def pulse(self, ch):
        """(start ns, width ns) of the part of the ADC amplitude above half its maximum, or None if there is none."""
        t, z = self.adc_wave(ch)
        a = np.abs(z)
        if a.max() < 50:
            return None
        on = np.flatnonzero(a > 0.5 * a.max())
        return t[on[0]], t[on[-1]] - t[on[0]] + (t[1] - t[0])

    def phase_stability(self, chans, n_captures=4, t0_ns=400.0):
        """
        Per channel: phase slope within one capture (deg/us, a frequency offset between DAC and ADC mixers shows here)
        and the spread of the capture phase over n_captures (drift or NCO phase changes between captures).
        """
        phases = []
        slopes = {}
        for k in range(n_captures):
            if k:
                self.settle()
            row = []
            for ch in chans:
                t, z = self.adc_wave(ch)
                sel = t >= t0_ns
                row.append(np.degrees(np.angle(z[sel].mean())))
                if k == 0:
                    ph = np.degrees(np.unwrap(np.angle(z[sel])))
                    slopes[ch] = np.polyfit(t[sel] / 1e3, ph, 1)[0]
            phases.append(row)
        phases = np.array(phases)
        spread = np.ptp(np.degrees(np.unwrap(np.radians(phases), axis=0)), axis=0)
        return {ch: (slopes[ch], spread[i]) for i, ch in enumerate(chans)}


def pulse_iq(chk, length_ns, level=16000, name="DAC:TWF"):
    """I (constant `level` for length_ns, then 0) and Q (0) at the DAC complex rate, as long as the DAC waveform."""
    t = np.asarray(chk.get(name), dtype=float)
    i = np.where(t < length_ns, level, 0).astype(np.int16)
    return i, np.zeros_like(i)


def check_shared_waveform(chk, chans, length_ns=1000.0):
    """DAC:IWF writes every DAC: the pulse must arrive on every ADC with the same width and start."""
    i, q = pulse_iq(chk, length_ns)
    chk.put("DAC:QWF", q)
    chk.put("DAC:IWF", i)
    chk.settle(2)
    res = {ch: chk.pulse(ch) for ch in chans}
    missing = [ch for ch, r in res.items() if r is None]
    if missing:
        chk.report("shared waveform on every ADC", False, f"no pulse on ADC {missing} (cables? DAC enabled?)")
        return
    starts = np.array([res[ch][0] for ch in chans])
    widths = np.array([res[ch][1] for ch in chans])
    ok = np.all(np.abs(widths - length_ns) < 50) and np.ptp(starts) < 20
    chk.report(
        "shared waveform on every ADC",
        ok,
        f"widths {np.round(widths).astype(int).tolist()} ns (expected {length_ns:.0f}), "
        f"starts {np.round(starts).astype(int).tolist()} ns",
    )


def check_capture_reads(
    chk, chans, rf_mhz, has_shared, n_reads=12, period_cycles=250000, df_mhz=0.3003717, block_ns=100.0, tol_deg=2.0
):
    """
    Capture reads are not torn (development plan item 11): with a fast trigger and the ADC mixer df_mhz off the DAC
    mixer, the baseband rotates, so every capture starts at a different phase but is a straight phase ramp. A read
    that mixes two captures shows a phase jump. Free-running captures read after the IRQ tear when the read takes
    longer than the trigger period; one-shot captures (armed per read) do not.
    The phase is averaged over block_ns blocks first: with ADC decimation 1 the R2C mixer output also carries the
    sum-frequency image, which the IOC's short average (4 ns) passes as a ripple of several degrees.
    """
    saved_period = chk.get("rf_control:trig_period:RBV")
    if has_shared:
        i, q = pulse_iq(chk, 1e9)  # constant: a 16.4 us burst per trigger, longer than the capture
        chk.put("DAC:QWF", q)
        chk.put("DAC:IWF", i)
    chk.put("rfdc_mixer:adc_rf_freq_mhz", rf_mhz + df_mhz)
    chk.put("rf_control:trig_period", period_cycles)
    try:
        chk.settle()
        worst = 0.0
        torn = 0
        for _ in range(n_reads):
            time.sleep(0.25)
            for ch in chans:
                t, z = chk.adc_wave(ch)
                a = np.abs(z)
                sel = (t >= 400) & (a > 0.5 * a.max())
                nb = int(sel.sum() * (t[1] - t[0]) // block_ns)
                if nb < 10:
                    continue
                k = sel.sum() // nb
                zb = z[sel][: nb * k].reshape(nb, k).mean(axis=1)
                tb = t[sel][: nb * k].reshape(nb, k).mean(axis=1)
                ph = np.degrees(np.unwrap(np.angle(zb)))
                resid = np.abs(ph - np.polyval(np.polyfit(tb, ph, 1), tb)).max()
                worst = max(worst, resid)
                torn += resid > tol_deg
        chk.report(
            "capture reads not torn (fast trigger, rotating baseband)",
            torn == 0,
            f"{n_reads} reads x {len(chans)} ADCs at trig_period {period_cycles}: {torn} with a phase jump "
            f"(> {tol_deg} deg from a ramp, {block_ns:.0f} ns blocks), worst residual {worst:.2f} deg",
        )
    finally:
        chk.put("rf_control:trig_period", saved_period)
        chk.put("rfdc_mixer:adc_rf_freq_mhz", rf_mhz)
        chk.settle()


def check_dac_enable(chk, chans, has_shared):
    """rf_control:dac_enable bit 0 gates every DAC: no burst on any ADC while it is clear, bursts again once set."""
    if has_shared:
        i, q = pulse_iq(chk, 1e9)  # constant over the whole memory
        chk.put("DAC:QWF", q)
        chk.put("DAC:IWF", i)
    value = int(chk.get("rf_control:dac_enable:RBV"))
    chk.put("rf_control:dac_enable", value & ~1)
    chk.settle(2)
    off = [chk.pulse(n) for n in chans]
    chk.put("rf_control:dac_enable", value | 1)
    chk.settle(2)
    on = [chk.pulse(n) for n in chans]
    ok = all(r is None for r in off) and all(r is not None for r in on)
    chk.report(
        "dac_enable bit 0 gates every DAC",
        ok,
        f"bursts with the DACs disabled: {sum(r is not None for r in off)}/{len(chans)}, "
        f"enabled: {sum(r is not None for r in on)}/{len(chans)}",
    )


def set_modes(chk, n_dac, mode, apply=True):
    for ch in range(n_dac):
        chk.put(f"DAC{ch}:mode", mode)
    if apply:
        chk.put("DAC:apply", 1)


def check_cw(chk, n_dac, chans, ch_step, loopback, tol_deg=1.0, tol_amp=0.02):
    """Staging, a CW step on one DAC, and 45 deg * n on all DACs. Returns the baseline phasors (or None)."""
    rbv0 = [chk.get(f"DAC{ch}:mode:RBV", as_string=True) for ch in range(n_dac)]
    for ch in range(n_dac):
        chk.put(f"DAC{ch}:cw:amp", 0.5)
        chk.put(f"DAC{ch}:cw:phase", 0.0)
    set_modes(chk, n_dac, "CW", apply=False)
    chk.settle()
    rbv = [chk.get(f"DAC{ch}:mode:RBV", as_string=True) for ch in range(n_dac)]
    chk.report("modes staged until DAC:apply", rbv == rbv0, f"mode:RBV {rbv} (before {rbv0})")
    chk.put("DAC:apply", 1)
    chk.settle(2)
    rbv = [chk.get(f"DAC{ch}:mode:RBV", as_string=True) for ch in range(n_dac)]
    chk.report("CW active on all DACs after DAC:apply", all(r == "CW" for r in rbv), f"mode:RBV {rbv}")
    if not loopback:
        return None

    stab = chk.phase_stability(chans)
    for ch in chans:
        slope, spread = stab[ch]
        chk.info(f"ADC{ch} CW phase: slope {slope:+.3f} deg/us within a capture, spread {spread:.2f} deg over captures")
    ok = all(abs(s) * 8 < tol_deg and sp < tol_deg for s, sp in stab.values())
    chk.report("CW phase stable within and between captures", ok, f"tolerance {tol_deg} deg")
    z0 = chk.phasors(chans)

    def compare(name, z, want_deg, want_ratio):
        d = wrap_deg(np.degrees(np.angle(z / z0)))
        r = np.abs(z / z0)
        for k, ch in enumerate(chans):
            ok = abs(wrap_deg(d[k] - want_deg[k])) < tol_deg and abs(r[k] - want_ratio[k]) < tol_amp
            chk.report(
                f"{name}: ADC{ch}",
                ok,
                f"phase {d[k]:+7.2f} deg (expected {wrap_deg(want_deg[k]):+7.1f}), amplitude ratio {r[k]:.3f} "
                f"(expected {want_ratio[k]:.2f})",
            )

    # one DAC: staged (no change), then applied (+90 deg, half amplitude); the others unchanged
    chk.put(f"DAC{ch_step}:cw:phase", 90.0)
    chk.put(f"DAC{ch_step}:cw:amp", 0.25)
    chk.settle()
    compare("CW step staged, before apply", chk.phasors(chans), [0.0] * len(chans), [1.0] * len(chans))
    chk.put("DAC:apply", 1)
    chk.settle(2)
    want_d = [90.0 if ch == ch_step else 0.0 for ch in chans]
    want_r = [0.5 if ch == ch_step else 1.0 for ch in chans]
    compare(f"CW step on DAC{ch_step}", chk.phasors(chans), want_d, want_r)

    # all DACs at once: 45 deg * n
    chk.put(f"DAC{ch_step}:cw:amp", 0.5)
    for ch in range(n_dac):
        chk.put(f"DAC{ch}:cw:phase", 45.0 * ch)
    chk.put("DAC:apply", 1)
    chk.settle(2)
    compare("CW 45 deg * n on one apply", chk.phasors(chans), [45.0 * ch for ch in chans], [1.0] * len(chans))
    for ch in range(n_dac):
        chk.put(f"DAC{ch}:cw:phase", 0.0)
    chk.put("DAC:apply", 1)
    chk.settle(2)
    return z0


def check_nco_repeatability(chk, chans, rf_mhz):
    """Informational: per-ADC CW phase change after setting both mixers to 0 MHz and back (NCO phase at an update)."""
    za = chk.phasors(chans)
    for conv in ("dac", "adc"):
        chk.put(f"rfdc_mixer:{conv}_rf_freq_mhz", 0.0)
    chk.settle()
    for conv in ("dac", "adc"):
        chk.put(f"rfdc_mixer:{conv}_rf_freq_mhz", rf_mhz)
    chk.settle(2)
    d = wrap_deg(np.degrees(np.angle(chk.phasors(chans) / za)))
    chk.info(
        "NCO repeatability (informational): per-ADC phase change after mixers 0 and back: "
        + ", ".join(f"ADC{ch} {d[k]:+.1f}" for k, ch in enumerate(chans))
        + " deg"
    )


def check_per_dac_waveform(chk, n_dac, chans, ch_pulse, has_shared, length_ns=1000.0):
    """Single mode: a 1 us pulse on one DAC only; with a shared waveform the others play it over the whole capture."""
    set_modes(chk, n_dac, "single")
    if has_shared:
        i, q = pulse_iq(chk, 1e9)  # constant over the whole memory on every DAC
        chk.put("DAC:QWF", q)
        chk.put("DAC:IWF", i)
    i, q = pulse_iq(chk, length_ns)
    chk.put(f"DAC{ch_pulse}:QWF", q)
    chk.put(f"DAC{ch_pulse}:IWF", i)
    chk.settle(2)
    res = {ch: chk.pulse(ch) for ch in chans}
    r = res.get(ch_pulse)
    ok = r is not None and abs(r[1] - length_ns) < 50
    chk.report(
        f"DAC{ch_pulse}:IWF pulse on ADC{ch_pulse} only",
        ok,
        f"start {r[0]:.0f} ns, width {r[1]:.0f} ns (expected {length_ns:.0f})" if r else "no pulse",
    )
    if has_shared:
        long_ok = all(res[ch] is not None and res[ch][1] > 5 * length_ns for ch in chans if ch != ch_pulse)
        widths = {ch: (round(res[ch][1]) if res[ch] else None) for ch in chans if ch != ch_pulse}
        chk.report("other DACs keep the shared waveform", long_ok, f"widths (ns) {widths}")
    return r


def check_wave_length(chk, chans, ch, tol_ns=20.0):
    """
    Waveform length PVs (ns): with a constant waveform on every DAC, the ADC burst lasts DAC:wave_length;
    rf_control:pulse_length (4 ns cycles) sets the same length; DAC{ch}:wave_length changes only that DAC.
    """
    i, q = pulse_iq(chk, 1e9)  # constant over the whole memory
    chk.put("DAC:QWF", q)
    chk.put("DAC:IWF", i)

    def widths():
        chk.settle(2)
        return {n: (r[1] if (r := chk.pulse(n)) else None) for n in chans}

    def report(name, got, want):
        ok = all(w is not None and abs(w - want[n]) < tol_ns for n, w in got.items())
        chk.report(name, ok, f"burst widths (ns) {[None if w is None else round(w) for w in got.values()]}")

    chk.put("DAC:wave_length", 2000)
    report("DAC:wave_length 2000 ns on every DAC", widths(), dict.fromkeys(chans, 2000))
    rbv = chk.get(f"DAC{ch}:wave_length:RBV")
    chk.report("DAC{n}:wave_length:RBV follows", abs(rbv - 2000) < 1, f"DAC{ch} RBV {rbv} ns")
    chk.put("rf_control:pulse_length", 250)
    report("rf_control:pulse_length 250 cycles = 1000 ns", widths(), dict.fromkeys(chans, 1000))
    chk.put(f"DAC{ch}:wave_length", 500)
    report(f"DAC{ch}:wave_length 500 ns on DAC{ch} only", widths(), {n: 500 if n == ch else 1000 for n in chans})


def check_loop(chk, ch_pulse, n_captures=4):
    """Loop mode: the whole memory loops freely, so the pulse moves between captures; single mode keeps it fixed."""

    def starts(n):
        out = []
        for k in range(n):
            if k:
                chk.settle()
            r = chk.pulse(ch_pulse)
            out.append(None if r is None else round(r[0]))
        return out

    chk.put(f"DAC{ch_pulse}:mode", "loop")
    chk.put("DAC:apply", 1)
    chk.settle(2)
    rbv = chk.get(f"DAC{ch_pulse}:mode:RBV", as_string=True)
    chk.report(f"DAC{ch_pulse} loop mode active", rbv == "loop", f"mode:RBV {rbv}")
    s = starts(n_captures)
    found = [x for x in s if x is not None]
    moving = None in s or (len(found) > 1 and np.ptp(found) > 100)
    chk.report("loop: pulse position changes between captures", moving, f"pulse starts (ns) {s}")
    chk.put(f"DAC{ch_pulse}:mode", "single")
    chk.put("DAC:apply", 1)
    chk.settle(2)
    s = starts(3)
    fixed = None not in s and np.ptp(s) < 20
    chk.report("single: pulse position fixed", fixed, f"pulse starts (ns) {s}")


def main():
    parser = argparse.ArgumentParser(description="Check the DAC PVs of a running IOC (DAC n -> ADC n loopback).")
    parser.add_argument("--prefix", default="MIMO_5G_ZCU208", help="IOC PV prefix (the overlay name)")
    parser.add_argument("--rf-mhz", type=float, default=200.0, help="DAC and ADC mixer RF frequency")
    parser.add_argument("--channel", type=int, default=3, help="DAC for the single-channel checks")
    parser.add_argument("--settle", type=float, default=1.5, help="seconds to wait for fresh captures")
    parser.add_argument("--no-loopback", action="store_true", help="PV-level checks only (no loopback cables)")
    args = parser.parse_args()

    chk = IocDacCheck(args.prefix, settle_s=args.settle)
    if not chk.exists("DSP:TWF"):
        sys.exit(f"no IOC with prefix {args.prefix} (DSP:TWF not found)")
    chk.t_dsp = np.asarray(chk.get("DSP:TWF"), dtype=float)
    n_adc = chk.count_channels("ADC{}:IWF")
    n_dac = chk.count_channels("rfdc_mixer:DAC{}:rf_freq_mhz")
    has_shared = chk.exists("DAC:IWF")
    per_dac = chk.exists("DAC0:mode") and chk.exists("DAC:apply")
    chans = list(range(min(n_adc, n_dac)))
    ch = min(args.channel, n_dac - 1)
    print(
        f"{args.prefix}: {n_adc} ADCs, {n_dac} DACs, shared DAC waveform: {'yes' if has_shared else 'no'}, "
        f"per-DAC generators: {'yes' if per_dac else 'no'}; loopback DAC n -> ADC n: {not args.no_loopback}"
    )

    # state to restore
    saved_rf = {c: chk.get(f"rfdc_mixer:{c}_rf_freq_mhz:RBV") for c in ("dac", "adc")}
    saved_wfm = {p: np.array(chk.get(f"DAC:{p}WF")) for p in ("I", "Q")} if has_shared else None
    has_wave_length = chk.exists("DAC:wave_length")
    saved_pulse_length = chk.get("rf_control:pulse_length:RBV")
    saved_dac_enable = int(chk.get("rf_control:dac_enable:RBV"))
    saved_wave_length = chk.get("DAC:wave_length") if has_wave_length else None
    saved_cw = {(n, k): chk.get(f"DAC{n}:cw:{k}") for n in range(n_dac) for k in ("amp", "phase") if per_dac}
    try:
        try:
            chk.put("rf_control:dac_enable", saved_dac_enable | 1)  # the IOCs boot with the DACs disabled
            for c in ("dac", "adc"):
                chk.put(f"rfdc_mixer:{c}_rf_freq_mhz", args.rf_mhz)
            if per_dac:
                set_modes(chk, n_dac, "single")
            chk.settle(2)
            if has_shared and not args.no_loopback:
                check_shared_waveform(chk, chans)
            if not args.no_loopback:
                check_capture_reads(chk, chans, args.rf_mhz, has_shared)
                check_dac_enable(chk, chans, has_shared)
            if per_dac:
                check_cw(chk, n_dac, chans, ch, loopback=not args.no_loopback)
                if not args.no_loopback:
                    check_nco_repeatability(chk, chans, args.rf_mhz)
                    if check_per_dac_waveform(chk, n_dac, chans, ch, has_shared) is not None:
                        check_loop(chk, ch)
                    if has_wave_length and has_shared:
                        check_wave_length(chk, chans, ch)
                else:
                    set_modes(chk, n_dac, "loop")
                    chk.settle()
                    rbv = [chk.get(f"DAC{n}:mode:RBV", as_string=True) for n in range(n_dac)]
                    chk.report("loop mode active on all DACs", all(r == "loop" for r in rbv), f"mode:RBV {rbv}")
        except RuntimeError as e:  # e.g. the IOC stopped updating the ADC waveforms: later checks would be meaningless
            chk.report("IOC responsive", False, str(e))
    finally:
        print("  restoring the IOC state")
        if per_dac:
            for (n, k), v in saved_cw.items():
                chk.put(f"DAC{n}:cw:{k}", v)
            set_modes(chk, n_dac, "single")
        chk.put("rf_control:pulse_length", saved_pulse_length)  # on per-DAC IOCs this also sets DAC:wave_length
        if saved_wave_length is not None:
            chk.put("DAC:wave_length", saved_wave_length)
        if saved_wfm is not None:
            chk.put("DAC:QWF", saved_wfm["Q"])
            chk.put("DAC:IWF", saved_wfm["I"])
        for c, v in saved_rf.items():
            chk.put(f"rfdc_mixer:{c}_rf_freq_mhz", v)
        chk.put("rf_control:dac_enable", saved_dac_enable)

    failed = [name for name, ok in chk.results if not ok]
    print(f"\n{len(chk.results) - len(failed)}/{len(chk.results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
