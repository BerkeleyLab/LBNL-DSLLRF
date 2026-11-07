# RF-ADC interleaving calibration: ZCU208 findings

Hardware investigation for the ADC calibration support in `mimo_mts` (branch `feature/adc-interleaving-cal`,
MR !37), November 2026. Notebooks with the raw outputs:

- `doc/zcu208/adc_calibration.ipynb`: calibration states, pulsed tracking, training at 3·Fs/4, restore tests.
- `doc/zcu208/adc_reload_variability.ipynb`: load-to-load variability, tile restarts, clock re-programming.

## Setup

- ZCU208, overlay `ALS_LLRF_ZCU208`: Fs = 4 GSPS, ADC NCO 3000 MHz in the 2nd Nyquist zone, RFDC decimation 8
  (captures at 500 MSPS, ±250 MHz).
- DAC-to-ADC0 loopback cable, **no filter**. The CW tone comes from the LLRF amplitude setpoint through the DAC NCO.
- ALS operates at a fixed ratio: f_ref = 499.64 MHz, Fs = 8·f_ref, carrier 6·f_ref = 3·Fs/4.

## Summary

1. **At 3·Fs/4 the interleaving errors are not visible as spurs.** Every interleaving product lies on the Fs/8
   grid, and the only grid point inside the decimated band is the carrier. The gain/skew image folds onto the carrier
   as a phase-dependent amplitude/phase error (image level -80 dBc ≈ 0.01 %, 0.006°; -50 dBc ≈ 0.3 %, 0.2°).
   Measurements therefore use a 2973 MHz probe tone, whose image appears at 6000 MHz − f_in = 3027 MHz.
2. **Background calibration must not track the ALS signal.** Tracking on 5 µs pulses raised the image from -82 to
   -52 dBc in 2 minutes, and tracking a CW tone at exactly 3·Fs/4 pushed TSCB to near its limits (-50 dBc).
   Frozen, nothing changed.
3. **Only GCB can be restored.** TSCB writes set the override bit but neither the read-back nor the measured image
   changes. Startup TSCB is near its limits in every load (-38 to -54 dBc if frozen at startup values).
4. **The loopback carrier level, and with it the calibration result, varies by about 4 dB between clock
   programmings.** It is set when the CLK104 is programmed, not by the converter tiles. The likely cause is that each
   LMX2594 divides an 8 GHz VCO by 2 without phase sync, so the DAC-to-ADC sample timing changes by half a sample
   between programmings. With no filter in the loopback, the DAC's 1027 MHz Nyquist image aliases onto the tone and
   adds or subtracts depending on that timing.
5. **The same timing ambiguity means the DAC-to-ADC RF phase is not deterministic across reboots** (half a sample
   ≈ 135° at 2998 MHz). This is outside the calibration work but matters for ALS.

## Calibration mechanics (driver and hardware behaviour)

| Item | Finding |
|---|---|
| State after overlay load | Not frozen, `DisableFreezePin=0`, as PG269 describes. |
| Software freeze | `DisableFreezePin=1`, toggle `FreezeCalibration`; `CalFrozen` follows. |
| Freeze across tile reset | Survives `restart_adc_tiles()`; cleared by an overlay reload. |
| Calibration mode | Reads 2 on all channels; not set by the driver (Gen 3 selects automatically). |
| GCB write | Read-back matches; zeroing GCB raises the image by 19 to 23 dB. Restore after reload works. |
| TSCB write | Override bit 15 set, value field keeps the engine value; no measurable effect. Not verified on restore. |
| Startup GCB / TSCB | GCB ≈ 0; TSCB 160–250 of ±255 in every load (tracks with no input during overlay init). |
| `restart_adc_tiles()` with freeze on | Foreground calibration re-runs (OCB2 changes), TSCB returns near zero, MTS check passes. |
| `pulse_length` | Counts 4 ns ticks (1250 ticks measured 5.00 µs). |

