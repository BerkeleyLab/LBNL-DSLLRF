# Development plan

Planned work beyond the current merge requests, in suggested order. Each item lists the current state, the goal, the
first steps and open questions. Update this file as items progress; repository conventions are in
[developer_guide.md](developer_guide.md).

| # | Item | Depends on | Size |
|---|---|---|---|
| 1 | Upgrade cocotb to 2.1 | – | small |
| 2 | Complete the waveform generator and enable 5 GSPS | – | medium |
| 3 | LLRF logic in the MIMO overlays, CW mode | 2 (DAC path) | medium |
| 4 | Upgrade to PYNQ 4.0 (Vivado 2025.2) | – | large |
| 5 | Partial reconfiguration of the LLRF logic | 3, 4 | large |
| 6 | Complete EPICS PV reference (`PVs.md`) | – | small |

Items 4 and 5 both change the Vivado flow; doing the tool upgrade first avoids building the DFX flow twice. Item 6
is independent and can be done at any time; items 2, 3 and 5 add PVs, so generating the reference (below) pays off.

## 1. Upgrade cocotb to 2.1

**State.** `pyproject.toml` pins `cocotb==2.0.1` and `cocotbext-axi>=0.1.28`; the testbenches in `designs/ip/tb/` run
with Verilator (`cocotb_inc.mk`) locally and in the `rtl_test` CI job. The latest cocotb release is 2.1.0.

**Steps.**
- Bump the pin to `cocotb==2.1.0` (and check `cocotbext-axi` compatibility), run `make` in `designs/ip/tb`.
- Read the 2.1 release notes for deprecations that apply here (`cocotb.handle` value assignment, `Immediate`,
  `ClockCycles`, makefile variables in `cocotb_inc.mk`, `COCOTB_RESOLVE_X`).
- Check the Verilator version in the CI image (`xilinx_env_trixie_custom_verilator`) against cocotb 2.1's supported
  range; locally Verilator 5.052 is used.

**Done when** all 9 testbenches pass locally and in CI with no deprecation warnings.

## 2. Complete the waveform generator and enable 5 GSPS

**State.** Two wrappers around the common `wave_gen.v` core:

| Module | Interface | Status |
|---|---|---|
| `axi_wave_gen.v` | full AXI4 (256-bit data, burst writes), AXI-Stream out | used first in `ZCU208/mimo_mts_5g`; met timing, but the CPU stalled in the hardware test |
| `axil_wave_gen.v` | AXI4-Lite, AXI-Stream out | now in `ZCU208/mimo_mts_5g` and in `ZCU208/base` / `LBL208/base`; `mimo_mts_5g` fails timing |

`axil_wave_gen` uses its default 64-bit AXI4-Lite data width in both block designs (`C_S_AXI_DATA_WIDTH` is not
overridden; set it to 32 if a 32-bit interface is intended). In `base` it runs entirely on the 100 MHz `pl_clk0` with
a 256-bit output; in `mimo_mts_5g` the whole module, including its AXI-Lite slave, runs on the 250 MHz stream clock
with the default 320-bit output, so moving from `base` to `mimo_mts_5g` also raises its clock 2.5×.

Both have testbenches (`designs/ip/tb/axi_wave_gen`, `axil_wave_gen`) with a synthesis check (`synth/`). 5 GSPS ADC
and DAC sampling has already passed MTS on hardware with either wrapper.

5 GSPS also matters for ALS LLRF: at Fs = 10·f_ref = 4996.4 MSPS the RF-ADC interleaving products move 125 and
250 MHz away from the carrier instead of folding onto it at Fs = 8·f_ref, so the 0.1° phase requirement no longer
depends on the interleaving calibration (`doc/adc_calibration_findings.md`, "Alternative: sample at Fs = 10·f_ref").
A quick check on `mimo_mts_5g`: a tone at 3·Fs/5 should show those spurs and none on the tone.

Note on the timing failure: the only local `mimo_mts_5g` build (1 Aug, before the last design change on 4 Aug) fails
in the ADC receiver, not the waveform generator: `receiver/m32/axis_dwidth_converter_0` at 500 MHz, a high-fanout
clock enable with 89 % routing delay (WNS -0.057 ns, 54 endpoints). Rebuild the current design before drawing
conclusions.

**Steps.**
- Test `axil_wave_gen` in `ZCU208/base` first (100 MHz AXI clock, timing met): write a waveform through PYNQ, trigger
  it, check the captured output and that the CPU stays responsive during large writes.
- Rebuild `mimo_mts_5g` and locate the failing paths with `designs/scripts/vivado_reports.py` (per-clock slack) and
  the timing report. Candidates: the width converter's clock enable (pipeline it, or convert on a slower clock), and
  the wave generator itself at 250 MHz; consider clocking its AXI-Lite side on the AXI clock with a clock-domain
  crossing to the stream side.
