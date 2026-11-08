# Development plan

Planned work beyond the current merge requests, in suggested order. Each item lists the current state, the goal, the
first steps and open questions. Update this file as items progress; repository conventions are in
[developer_guide.md](developer_guide.md).

| # | Item | Depends on | Size |
|---|---|---|---|
| 1 | Upgrade cocotb to 2.1 | – | small |
| 2 | 5 GSPS with a waveform generator per DAC channel | – | large |
| 3 | LLRF logic in the MIMO overlays, CW mode | 2 (DAC path) | medium |
| 4 | Upgrade to PYNQ 4.0 (Vivado 2025.2) | – | large |
| 5 | Partial reconfiguration of the LLRF logic | 3, 4 | large |
| 6 | Complete EPICS PV reference (`PVs.md`) — done | – | small |

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
2. **ADC capture with the banked memory** (the 5 → 4 direction of the same mapping):
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
   Hardware test: MTS, captures of a tone without gaps, the generator played through the broadcaster, CPU
   responsive with the DAC stream stopped.
4. **Per-channel generators**: one `wave_gen` per DAC (8 instances, URAM, BANK_DEPTH 2048), replacing the broadcaster
   and `hier_dac_cap`; a shared trigger and start-time alignment across channels; one
   control interface (per-channel `wave_length`, a common trigger/arm register) rather than eight AXI-Lite slaves if
   the interconnect gets large. Driver and IOC: `ol.wave_gens[ch]`, and per-channel waveform PVs `DAC{n}:IWF` /
   `DAC{n}:QWF` next to today's shared `DAC:IWF` / `DAC:QWF`.
5. **Choose the bus flavour**: `axil_wave_gen` (registers included, CPU writes) or `axi_wave_gen` (256-bit memory
   like `axi_bram_ctrl`, DMA bursts, read-back; needs a driver and separate control). Loading eight channels does not
   need DMA: 8 × 80 KB take about 4 ms at the measured 153.5 MB/s.
6. Optional: DDR4-backed playback or capture for longer records (as in `ZCU216/mimo_mts_ddr4`).

**Done when** `mimo_mts_5g` meets timing and plays an independent waveform on each of the 8 DACs at 5 GSPS, captures
all ADC channels without lost samples, with MTS working, and an IOC (or notebook) loads the waveforms without stalling
the CPU.

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

**Done** (branch `feature/pv-docs`). `doc/PVs.md` has usage notes per group and a reference generated from
the IOC code by `python -m mimo_mts.ioc.gen_pv_docs`: every IOC class is built off-board against a stand-in overlay,
its records written with softioc's `WriteRecords` and rendered as tables (channels collapsed to `ADC{n}`, a column for
the IOC classes that have each PV). The `pv_docs` CI job runs it with `--check`. Every record has a `DESC` and units;
the `rf_control:*` descriptions come from `axil_rf_control.json` (the `dac_enable` copy-paste fixed); read-only
registers have only `:RBV`; the `mimo5g-zcu208-ioc` entry point now uses the `MIMO5G_ZCU208` overlay (it named a
configuration that did not exist). `--list <IOC class>` prints the full names for comparing with `dbl()` on the board.

The Phoebus screens (`epics/*.bob`) use none of the removed read-only setpoints. Open: compare `--list` with `dbl()`
from a running IOC.

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
