# Development plan

Planned work beyond the current merge requests, in suggested order. Each item lists the current state, the goal, the
first steps and open questions. Update this file as items progress; repository conventions are in
[developer_guide.md](developer_guide.md).

| # | Item | Depends on | Size |
|---|---|---|---|
| 1 | Upgrade cocotb to 2.1 | – | small |
| 2 | 5 GSPS with a waveform generator per DAC channel — done (optional: DDR4-backed records) | – | large |
| 3 | LLRF logic in the MIMO overlays (closed-loop pulsed and CW) | 2 (DAC path) | medium |
| 4 | Upgrade to PYNQ 4.0 (Vivado 2025.2) | – | large |
| 5 | Partial reconfiguration of the LLRF logic | 3, 4 | large |
| 6 | Complete EPICS PV reference (`PVs.md`) — done | – | small |
| 7 | CW mode for `mimo_mts_5g` (per-DAC constant I/Q) — done | 2 (per-DAC AWG) | medium |
| 8 | `mimo_mts_5g` for the LBL208 | 2 | medium |
| 9 | Rerun the ADC calibration tests on ZCU208 and LBL208, update the findings | – (5 GSPS part: 8) | medium |
| 10 | `mimo_mts_iq` at 5 GSPS with `wave_gen` / `wave_cap` | 2 | medium |
| 11 | IOC capture reads without tearing (one-shot captures) — done | – | small |
| 12 | `mimo_mts_max`: DAC at 7 GSPS (MTS maximum) with per-DAC `wave_gen` | 2 | medium |
| 13 | NCO phase repeatability per DAC and ADC (MIMO phase coherence) | – | medium |
| 14 | `mimo_mts_5g`: common capture arm, `dac_enable` gating of the DAC outputs | 2 | small |

Next in line: the LBL208 port (8) and the IOC capture reads (11); item 9 can run in parallel on the existing overlays,
with its 5 GSPS part after item 8. The per-DAC AWG (2) and CW mode (7) are done (branch `feature/per-dac-cw`). Items 4 and 5 both change the Vivado flow; doing
the tool upgrade first avoids building the DFX flow twice. Item 6 is independent and can be done at any time; items 2, 3
and 5 add PVs, so generating the reference (below) pays off.

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

## 2. 5 GSPS with a waveform generator per DAC channel

**Goal.** This repository serves MIMO applications, so each DAC channel gets its own arbitrary waveform generator
(`wave_gen`), loaded independently and started by a common trigger, in `ZCU208/mimo_mts_5g` at 5 GSPS with ADC
capture and MTS working. The ADC capture path uses the same banked, address-mapped memory as the generator.

**State.**

- `wave_gen` core redesigned on branch `fix/axi-wave-gen` (design notes in [wave_gen.md](wave_gen.md)):
  address-mapped writes replace the gearbox, so writes of any size and order work, never stall and need no flush
  (the flush register is removed), and playback handles back-pressure. The CPU stall of `axi_wave_gen` had three
  causes, all reproduced in the testbench and fixed: reads were never answered, writes blocked while playback was
  stalled, and narrow CPU writes were stored as full beats. The `WaveGen` driver's memory view was 72 bytes off
  (fixed).
- `ZCU208/base` with `axil_wave_gen` (256-bit output, 100 MHz) meets timing and passes all 6 on-board checks of
  `mimo_mts/tests/test_wave_gen.py` (8 Nov 2026): bulk and shuffled 16/32-bit writes captured bit-exactly, no stall
  while rewriting during playback, CPU write rate 153.5 MB/s (results in [wave_gen.md](wave_gen.md)).
- `ZCU208/mimo_mts_5g` has **one** `axil_wave_gen` (320 bits at 250 MHz) → clock converter → width converter
  (160 bits at 500 MHz) → `axis_broadcaster_0` with 9 outputs: the 8 DACs and `hier_dac_cap`. All DACs play the
  same waveform.
- ADC side of `mimo_mts_5g`: 16 receivers (`receiver/mXY`), each RFDC stream 160 bits at 500 MHz → `axis_dwidth_converter`
  20 → 32 bytes at 500 MHz → clock converter → `adc_capture` and `axi_bram_ctrl` at 256 bits, 250 MHz. Two problems:
  the 20 → 32-byte converter is not an integer ratio and is the path that fails timing (below); and 256 bits ×
  250 MHz = 64 Gb/s is less than 160 bits × 500 MHz = 80 Gb/s, while the RFDC ignores `tready`, so long captures
  probably lose samples once the clock-converter FIFO is full (to verify: phase continuity of a captured tone).