- `axi_wave_gen` CPU stall: likely an AXI4 handshake or burst issue (for example `WLAST`, `BVALID`/`BREADY`, an
  unsupported burst type or a write that never completes). Reproduce in the testbench with `cocotbext-axi`'s AXI master
  using the same burst lengths and sizes as the PS; consider an AXI protocol checker (Xilinx `axi_protocol_checker`)
  in a debug build.
- Choose one flavor for 5 GSPS: `axil_wave_gen` is simpler but each waveform write is a 32-bit single beat;
  `axi_wave_gen` gives faster loading once the stall is fixed.

**Done when** `mimo_mts_5g` meets timing and plays a loaded waveform at 5 GSPS on hardware, with ADC capture and MTS
working, and an IOC (or notebook) loads waveforms without stalling the CPU.

## 3. LLRF logic in the MIMO overlays; CW mode

**State.** Only `als_llrf_mts` (ZCU208, LBL208) contains `axil_llrf` (RF control + `llrf_dsp`: amplitude/phase loops,
interpolator, averager). The `mimo_mts*` overlays have `axil_rf_control` with `dac_streamer` or the waveform generator
and no feedback DSP. The ALS overlays run the RFDC with decimation/interpolation 8 (500 MSPS, 250 MHz DSP clock); the
MIMO overlays sample directly (decimation 1).

**Steps.**
- Decide the DSP data path for direct sampling: decimate in the RFDC for the LLRF channels as in ALS, or add a
  fabric down-converter in front of `llrf_dsp`.
- Add the LLRF hierarchy to the MIMO block designs (ZCU208, LBL208, ZCU216), and the matching `ol_configs` entries
  and IOC classes.
- CW mode: `llrf_dsp` already drives continuously when `pulse_enable = 0` (`llrf_dsp.v:165`; pulsed when 1, gated
  by `pulse_length`). Bring this to the MIMO overlays with the LLRF logic, expose the mode as an IOC PV (today only
  set in `init_rf_control()`), and add a CW case to `test_axil_llrf.py`.
- Keep ADC interleaving calibration frozen in CW and pulsed operation (see MR !37).

**Done when** a MIMO overlay closes the amplitude/phase loop in pulsed and CW mode on hardware.

## 4. Upgrade to PYNQ 4.0

**State.** Boards run the PYNQ 3.0.1 image; overlays are built with Vivado 2022.1. `install.sh` patches PYNQ's
`xrfdc`/`xrfclk` from the BerkeleyLab fork for multi-tile synchronization, and `pyproject.toml` pins `pynq==3.0.1` and
`setuptools<82` (for `pkg_resources`).

**PYNQ 4.0 requirements** (PYNQ changelog): Xilinx tools **2025.2**, an **Ubuntu 24.04** root filesystem, and the
image build moved from Petalinux to AMD EDF (Yocto); `pynq.lib.arduino`, `logictools` and `rpi` were removed. ZCU208
images come from the RFSoC-PYNQ v4.0 release (EDF 2025.2 board support for ZCU208); confirm the board list and image
on pynq.io before planning LBL208 and ZCU216, which may need custom board images.

**Steps.**
- Install Vivado 2025.2 next to 2022.1; update `XILINX_VIVADO` and the CI image.
- Re-create each block design in 2025.2 (upgrade IP, re-export `<design>.tcl`), starting with `ZCU208/base`. Check the
  RFDC IP version against what PYNQ 4.0's `xrfdc` driver binds to.
- Port the MTS patches to PYNQ 4.0's `xrfdc`/`xrfclk`, or confirm they are upstream. Retest MTS latency and the
  CLK104/CLK104A programming (`config_clk104.py` uses private `xrfclk` helpers, see `typings/xrfclk`).
- Python: the Ubuntu 24.04 image moves from Python 3.10 to the version it ships; update `requires-python`, the
  `pynq` pin and the `typings/` stubs, and re-check `pkg_resources` use.
- Device-tree overlays (`designs/dts/`, `mimo_mts/boot.py`) under the EDF kernel.
- Board images for LBL208 (custom board files, `designs/board_files/lbl208`) and ZCU216.

**Done when** all CI overlays build with 2025.2 and every IOC runs on PYNQ 4.0 images with MTS and the CLK104
configuration verified.

## 5. Partial reconfiguration of the LLRF logic

**Goal.** Swap the LLRF processing (reconfigurable module) without reloading the static design: RFDC, MTS clocking,
CLK104 configuration and the PS stay running, so MTS alignment and the ADC calibration state survive a change.

**Steps.**
- Define the partition boundary: AXI-Lite control, ADC and DAC AXI-Stream data, trigger and interrupt signals, with
  decoupling (for example DFX Decoupler) and a reset of the reconfigurable module after loading.
- Set up the Vivado DFX flow in the build scripts (`proj.tcl`, `build_overlay.tcl`): partition definition,
  floorplanning (pblocks), a static checkpoint and one or more reconfigurable-module configurations, partial
  bitstreams plus `.hwh`.
