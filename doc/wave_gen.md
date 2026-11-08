# Waveform generator and capture (`wave_gen`, `wave_cap`)

Design notes for the arbitrary-waveform DAC source and the matching ADC capture, which share one banked memory.
Modules in `designs/ip/rtl/`:

| Module | Role |
|---|---|
| `banked_mem.v` | the banks; port A: bus side, byte addressed, address-mapped writes (with strobes) and reads; port B: one row per clock, read or write |
| `axi4_mem_port.v` | AXI4 memory slave (INCR/FIXED/WRAP bursts, narrow transfers, reads) driving port A |
| `wave_gen.v` | `banked_mem` + playback (port B reads rows to `m_axis`) |
| `wave_cap.v` | `banked_mem` + capture (port B writes rows from `s_axis`) |
| `axi_wave_gen.v`, `axi_wave_cap.v` | `axi4_mem_port` + core |
| `axil_wave_gen.v` | AXI4-Lite wrapper with control registers + `wave_gen` |

Testbenches: `designs/ip/tb/axi_wave_gen`, `axil_wave_gen`, `axi_wave_cap`.

## Widths and clocks

The RFDC data interface runs at 500 MHz from the LMK and carries 10 samples per clock (160 bits of 16-bit samples) at
5 GSPS. The DSP and the waveform generator run at `dsp_clk` = 250 MHz, so the generator's output is twice as wide:
**OUT_DATA_WIDTH = 320 bits = 20 samples** per clock, converted to 160 bits at 500 MHz by the AXI-Stream width and
clock converters in the block design.

The PS writes the waveform over AXI, whose data widths are powers of two. The PS master port `M_AXI_HPM0_FPD` is
128 bits in all overlays (`PSU__MAXIGP0__DATA_WIDTH`); the memory slaves behind `rf_interconnect` are 256 bits
(`axi_bram_ctrl` in `mimo_mts`, `axi_wave_gen` in `mimo_mts_5g`), so the interconnect inserts a 128→256 upsizer.
The CPU writes at most 16 bytes per transaction (device memory, no write combining), so every CPU write arrives as a
single beat with partial `WSTRB`. Only a DMA writing through HPM0 produces bursts, of 128-bit beats that the upsizer
may pack into 256-bit beats.

So the generator has to bridge a power-of-two bus (64, 128 or 256 bits) and a 320-bit output, and accept writes of
any size and order.

## Memory organization

The memory is `NUM_BANKS = OUT_DATA_WIDTH / GRANULE` banks (5 with the defaults), each `GRANULE` = 64 bits wide and
`BANK_DEPTH` rows deep. Output word r, one AXI-Stream beat, is row r of all banks, read in parallel:

```
              bank0      bank1      bank2      bank3      bank4
output word 0: G0         G1         G2         G3         G4        ← 320 bits, samples 0..19
output word 1: G5         G6         G7         G8         G9        ← samples 20..39
output word r: G5r ...                                    G5r+4
```

The bus side sees the waveform as a flat byte array in output order: DAC sample n (int16) is at byte 2n, and
granule G (bytes 8G to 8G+7, samples 4G to 4G+3) lives at

> **bank = G mod NUM_BANKS, row = G div NUM_BANKS.**

## Width conversion by address mapping

A bus beat carries `AXI_GRANULES = AXI_DATA_WIDTH / GRANULE` consecutive granules (4 for 256 bits). Consecutive
granules fall into distinct banks as long as `AXI_GRANULES <= NUM_BANKS`, so a beat writes its lanes into different
banks, in rows r and r+1, in one cycle:

| Beat (byte address) | Granules | (bank, row) |
|---|---|---|
| 0 | G0 G1 G2 G3 | (0,0) (1,0) (2,0) (3,0) |
| 32 | G4 G5 G6 G7 | (4,0) (0,1) (1,1) (2,1) |
| 64 | G8 G9 G10 G11 | (3,1) (4,1) (0,2) (1,2) |