- Resources: `mimo_mts_5g` uses 73 of 80 URAM (17 capture buffers of 4096 rows × 256 bits = 4 URAM, 5 for
  `wave_gen`) and 2 % of the block RAM. See the resource budget below.

`axil_wave_gen` uses its default 64-bit AXI4-Lite data width (`C_S_AXI_DATA_WIDTH` is not overridden). In `base` it
runs on the 100 MHz `pl_clk0` with a 256-bit output; in `mimo_mts_5g` the whole module, including its AXI-Lite slave,
runs on the 250 MHz stream clock with the 320-bit output.

5 GSPS also matters for ALS LLRF: at Fs = 10·f_ref = 4996.4 MSPS the RF-ADC interleaving products move 125 and
250 MHz away from the carrier instead of folding onto it at Fs = 8·f_ref, so the 0.1° phase requirement no longer
depends on the interleaving calibration (`doc/adc_calibration_findings.md`, "Alternative: sample at Fs = 10·f_ref").
A quick check on `mimo_mts_5g`: a tone at 3·Fs/5 should show those spurs and none on the tone.

**Resource budget (decided).** Every buffer becomes a banked 320-bit memory (5 banks × 64 bits): the 8 DAC
generators and the 16 ADC capture streams (8 ADCs, I and Q kept, R2C at decimation 1). `hier_dac_cap` is dropped:
each generator's memory can be read back. A URAM288 is 4096 × 72 bits, so a 64-bit bank costs one URAM at any depth
up to 4096 rows (5 URAM per memory); a BRAM36 bank costs 4 (2048 rows, as 2K × 18) or 8 (4096 rows). ZU48DR: 80 URAM,
1080 BRAM36.

| Layout (24 memories) | URAM | BRAM36 | |
|---|---|---|---|
| 4096 rows, all URAM | 120 | – | does not fit |
| 4096 rows, all BRAM | – | 960 (89 %) | not practical |
| 4096 rows, 15 in URAM + 9 in BRAM | 75 (94 %) | 360 (33 %) | URAM nearly full |
| **2048 rows: DAC generators in URAM, ADC captures in BRAM** | **40 (50 %)** | **320 (30 %)** | **chosen** |

2048 rows × 20 samples = 40,960 samples = **8.2 µs at 5 GSPS** per channel, for playback and for capture.
(Halving the depth saves no URAM; it halves the BRAM.)

Note on the timing failure: the only local `mimo_mts_5g` build (1 Aug, before the last design change on 4 Aug) fails
in the ADC receiver, not the waveform generator: `receiver/m32/axis_dwidth_converter_0` at 500 MHz, a high-fanout
clock enable with 89 % routing delay (WNS -0.057 ns, 54 endpoints).

**Steps.**

1. ~~**Hardware test in `ZCU208/base`**~~: done, 6/6 passed (8 Nov 2026).
2. **ADC capture with the banked memory** (the 5 → 4 direction of the same mapping). *RTL done* on branch
   `feature/banked-capture`: `banked_mem.v`, `axi4_mem_port.v`, `wave_cap.v`, `axi_wave_cap.v`, testbench 6/6,
   20 BRAM36 and WNS +1.42 ns at 250 MHz out of context. Remaining: the block design (below and step 3).
   Original plan:
   - Factor the memory out of `wave_gen.v` into `banked_mem.v`: the 5 × 64-bit banks, port A (AXI byte port:
     address-mapped writes with `WSTRB`, reads) and port B (one full row per cycle). `wave_gen` = `banked_mem` +
     playback control (port B read); the new capture core = `banked_mem` + capture control (port B write).
   - Capture core (e.g. `wave_cap.v`, AXI4 wrapper `axi_wave_cap.v`): replaces `adc_capture` + `blk_mem_gen` +
     `axi_bram_ctrl` in each `receiver/mXY`, with the same `trigger`, `n_rows` and `write_done` ports so the block
     design wiring stays. `RAM_STYLE = "block"`, BANK_DEPTH 2048.
   - In front of it: a 2:1 width converter at 500 MHz (20 → 40 bytes, an integer ratio) and the clock converter to
     250 MHz, replacing the 20 → 32-byte converter. 320 bits × 250 MHz carries the full 80 Gb/s.
   - AXI read side: the bus sees each capture as a flat int16 array in sample order (row r holds samples 20r to
     20r + 19), so `capture_adc_iq_buf()` keeps working with the new buffer length. Pipeline the read bursts in the
     AXI4 slave (today one beat per ~9 cycles) if DMA readout is wanted.
   - Testbench: stream rows in at full rate, trigger, read back over AXI with mixed sizes, compare.