- Load partial bitstreams from Python: PYNQ supports hierarchy partial reconfiguration
  (`DefaultHierarchy.download()`); verify this on PYNQ 4.0 and how it interacts with `MimoMtsOverlay` drivers.
- CI: build the static design once and reconfigurable modules separately.

**Done when** two LLRF variants can be swapped on hardware without losing MTS alignment.

## 6. Complete EPICS PV reference

**State.** `mimo_mts/ioc/PVs.md` documents only the LBL208 telemetry PVs (`pmbus:*`); its "RF control PVs" section is
`TODO`. The IOC creates about 230 PVs for an 8-ADC board (`$P` is the IOC prefix, e.g. `ALS_LLRF_LBL208`):

| Group | PVs | Created in |
|---|---|---|
| Time axes | `ADC:TWF`, `DSP:TWF` | `MimoMtsIoc.create_ioc()` |
| ADC waveforms | `ADC{n}:IWF`, `ADC{n}:QWF`, `DSP:ADC{n}:AWF`, `DSP:ADC{n}:PWF` | `create_ioc()` |
| RFDC mixers | `rfdc_mixer:{adc,dac}_mixer_nco_{freq_mhz,nyquist,phase}`, `rfdc_mixer:{ADC,DAC}{n}:nco_*`, each with `:RBV` | `add_mixer_pvs()` |
| RF control | `rf_control:<register>` and `:RBV` for the 21 registers in `axil_rf_control.json` | `add_rf_control_pvs()` |
| Pulse statistics | `DSP:ADC{n}:pulse_stat:{start_ns,end_ns,amp:mean,amp:std,phs:mean,phs:std}` | `add_pulse_pvs()` |
| Telemetry (LBL208) | `pmbus:*` (documented) | `AlsLlrfLBL208.add_pmbus_pvs()` |
| IOC statistics | standard `devIocStats` records under `<overlay>:ioc` | `start_ioc()` |
| ADC calibration | `adc_cal:*` (documented on the MR !37 branch) | `add_adc_cal_pvs()` |

**Steps.**
- Generate the reference from the code rather than by hand: create the records off-board with a stand-in overlay (no
  PYNQ hardware; `softioc` is in the development environment) and write them out with `softioc.builder.WriteRecords`,
  then render a table per group: name, record type, direction (setpoint / readback), units (`EGU`), limits,
  description. A small script (e.g. `mimo_mts/ioc/gen_pv_docs.py`) can be run in CI to flag a stale `PVs.md`.
- Give every record a `DESC` (40 characters max); take the register descriptions for `rf_control:*` from
  `axil_rf_control.json`. Fix the `dac_enable` description there, which reads "Pulse length" (copy-paste).
- Per-IOC differences: which PVs exist per IOC class and overlay (pmbus only on LBL208, channel counts per board).
- While there: `add_rf_control_pvs()` creates writable `longOut` PVs also for the read-only status registers
  (`rf_status`, `amp_measured`, `amp_loop_err`, `phs_measured`, `phs_loop_err`); create only the `:RBV` input for
  those (the JSON `access` field says which are read-only).
- Keep the hand-written parts (meaning, typical values, how to use) next to the generated tables, and update the
  Phoebus screens (`epics/*.bob`) if PV names change.

**Done when** `PVs.md` lists every PV of every IOC class and a check fails when the code and the document disagree.

## Related open work

- ADC interleaving calibration (MR !37): `AlsLlrfLBL208` now freezes, restarts the ADC tiles with the DAC disabled
  and restores. Verify on the LBL208 (step 15 with a muted restart, plus a carrier-phase sweep against 0.1°).
  Longer term: pilot-tone injection (one spare DAC, splitter, a coupler per phase-critical ADC) for training at boot.
- LBL208 analog front end: the ADC-to-RX-slice mapping is apparently reversed on the hardware (loopback on ADC7 is
  controlled by slice 4, attenuators 0/1, which `doc/lbl208/als_llrf_mts_ffe.ipynb` maps to ADC0). Verify all channels,
  fix the map, and add a per-ADC attenuation helper to `FrontendControl` (and IOC PVs) that uses the verified
  mapping, configurable per board.
- ADC calibration notebooks (`doc/zcu208/`, `doc/lbl208/adc_calibration.ipynb`) duplicate their helpers (capture with
  trigger-delay wait, spectrum, interleaving-spur levels, front-end attenuation); move them into a small module,
  e.g. `mimo_mts/utils/adc_cal_test.py`, once the procedure settles.

## References

- PYNQ changelog: https://github.com/Xilinx/PYNQ/blob/master/docs/source/changelog.rst
- RFSoC-PYNQ v4.0 (ZCU208 board support): https://github.com/Xilinx/RFSoC-PYNQ/pull/80
- PYNQ board images: https://www.pynq.io/
- cocotb releases: https://pypi.org/project/cocotb/