The width conversion is done by where each granule is written, not by when; there is no gearbox. `WSTRB` becomes the
byte write enables of the banks, so a 16-byte store at byte 16 writes G2 and G3 (banks 2 and 3, row 0) and nothing
else. Writes need no particular order, never wait, and need no flush.

An earlier version used a gearbox: a shift register that collected 256-bit beats and wrote a 320-bit row once it had
enough data. It required complete beats in strict order starting at address 0 and a flush at the end, and it stalled
the bus while the waveform played (see "History").

## Hardware

Memory port (bank port A, bus side), one request per cycle, pipelined:

| Stage | Work |
|---|---|
| s1 | register the request; granule index of the beat-aligned address, G0 = (addr >> log2(AXI_BYTES)) · AXI_GRANULES |
| s2 | row0 = G0 div NUM_BANKS as a multiply by a reciprocal: (G0 · RECIP) >> RECIP_SHIFT, exact for all G0 (one DSP) |
| s3 | bank0 = G0 − row0 · NUM_BANKS, the bank of lane 0 |
| s4 | per bank b: lane = (b − bank0) mod NUM_BANKS, row = row0 + (b < bank0); write enables = `WSTRB` bytes of that lane if lane < AXI_GRANULES and row < BANK_DEPTH; data = 64-bit lane mux |
| s5, s6 | RAM access and output register (reads) |
| s7 | reads: lane l of the beat = bank (bank0 + l) mod NUM_BANKS |

Reciprocal division: with x < 2^W, S = W + ⌈log2 N⌉ and M = ⌊2^S / N⌋ + 1, x div N = (x · M) >> S for every x.
The divide happens once per request, so it costs one DSP and pipeline latency, not throughput.

Implementation (`axi_wave_gen`, 256 → 320 bits, BANK_DEPTH 4096, xczu48dr-2, out of context, placed and routed at
250 MHz): 5 URAM, 1 DSP, about 1030 LUTs and 2230 registers; WNS +1.76 ns, worst path the read-data register enable
(mostly routing), not the RAM or the divider.

Requests are processed in order, so a read after a write returns the new data (read latency 7 cycles). Port A uses
the URAM/BRAM byte-write, no-change template.

Playback (bank port B): on `trigger` (ignored while playing), rows 0 to `wave_length` − 1 stream out on `m_axis`
(`wave_length` = 0 plays all `BANK_DEPTH` rows), with `tlast` on the last row. The RAM read, data pipeline and
valid/last pipeline all advance only when the output is accepted, so back-pressure is handled. Writes during playback
are accepted and change the rows not yet read. `busy` = playback running.

Parameter rules (checked at elaboration): `AXI_DATA_WIDTH` ≤ `OUT_DATA_WIDTH` (one lane per bank per beat);
`AXI_DATA_WIDTH / GRANULE` a power of two; `GRANULE` a multiple of 8; `BANK_DEPTH` a power of two. A 512-bit bus
with a 320-bit output would need two write ports per bank and is not supported.

## Wrappers

**`axi_wave_gen`** (full AXI4 slave, `s_axi`; control through ports `ctrl_trigger`, `ctrl_wave_length`,
`ctrl_busy`): behaves like a memory, as `axi_bram_ctrl` does. It supports INCR, FIXED and WRAP bursts,
narrow and unaligned transfers and `WSTRB`, and reads return the stored data. It handles one transaction at a time,
writes first, at one write beat per clock; reads take about 9 clocks per beat (read-back is for checking, not speed).
All responses are OKAY: an error response to a CPU store raises an asynchronous SError on the A53.

**`axil_wave_gen`** (AXI4-Lite, 64-bit, PYNQ driver `mimo_mts/drivers/wave_gen.py`): registers `ctrl` (0x00:
bit 0 trigger, bit 1 reserved (was flush), bit 2 trigger_mode), `wave_length` (0x08), `status` (0x10: busy); waveform memory from 0x18
(`waveform_data` in `axil_wave_gen.json`). Waveform reads are not implemented here and return a register value.

