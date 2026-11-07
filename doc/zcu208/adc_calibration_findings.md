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
   ≈ 135° at 2998 MHz). For ALS operation this is absorbed: phases are measured against the reference line on the
   same ADC clock, and the polar phase loop integrates out a static drive-phase offset. Where a fixed DAC-to-ADC
   phase is wanted, clocking ADC and DAC from one LMX2594 removes the ambiguity (see Open items).

## Conclusion

Background calibration must be frozen during ALS operation. Calibration coefficients should be trained on an
off-carrier CW tone (about 60 s), frozen and saved. GCB can be restored at boot; TSCB cannot be restored through the
driver override, so whether restore-and-freeze reproduces the trained performance after a reboot is the remaining
question, to be tested on the LBL208 with single-LMX clocking (`adc_calibration.ipynb` step 15).

| Element | Status |
|---|---|
| Freeze during operation | Supported: tracking on pulses -82 → -52 dBc in 2 min; at 3·Fs/4 TSCB runs to its limits |
| Train on an off-carrier tone | Supported: 60 s at 2973 MHz -79.7 dBc vs 60 s at 3000 MHz -49.6 dBc |
| Save coefficients | Works for all four blocks |
| Restore after reboot reproduces the trained state | **Not demonstrated**: only GCB restores; startup TSCB is near its limits; reload + restore was equal to the startup state in run 3 and 10 dB worse in run 4 |

Why it matters at the ALS carrier: trained calibration (about -80 dBc) means about 0.01 % / 0.006° carrier error;
startup TSCB (down to -38 dBc) means up to about 1.3 % / 0.7°, depending on the carrier phase. Frozen coefficients do
not follow temperature drift, so periodic retraining may be needed.

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

1. **Decisive test** (`adc_calibration.ipynb` step 15) on the LBL208 with clean loopback data: single-LMX clocking
   (item 3), a ~3 GHz band-pass filter, or an external generator. Train on the offset tone, freeze, save; then about
   five times: reload, freeze immediately, restore, measure; and the alternative freeze → `restart_adc_tiles()` →
   restore. Restore near the trained reference → the `AlsLlrfLBL208` policy is complete. Well below → TSCB cannot
   be restored; use the restart variant or retrain on an offset tone at every boot (needs a tone injection path).
2. Measure the DAC-to-ADC loop phase at exactly 3000 MHz across CLK104 re-programmings to confirm the RF phase
   jumps directly.
3. DAC-to-ADC clock phase (outside this MR):
   - **Impact on ALS operation: absorbed.** All ADC tiles are clocked from the ADC LMX through tile 225, so an ADC
     LMX shift moves every ADC channel equally, including the master-oscillator reference line; cavity phase relative
     to the reference is unchanged. A DAC LMX shift is a static drive-phase offset, which the polar phase loop
     (`phs_loop`, integral action) removes, so the cavity reaches its phase setpoint whatever the DAC phase after a
     reboot. Caveats: I/Q feedback would need the loop phase calibrated at each boot (a 135° error destabilizes it);
     if the phase integrator resets every pulse, the offset must be corrected within each 5 µs pulse; anything stored
     in DAC-phase terms across reboots (feedforward tables, loop-phase or latency diagnostics) shifts with it.
   - **Chosen approach where a fixed phase is wanted: clock ADC and DAC from one LMX2594.** RFoutA and RFoutB share
     the same channel divider (datasheet Figure 24, Table 9), so their relative phase is fixed whichever way the ÷2
     starts. Each CLK104 LMX brings out both outputs (`RF1_CLKO_A`/`_B`, J27–J30), ADC and DAC both run at 4 GSPS, and
     `LMX2594_4G.tcs` already routes OUTB through the channel divider (`OUTB_MUX` = 0). Cable ADC-LMX OUTA to the ADC
     clock and OUTB to the DAC clock: the phase-detector frequency and the optimized CLK104A loop filter stay
     unchanged, the DAC gets the same low-noise clock, and the DAC LMX can be powered down. To check: OUTB power into
     the DAC clock input, and the CLK104A layout and cabling. On the LBL208 this also gives a loopback without the
     4 dB level jumps, i.e. clean calibration data without a filter, and directly tests the explanation in Summary
     item 4.
   - **Rejected: LMX2594 phase-sync mode.** `VCO_PHASE_SYNC` is a register bit (R0[14]), not a pin. The current
     setup is datasheet SNAS696C §7.3.10 **Category 1** (no SYNC pulse needed), but sync mode moves the ÷2 into the
     feedback loop (IncludedDivide = 4); with minimum N = 28 the phase detector would have to drop from 250 to
     62.5 MHz, with ~6 dB more in-band PLL noise and a re-tuned loop filter. Not acceptable for the CLK104A's loop
     filter, which is optimized for lowest additive phase noise at 4 GHz. (The LMX SYNC pins are wired on the CLK104,
     schematic 038-05007-01 rev A02, but are only required for Category 3.)
   - **LMK04828 dividers:** in PLL2 mode the LMX references come from /5 DCLKout dividers excluded from SYNC
     (`0x144 = 0xFF`). This matters only while the two LMXs use separate references; single-LMX clocking or the
     `_DIST` configuration (dividers /1, available on CLK104A) avoids it.
4. Decide the boot policy for `AlsLlrfLBL208` from item 1.

## Pitfalls found on the way

- After an overlay load the internal trigger can take many seconds before the first capture; captures are all zeros
  until then (pre-existing RTL issue). The notebooks' `capture()` waits for it.
- Resetting ADC tiles **without** re-running MTS and the FIFO setup scrambles the data path and leaves the capture
  logic stuck until the next overlay load. Use `restart_adc_tiles()`.
- Loading an overlay over a running one without `ol.free()` gave inconsistent results. Restart the kernel between
  notebook runs.