3. **Rebuild `mimo_mts_5g`** with the new capture path and check timing with `designs/scripts/vivado_reports.py`.
   *Done 8 Nov 2026:* timing met (WNS +0.080 ns at 500 MHz; URAM 5, BRAM36 361.5, LUTs 59k) and verified on
   hardware: bit-exact DAC copy, gap-free 8.2 µs captures, capture IRQ, one-shot captures (details in
   [wave_gen.md](wave_gen.md)).
   Hardware test: MTS, captures of a tone without gaps, the generator played through the broadcaster, CPU
   responsive with the DAC stream stopped.
4. ~~**Per-DAC AWG**~~: *done 8 Nov 2026* (branch `feature/per-dac-cw`). Eight `axil_wave_gen` (`transmitter/dac0`
   … `dac7`, 4096 rows each, URAM 40 of 80) on interconnect M00–M07, a common trigger and a common CW apply from
   `axil_rf_control`; the broadcaster and `hier_dac_cap` are removed. Timing met (WNS +0.103 ns at 500 MHz, +0.197 ns
   at 250 MHz; BRAM36 333, LUTs 63k). `test_mimo5g.py --nco` 45/45 on hardware: DAC n's own tone on ADC n for all
   8 channels, CW phase steps within 0.06°, CW amplitude ratio 0.500, loop mode continuous across the wraps, ADC
   captures continuous within 0.4°. Driver, overlay and IOC: `ol.wave_gens`, `ol.write_dac_iq_buf_ch()`,
   `DAC{n}:IWF` / `DAC{n}:QWF` (see [wave_gen.md](wave_gen.md)). Original plan: one `wave_gen` per DAC (8 instances,
   URAM, BANK_DEPTH 2048), replacing the broadcaster
   and `hier_dac_cap`; a shared trigger and start-time alignment across channels; one
   control interface (per-channel `wave_length`, a common trigger/arm register) rather than eight AXI-Lite slaves if
   the interconnect gets large. Driver and IOC: `ol.wave_gens[ch]`, and per-channel waveform PVs `DAC{n}:IWF` /
   `DAC{n}:QWF` next to today's shared `DAC:IWF` / `DAC:QWF`. Design the control interface so the CW registers of
   item 7 fit in it.
5. ~~**Choose the bus flavour**~~: *chose `axil_wave_gen`* (eight AXI-Lite slaves fit the interconnect and timing).
   Options were `axil_wave_gen` (registers included, CPU writes) or `axi_wave_gen` (256-bit memory
   like `axi_bram_ctrl`, DMA bursts, read-back; needs a driver and separate control). Loading eight channels does not
   need DMA: 8 × 80 KB take about 4 ms at the measured 153.5 MB/s.
6. Optional: DDR4-backed playback or capture for longer records (as in `ZCU216/mimo_mts_ddr4`).

**Done when** `mimo_mts_5g` meets timing and plays an independent waveform on each of the 8 DACs at 5 GSPS, captures
all ADC channels without lost samples, with MTS working, and an IOC (or notebook) loads the waveforms without stalling
the CPU.

## 3. LLRF logic in the MIMO overlays (closed-loop pulsed and CW)

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

**Done** (branch `feature/pv-docs`). `doc/PVs.md` has usage notes per group and a reference generated from
the IOC code by `python -m mimo_mts.ioc.gen_pv_docs`: every IOC class is built off-board against a stand-in overlay,
its records written with softioc's `WriteRecords` and rendered as tables (channels collapsed to `ADC{n}`, a column for
the IOC classes that have each PV). The `pv_docs` CI job runs it with `--check`. Every record has a `DESC` and units;
the `rf_control:*` descriptions come from `axil_rf_control.json` (the `dac_enable` copy-paste fixed); read-only
registers have only `:RBV`; the 5 GSPS entry point now uses the existing 5 GSPS overlay configuration (it named one
that did not exist); both were later renamed to `mimo-5g-zcu208-ioc` and `MIMO_5G_ZCU208`. `--list <IOC class>` prints the full names for comparing with `dbl()` on the board.