Both wrappers complete every write in a bounded time, whatever the state of playback or of the downstream stream.

## Using it from software

1. Write the samples as an int16 array at the waveform base address, any order and any write size (the PYNQ driver
   exposes `wave_mem`).
2. Set `wave_length` in output words (20 samples each with the 320-bit output).
3. Trigger (register or external trigger input).

No flush is needed: the flush register, port and driver methods were removed with the gearbox. `wait_idle()` waits
until playback has finished (with a timeout).

## Hardware test

`mimo_mts/tests/test_wave_gen.py` on a ZCU208 with the `base` overlay (`axil_wave_gen`, 64-bit AXI4-Lite, 256-bit
output, 100 MHz), 8 November 2026. The generator output is captured by `adc_capture` on the same trigger and compared
bit-exactly; all 6 checks pass:

| Check | Result |
|---|---|
| Bulk numpy write (`wave_mem[:] = …`), 200 rows | exact; waveform starts at capture row 3 (generator latency) |
| 16-bit stores in random order | exact |
| 32-bit stores in random order | exact |
| Rewriting the waveform for 2 s while it plays every 10 µs | 127,673 writes of up to 512 B, slowest 173 µs (no stall) |
| Waveform after those writes | exact |
| Full-memory write, 128 KiB | 0.9 ms, 153.5 MB/s |

At that rate, 8 channels × 80 KB (2048 rows of 320 bits) load in about 4 ms, so CPU writes are fast enough and DMA is
not needed for loading. Not covered by `base`: the stalled-stream case (`adc_capture` always accepts data) and the
4-to-5 lane mapping (64-bit bus, 256-bit output); both are covered by the testbenches and remain to be seen on
`mimo_mts_5g`.

## Hardware test on `mimo_mts_5g`

ZCU208 with 8 DAC-to-ADC loopback cables, `mimo_mts_5g` with all 17 captures on `axi_wave_cap` (8 November 2026,
`mimo_mts/tests/test_mimo5g.py` and `doc/zcu208/mimo_mts_5g.ipynb`):

- DAC copy (generator → 160-bit broadcast stream → 2:1 converter → `axi_wave_cap`) bit-exact from row 0, i.e. from
  the trigger; capture-done interrupt every trigger (0.1 s).
- ADC captures gap-free: phase continuity of a 200 MHz tone within 0.2–0.3° over the full 8.2 µs on all 8 channels,
  with the tone from the DAC NCO and from the generator.
- Loopback latency 205.6 ns on all channels; carrier-phase skew vs ADC0 −10 to −45 ps (ADC7 −110 ps), repeatable to
  ≤0.7 ps over captures and identical between two bitstreams (cables and channels).
- No CPU stall while rewriting the waveform during playback (slowest write 87 µs); capture counters one per trigger;
  generator busy 0.02 % of the time (16.4 µs per 0.1 s trigger). `test_mimo5g.py --repeat 3 --nco`: 52/52 passed.

The first builds showed a phase step in half the captures and random DAC-capture offsets. The debug status added to
`axil_wave_gen` (tready, tvalid, play row) traced it to the `wave_length = 0` bug below, not to the stream or the
captures.

## ADC capture (`wave_cap`)

The 5 GSPS ADC path has the mirror-image problem: the RFDC delivers 160 bits at 500 MHz, and the CPU reads through a
power-of-two AXI port. `mimo_mts_5g` converts 20 → 32 bytes in an `axis_dwidth_converter` at 500 MHz, a non-integer
ratio that fails timing, and then captures 256 bits at 250 MHz (64 Gb/s), less than the 80 Gb/s from the ADC.

`wave_cap` uses the same banked memory in the other direction. The stream is converted 2:1 to 320 bits at 250 MHz
(an integer ratio, exactly 80 Gb/s) in front of it; each valid beat is written as one row to all five banks at once
(port B), and the CPU reads the capture as a flat int16 array in sample order through the address mapping (port A),
row r holding samples 20r to 20r + 19.