## Calibration measurements

Image at 3027 MHz for a 2973 MHz probe, ADC0. Carrier -28.8 dBFS (good clock state) unless noted.

| State | Image |
|---|---|
| Trained on CW and frozen | -81 to -85 dBc |
| GCB zeroed | -59.6 to -61.5 dBc |
| Trained, then 120 s of 5 µs pulses at 2 Hz with tracking | **-51.7 dBc** (GCB moved 14–94 LSB on all 8 channels) |
| Trained, then the same pulses frozen | -84.2 dBc (GCB unchanged) |
| Trained 60 s at 2973 MHz (carrier -33 dBFS) | -79.7 dBc |
| Trained 60 s at 3000 MHz = 3·Fs/4 (same load) | **-49.6 dBc** (TSCB moved up to 246 LSB) |
| Fresh load, frozen at startup values (good and bad loads) | -38 to -54 dBc |

Training needs about 60 s from startup values; 5 s was enough only when starting close to converged.

## Load-to-load variability

| Test | Carrier level changes? |
|---|---|
| Overlay reload (6 + 6 loads) | Yes: 3 of 12 loads at -28.7 to -28.8 dBFS, the rest at -32.1 to -32.9 dBFS |
| CLK104 read-back (LMX VCO core and calibration values, LMK status, MTS offsets) | Identical in good and bad loads |
| DAC tile reset (6×) | No |
| ADC tile restart with MTS re-sync (6×) | No |
| CLK104 re-programming only, then tile restart (6×) | **Yes**: -28.8, -32.9, -33.3, -28.9, -31.5, -28.8 dBFS |

In bad states, 60 s of training reached only -43 to -70 dBc. The carrier level is explained by the loopback
artifact in Summary item 4. That the calibration engine also converges worse in those states is likely related
(two coherent components share the same ADC bin) but not proven.

`LMX2594_4G.tcs`: `OUTA_MUX` = channel divider, `CHDIV` = /2, PLL N = 32 (VCO 8 GHz), `VCO_PHASE_SYNC` = 0. The
LMK04828 in `LMK04828_500M_CLKin0.tcs` runs PLL2 with /5 output dividers; the `_DIST` file instead passes CLKin1
straight through.

## Policy for `AlsLlrfLBL208` (current code)

Restore GCB/TSCB from the board's calibration file and freeze; without a file, freeze at startup values. Given the
findings:

- Freezing is required in all cases.
- Freezing at startup values is the worst option (TSCB near its limits). Freezing and then running
  `restart_adc_tiles()` gives TSCB near zero (about -55 dBc measured in a bad clock state).
- Restoring helps GCB only. Good calibration needs about 60 s of training on an off-carrier tone after each boot,
  which needs a way to inject such a tone in the installed system.

## Open items

1. Repeat the reload loop with a ~3 GHz band-pass filter in the loopback, or with an external generator. Expect a
   constant carrier and consistent training; then re-check restore versus training on clean data.
2. Measure the DAC-to-ADC loop phase at exactly 3000 MHz across CLK104 re-programmings to confirm the RF phase
   jumps directly.
3. Clock fixes to evaluate: LMX2594 `VCO_PHASE_SYNC` with a SYNC/SYSREF pulse (if the CLK104 routes one), the
   `_DIST` LMK configuration with the reference on CLKin1.
4. Decide the boot policy for `AlsLlrfLBL208` after items 1–3.

## Pitfalls found on the way

- After an overlay load the internal trigger can take many seconds before the first capture; captures are all zeros
  until then (pre-existing RTL issue). The notebooks' `capture()` waits for it.
- Resetting ADC tiles **without** re-running MTS and the FIFO setup scrambles the data path and leaves the capture
  logic stuck until the next overlay load. Use `restart_adc_tiles()`.
- Loading an overlay over a running one without `ol.free()` gave inconsistent results. Restart the kernel between
  notebook runs.