The Phoebus screens (`epics/*.bob`) use none of the removed read-only setpoints. Open: compare `--list` with `dbl()`
from a running IOC.

## 7. CW mode for `mimo_mts_5g`

**Done 8 Nov 2026** (branch `feature/per-dac-cw`), as recommended below: `wave_gen` modes single / loop / CW, staged
`mode` and `cw_iq` registers applied by `ctrl.apply` or the common `cw_apply` (`axil_rf_control` `dac_enable` bit 2),
register map v2 with a `version` register, IOC PVs `DAC{n}:mode`, `DAC{n}:cw:amp`, `DAC{n}:cw:phase`, `DAC:apply`.
Verified on hardware with `test_mimo5g.py` (see item 2, step 4) and through the IOC with `test_ioc_dac.py` (34/34,
9 Nov 2026). Still open from item 6: compare `gen_pv_docs --list` with `dbl()`.

**Goal.** Continuous wave on every DAC with its own amplitude and phase, changed by software at any time and on all
channels at once, for MIMO measurements without reloading waveforms.

**Approach (recommended): per-DAC constant I/Q in the generator, carrier from the DAC NCO.** The RFDC fine mixer
already makes a phase-continuous carrier at the frequency set by `rfdc_mixer:*:rf_freq_mhz` (the NCO tone was flat to
0.2° over 8.2 µs on hardware); CW then only needs a constant baseband I/Q per DAC.
- Add a CW mode to each per-DAC generator: instead of reading the memory it streams one I/Q pair from registers,
  repeated in every 320-bit row (10 I/Q pairs per row at the 2.5 GSPS complex rate), so no memory write is needed
  and the waveform memory keeps its pulse for the other mode.
- Double-buffer the I/Q registers and apply them with one common strobe, so all DACs change amplitude and phase on
  the same clock (MIMO phase coherence); switching between CW and playback takes effect on the trigger or the
  strobe, not mid-row.
- IOC: per-DAC `DAC{n}:cw:amp` (fraction of full scale) and `DAC{n}:cw:phase` (degrees) converted to I/Q, a mode PV
  (playback / CW), and an "apply" PV.
- Also add a loop mode to the generator (play `wave_length` rows repeatedly): periodic waveforms such as multitone
  without the CPU (what the `wave_length = 0` bug did by accident, made explicit with a control bit).

**Alternatives considered.** Writing a constant waveform into the memory works today but rewrites 80 KB per change
and cannot update channels together. A separate I/Q mux in front of each DAC duplicates the generator's control
logic. Closed-loop CW (amplitude/phase feedback) is item 3.

**Done when** each DAC holds its own CW amplitude and phase on hardware, updated on all channels on the same clock
(checked with the loopback captures), and the IOC exposes it.

## 8. `mimo_mts_5g` for the LBL208

**Goal.** The 5 GSPS MIMO overlay with banked captures and per-DAC AWG on the LBL208, as on the ZCU208.

**Steps.**
- `designs/LBL208/mimo_mts_5g` from the ZCU208 design: LBL208 pin constraints (`.xdc` from `LBL208/mimo_mts`),
  CLK104A device tree, the analog front end (`frontend_control_axi`: RX attenuators and power), EVR if wanted.
- `MIMO_5G_LBL208` in `config.py` (CLK104A TCS files for 5 GHz), an IOC class and entry point, the PV reference
  regenerated.
- Hardware check with `test_mimo5g.py` and `doc/lbl208/mimo_mts_5g.ipynb` (loopback through the front end; mind the
  reversed ADC-to-slice mapping, see Related open work).

**Done when** the LBL208 passes the same checks as the ZCU208 (bit-exact DAC copy, gap-free captures, alignment).

## 9. Rerun the ADC calibration tests on ZCU208 and LBL208

**Goal.** Close the open hardware questions of `doc/adc_calibration_findings.md` and measure the 5 GSPS case.

**Steps.**
- 4 GSPS (ALS overlays), both boards: repeat `adc_calibration.ipynb` step 15 with the DAC disabled during
  `restart_adc_tiles()` (the boot sequence now in `AlsLlrfLBL208`), and sweep the carrier phase to measure the peak
  phase error against the 0.1° requirement. Check the boot sequence through the IOC (`adc_cal:status`).