Capture control, as `adc_capture` (same `axis_clk`, `axis_aresetn`, `s_axis`, `trigger`, `n_rows`, `write_done` ports in
`axi_wave_cap`): on `trigger` (ignored while capturing) the next min(`n_rows`, DEPTH) valid beats go to rows 0, 1, …;
`write_done` pulses after the last row; `n_rows` = 0 ignores the trigger; `s_axis_tready` is always 1. The first row
is the beat one clock after the trigger. Unlike `adc_capture`, which advanced the address on every clock of its
window, the row address advances only on valid beats, so a gap in `tvalid` leaves no hole (a testbench mutant of the
old behaviour fails `test_capture_with_gaps`).

Implementation (`axi_wave_cap`, 320-bit rows, DEPTH 2048, `RAM_STYLE = "block"`, xczu48dr-2, out of context, placed
and routed at 250 MHz): 20 BRAM36, 1 DSP, about 1070 LUTs and 1900 registers; WNS +1.42 ns, worst path the row
counter fanning out to the BRAM address pins (routing only; register it per bank if it gets tight in the overlay).

In `mimo_mts_5g` (8 Nov 2026) all 17 capture paths (16 ADC streams and `hier_dac_cap`) use `axi_wave_cap` with
`RAM_STYLE = "block"` and DEPTH 2048 (8.2 µs at 5 GSPS), replacing `adc_capture` + `blk_mem_gen` + `axi_bram_ctrl`,
with a 20 → 40-byte converter in front. The overlay meets timing (WNS +0.072 ns at 500 MHz, +0.141 ns at 250 MHz;
the 1 Aug build failed by −0.057 ns in a receiver converter): URAM 73 → 5, BRAM36 21.5 → 361.5, LUTs 95k → 57k. The
tightest path is now the DAC broadcaster's register slice driving a DAC tile across the die, which the per-channel
generators remove. On-board check: `mimo_mts/tests/test_mimo5g.py`.

## History: why the gearbox core hung the PS

Found while troubleshooting the CPU stall of `axi_wave_gen` in `mimo_mts_5g` (November 2026), all reproduced in the
testbench before the redesign:

1. **Reads never completed.** `axi_wave_gen` tied `ARREADY` to 0 and never drove `RVALID`. The PS has no AXI timeout,
   so any read of the range (an `mmio.read`, a register dump) hung the CPU.
2. **Writes blocked during playback.** The core held its write-ready low while playing; if `m_axis_tready` stayed
   low (DAC path in reset), the first trigger left playback running forever and every later write hung the CPU. This
   affected `axil_wave_gen` too.
3. **CPU writes were corrupted.** The core ignored `WSTRB` and the address (except address 0) and counted every beat
   as full width, so 16-byte CPU stores through the 256-bit slave stored garbage. In the January block design,
   `ctrl_flush` was also tied to `enable`, flushing a partial row after every beat.
4. **Back-pressure corrupted playback.** The RAM read and data pipeline advanced every cycle while the valid pipeline
   held, so data and valid slipped apart whenever `m_axis_tready` dropped.

5. **`wave_length = 0` played forever** (found on `mimo_mts_5g`, November 2026, in the redesigned core too).
   `rd_addr == rd_length - 1` is evaluated at 32 bits, so 0 − 1 is 0xFFFFFFFF and the 12-bit row address never
   matches: the generator looped over the memory, kept `busy` set and ignored triggers. Symptoms: captures starting
   at random rows, and a phase step at every wrap of a tone that is not periodic in the memory. Fixed by a last-row
   index at the row-address width (`test_wave_length_zero_plays_full_depth_once`).

Testbench cases for each: `test_read_completes`, `test_write_completes_while_stream_stalled`,
`test_cpu_style_narrow_writes` (`axi_wave_gen`), `test_32bit_writes_shuffled` (`axil_wave_gen`) and
`test_random_order_sizes_readback_backpressure`.