- 5 GSPS (`mimo_mts_5g`, ZCU208 then LBL208): confirm that at Fs = 10·f_ref the interleaving products sit 125 and
  250 MHz from a 3·Fs/5 tone and none on it; measure SFDR untrained, trained and frozen. The banked captures (8.2 µs,
  one-shot) and the RF-frequency PVs make this a notebook job.
- Move the helpers duplicated between the calibration notebooks (capture with trigger wait, spectrum, interleaving
  spur levels, front-end attenuation) into `mimo_mts/utils/adc_cal_test.py` first.
- Update `doc/adc_calibration_findings.md`: boot-policy results against 0.1°, the 5 GSPS spur positions, and what
  remains (pilot tone).

**Done when** the findings document answers the 0.1° question for the ALS boot sequence and shows the 5 GSPS spur
positions on both boards.

## 10. `mimo_mts_iq` at 5 GSPS with `wave_gen` / `wave_cap`

**State.** `ZCU208/mimo_mts_iq` runs at 4 GSPS with the older data path: `dac_streamer` from a BRAM player and 9
`adc_capture` + `axi_bram_ctrl` captures (`MIMO_IQ_ZCU208` in `config.py`).

**Goal.** The same sampling scheme and data path as `mimo_mts_5g`: 5 GSPS, the waveform generator (per DAC once item 2
step 4 is done) and banked captures (`axi_wave_cap`, 2:1 width conversion to 320 bits at 250 MHz), with the capture
interrupt and one-shot captures.

**Steps.**
- Decide what stays specific to `mimo_mts_iq` (its I/Q stream arrangement, decimation and mixer modes) and what
  follows `mimo_mts_5g`; then migrate the block design with a script as for `mimo_mts_5g` (replace `adc_capture` +
  `blk_mem_gen` + `axi_bram_ctrl` by `axi_wave_cap`, the player by `wave_gen`), re-export with `write_bd_tcl`.
- `MIMO_IQ_ZCU208` at 5 GSPS (CLK104 5 GHz TCS files), PV reference regenerated.
- Hardware check with `test_mimo5g.py` (or a variant) and a notebook like `doc/zcu208/mimo_mts_5g.ipynb`.

**Done when** `mimo_mts_iq` passes the same hardware checks as `mimo_mts_5g`.

## 11. IOC capture reads without tearing

**State.** `MimoMtsIoc.update_adc_bufs` copies the ADC capture buffers while the captures keep running. A trigger
during the copy overwrites a buffer half read, so a waveform PV can mix two captures; on `mimo_mts_5g` this showed in
`test_mimo5g.py` as a phase step when the tone phase changed between triggers (loop mode, 67.5° per 0.1 s trigger).

**Goal.** On bitstreams with the `axi_wave_cap` control registers, read captures in one-shot mode: arm, wait for done
(the capture-done interrupt or `ol.wait_captures()`), read, re-arm, as `test_mimo5g.py` (`Mimo5gCheck.capture`) and
`doc/zcu208/mimo_mts_5g.ipynb` do. Older bitstreams keep the free-running read.

**Implemented** (branch `feature/ioc-oneshot`): `MimoMtsIoc.init_capture_mode()` puts the captures in one-shot mode
where the overlay has the control registers (`ol.has_capture_csrs`); the capture-done interrupt handler waits until
all captures are done, reads them and re-arms (`read_captures()`); a watchdog in the 0.5 s register loop reads and
re-arms if an interrupt was missed. Older overlays keep the free-running read. `test_ioc_dac.py` checks it: at a 1 ms
trigger with the ADC mixer 0.3 MHz off the DAC mixer, every capture must be a straight phase ramp.

**Done when** the IOC waveform PVs never mix captures on `mimo_mts_5g` (`test_ioc_dac.py`, capture-read check).
*Verified 9 Nov 2026:* with the free-running IOC all 96 reads (12 × 8 ADCs, 1 ms trigger) had a phase jump (worst
195°); with one-shot reads none (worst deviation from the ramp 0.33°). The IOC re-arms about 45 ms after a capture
completes. Remaining race: the 16 captures (I and Q of 8 ADCs) are armed by 16 separate register writes, so a trigger
during the arming splits them over two triggers (one of 96 reads at a 1 ms trigger had I and Q of one ADC from
different triggers). A common arm in hardware removes it (item 14).

## 12. `mimo_mts_max`: DAC at 7 GSPS

**State.** An earlier `ZCU208/mimo_mts_max` overlay ran the DACs at 7 GSPS, the highest rate tested with MTS, and MTS
worked with it, but its design files were never committed. What remains: the `MIMO_MAX_ZCU208` entry in `config.py`
(DAC 7 GSPS with `LMX2594_7G.tcs`, ADC 5 GSPS, interpolation 2, DAC MTS target latency 476) and the TCS file.

**Goal.** `mimo_mts_5g` with the DACs at 7 GSPS. The ALS 3 GHz carrier is then in the first Nyquist zone of the DACs
and is their strongest output: sinc loss about −2.8 dB, image at 4 GHz. At 5 GSPS the carrier is in the second zone
(about −5.9 dB in normal mode), and the 2 GHz zone-1 image is stronger than the carrier. The ADCs stay at 5 GSPS,
their maximum, so the ADC side is unchanged.

**Sizing.** Interpolation 2: 3.5 GSPS complex per DAC, so 14 int16 (7 I/Q pairs, 224 bits) per 500 MHz RFDC cycle
and 28 samples (448 bits) per 250 MHz `wave_gen` row, against 10 and 20 at 5 GSPS. The fabric clocks (500 and
250 MHz), the 2:1 DAC width converter and the 2.5 MHz SYSREF (7000 / 2.5 = 2800) carry over. Memory: 7 URAM banks
per DAC, 56 of 80 URAM for 8 DACs, 224 KB per DAC, still 4096 rows = 16.4 µs; a 448-bit row still fits the 256 KB
window per generator (`C_S_AXI_ADDR_WIDTH` 18), so the address map is the same.

**Steps.**
1. Testbench `axil_wave_gen` with `OUT_DATA_WIDTH = 448`: 7 banks (`banked_mem` reciprocal divide by 7), CW repeated
   14 times per row, loop mode.
2. Copy `designs/ZCU208/mimo_mts_5g` to `designs/ZCU208/mimo_mts_max` (Makefile, `.tcl`, `.xdc`, design name).
3. RFDC DAC tiles: 7 GSPS, reference clock 7000 MHz, `DAC_Data_Width` 14 at 500 MHz fabric. First risk: check that
   the RFDC IP accepts 14 samples per cycle for I/Q at interpolation 2.
4. `transmitter/dac0` … `dac7`: `OUT_DATA_WIDTH` 448, clock converter 56 bytes, width converter 56 → 28 bytes,
   register slice 28 bytes; re-export with `write_bd_tcl`.
5. Build: timing on the wider 500 MHz DAC paths, resources (URAM 56).
6. Software: `MIMO_MAX_ZCU208` gets `"verify": True` for the CLK104; IOC class and entry point (`mimo-max-zcu208-ioc`),
   `gen_pv_docs` (`PER_DAC_GENERATORS`), `PVs.md`; notebooks use `out_data_width // 32` I/Q pairs per row instead
   of 10. `test_mimo5g.py` and the RF-frequency PVs already handle different ADC and DAC rates.
7. Hardware: re-measure the DAC MTS latency (replace 476) and check it over reboots;
   `test_mimo5g.py --config MIMO_MAX_ZCU208 --nco`; a 3 GHz CW (DAC zone 1, ADC zone 2): level and image.
8. `wave_gen.md`, this plan, the CI synthesis matrix.

**Done when** `mimo_mts_max` meets timing, MTS locks with a repeatable latency, and `test_mimo5g.py` passes on
hardware with the DACs at 7 GSPS.

## 13. NCO phase repeatability per DAC and ADC

**State.** The RFDC fine mixers make the carrier (CW mode, `rfdc_mixer:*:rf_freq_mhz`). The overlay already updates
them on a SYSREF-timed event: `set_{adc,dac}_mixer` and `set_{adc,dac}_mixer_ch` set `EventSource =
EVNT_SRC_SYSREF`, call `ResetNCOPhase()` on each block and enable SYSREF in the MTS configuration around the update.
That should make the phases repeatable within a session; what remains to check is whether they also repeat when only
one side changes, after an IOC restart and after a reboot (new MTS). Within one setting the phase is
stable: `test_ioc_dac.py` measured the CW phase constant to 0.03° within and between captures. In the manual IOC test
the per-channel phases differed by up to 130° with identical CW settings, more than cables and channels explain
(10–110 ps, under 8° at 200 MHz). For MIMO phase coherence the per-DAC phase must be repeatable.
First data point (8 Nov 2026, `test_ioc_dac.py`): after setting both DAC and ADC mixers to 0 MHz and back to 200 MHz,
the per-ADC phases repeated to 0.0° on all 8 channels. Still open: changing only one side, IOC restarts, reboots.

**Goal.** DAC and ADC NCO phases repeatable after a frequency change, an IOC restart and a reboot (MTS), to the 0.1°
level ALS needs, or a documented calibration step that restores them.

**Steps.**
1. Measure: `test_ioc_dac.py` reports the per-ADC phase change after setting both mixers to 0 and back. Separate the
   DAC and ADC sides by changing only one of them; repeat several times; repeat across IOC restarts and reboots.
2. If not repeatable across restarts or reboots: find what differs (SYSREF edge used for the update, MTS latency,
   LMX/LMK phase after a reboot) and either fix it or calibrate the per-channel phase at startup.
3. Repeat step 1; add a pass/fail check to `test_ioc_dac.py` once the target is met.

**Done when** the per-DAC and per-ADC carrier phases repeat to 0.1° after frequency changes, IOC restarts and reboots
on the ZCU208 (and the LBL208, item 8), or the remaining offset is calibrated automatically.

## 14. `mimo_mts_5g`: common capture arm and DAC enable

**State.** Two gaps between `mimo_mts_5g` and the earlier overlays, found with the IOC test and the Phoebus screens:
- One-shot captures are armed one register write per capture (16 writes); a trigger in between splits the set over
  two triggers (item 11).
- `rf_control:dac_enable` bit 0 does not reach the DAC outputs (`transmitter/enable` is unconnected); on `mimo_mts`
  it gated `dac_streamer`. Bit 1 (`pulse_enable`) is not connected on either overlay.

**Steps.**
1. Common arm: an `arm` input on `axi_wave_cap` / `wave_cap`, driven by a one-cycle pulse from an `axil_rf_control`
   register bit (as `cw_apply` drives the generators), so one write arms all captures on the same clock. Software:
   `arm_captures()` uses it when present (version or register check), keeps the per-capture writes otherwise.
2. DAC enable: an `enable` input on `axis_idle_zero` (output zero while low), connected to `dac_enable`.
3. Testbenches, block design (`write_bd_tcl`), rebuild, `test_mimo5g.py` and `test_ioc_dac.py` on hardware.

The capture length stays the full capture memory (a constant at least the capture depth: now 4096, clamped to the
2048 rows), not `rf_control:pulse_length`: every capture fills the whole memory, so cable delay and latency never cut
off the end of a waveform. The capture depth stays 2048 rows (8.2 µs, 320 BRAM36 for the 16 streams) rather than
matching the 16.4 µs DAC memory: the remaining block RAM is reserved for the LLRF DSP's long decimated waveforms.

Also from the IOC side: the IOCs boot with `dac_enable` bit 0 cleared, and the `mimo_mts_5g` IOC starts with a zero
waveform until `dac_enable` gates its outputs.

**Done when** `test_ioc_dac.py` passes its capture-read check repeatedly at a 1 ms trigger and `dac_enable` = 0
silences all DACs.

## Related open work

- ADC calibration, longer term: pilot-tone injection (one spare DAC, splitter, a coupler per phase-critical ADC)
  for training at boot (item 9 covers the reruns).
- LBL208 analog front end: the ADC-to-RX-slice mapping is apparently reversed on the hardware (loopback on ADC7 is
  controlled by slice 4, attenuators 0/1, which `doc/lbl208/als_llrf_mts_ffe.ipynb` maps to ADC0). Verify all channels,
  fix the map, and add a per-ADC attenuation helper to `FrontendControl` (and IOC PVs) that uses the verified
  mapping, configurable per board.

## References

- PYNQ changelog: https://github.com/Xilinx/PYNQ/blob/master/docs/source/changelog.rst
- RFSoC-PYNQ v4.0 (ZCU208 board support): https://github.com/Xilinx/RFSoC-PYNQ/pull/80
- PYNQ board images: https://www.pynq.io/
- cocotb releases: https://pypi.org/project/cocotb/
