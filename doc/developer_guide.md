# Developer guide

Orientation for anyone working on this repository, human or AI coding agent: how the code is organized, how to build,
lint and test it, and the non-obvious constraints. The user-facing setup (flashing the SD card, installing on the
board, running the IOCs) is in the top-level `README.md`.

## Project

RFSoC MIMO / ALS LLRF controller firmware and software for three boards (ZCU208, LBL208, ZCU216). It has two halves:
Vivado/PYNQ **overlay designs** (`designs/`) and the **PYNQ Python package and EPICS soft IOCs** (`mimo_mts/`) that
run on the board. `bedrock/` is a git submodule (BerkeleyLab/Bedrock) providing RTL and CORDIC sources; clone with
`--recursive`.

## Commands

Python environment: `pip install -e .` (pins ruff, cocotb, pynq, softioc, etc.). Hardware-only packages (pynq,
xrfdc, xrfclk, softioc on the board) mean `mimo_mts` generally cannot run off-board.

```bash
# Lint / format (CI enforces both; the pre-commit hook runs the same on mimo_mts/ and designs/)
ruff check mimo_mts designs
ruff format mimo_mts designs        # line length 120, rules E,F,W,I,B,UP (pyproject.toml [tool.ruff])

# RTL simulation (cocotb + Verilator by default; CI runs `make` here)
cd designs/ip/tb && make                      # all testbenches
cd designs/ip/tb/axil_llrf && make            # one DUT
make SIM=icarus                               # alternative simulator
make WAVES=1                                  # dump FST waveforms (Verilator)

# Build an overlay (needs Vivado 2022.1 on PATH); outputs _xilinx/<design>.{bit,hwh}
cd designs/<BOARD>/<design> && make           # BOARD in ZCU208|LBL208|ZCU216; `make help` lists steps
make block_design                             # only create the project and block design, no synthesis

# Run an IOC on the board (production)
sudo -E {mimo,llrf}-{zcu208,lbl208,zcu216}-ioc   # entry points in pyproject.toml (also mimo5g-zcu208-ioc)
```

`mimo_mts/tests/*.py` are on-board scripts (argparse `main()`), not pytest tests; they need real hardware. The RTL
testbenches under `designs/ip/tb` are the CI-run tests.

CI (`.gitlab-ci.yml`): lint always; `rtl_test` only when `designs/ip/**` changes; synthesis jobs only when RTL, xdc or
tcl files change. Run `git config blame.ignoreRevsFile .git-blame-ignore-revs` to skip the ruff-migration commit in
`git blame`.

## Editor and static analysis

- Ruff is the only linter; editor integrations should use the ruff installed in the project environment, so results
  match CI.
- `mimo_mts` is clean under pyright in its default (standard) mode: `uvx --from pyright pyright --pythonpath
  .venv/bin/python mimo_mts`. Pylance in VS Code uses the same engine.
- `typings/` holds type stubs for board-only PYNQ modules (`typings/xrfdc`, `typings/xrfclk`), which Pylance/pyright
  pick up automatically. Imports of those modules carry `# pyright: ignore[reportMissingModuleSource]`. Add names to
  a stub when code starts using them.
- PYNQ creates register-map attributes and hierarchy members at runtime (from the JSON register descriptions and the
  `.hwh`), so static checkers cannot see them. Driver classes declare them as `Any`, e.g.
  `register_map: Any  # built at runtime by PYNQ from axil_evr.json`; follow that pattern in new drivers.

## Architecture

**Overlay build (`designs/`)**: each `designs/<BOARD>/<design>/` has a small `Makefile` (sets `OVERLAY`, `BOARD`,
`RTL_SRC`, optional `IP_SCRIPTS`, then includes `designs/scripts/common.mk`), a `<design>.tcl` (exported Vivado block
design; regenerate with `write_bd_tcl`, do not hand-edit heavily) and a `.xdc`. Shared Tcl lives in
`designs/scripts/`. Path variables come from the root `dir_list.mk`. Custom RTL is in `designs/ip/rtl/` (AXI-lite
wrappers `axil_*.v`, `llrf_dsp.v`, `pi_scalar.v`, `pulse_gen.v`, etc.) and is imported into the block design as
module references; Bedrock files are added through `RTL_SRC`. Device-tree overlays for the LBNL CLK104A are in
`designs/dts/`. `designs/README.md` documents the overlay source layout and `make` steps in more detail.

**Register maps**: AXI-lite register maps are described by JSON beside the RTL (`designs/ip/rtl/axil_rf_control.json`,
`axil_evr.json`, `axil_wave_gen.json`, `frontend_control_axi.json`). The drivers load these at runtime to populate
PYNQ `description["registers"]` (see `mimo_mts/drivers/rf_control.py`), so a register change must be made
consistently in the RTL and the JSON. The RF control driver binds to both the `axil_rf_control` and `axil_llrf`
module references.

**Python package (`mimo_mts/`)**:

- `config.py`: `ol_configs` dict keyed by overlay name (`MIMO_ZCU208`, `ALS_LLRF_LBL208`, …): bitfile, board,
  CLK104 TCS files, device-tree segments, RFDC decimation, IOC decimation, etc.
- `overlay.py`: `MimoMtsOverlay(Overlay)` applies device-tree segments, programs the SI570 and CLK104 (LMK/LMX from
  `utils/clk104/*.tcs`) *before* downloading the bitstream, then runs MTS and exposes the ADC/DAC capture buffers.
- `drivers/`: PYNQ `DefaultIP` drivers (`rf_control`, `evr`, `wave_gen`, `frontend_control`, `clocktreeMTS`) and
  `telemetry/` (PMBus: MAX31785 fan controller, M-CRPS power supply; LBL208 only).
- `ioc/base_ioc.py`: `MimoMtsIoc` builds the softioc PVs on top of the overlay (waveform capture, pulse statistics,
  per-channel mixers, etc.). `ioc/app_iocs.py` subclasses it per board and application (`AlsLlrfZCU208`,
  `AlsLlrfLBL208`, …), overriding `init_rf_control()`; the `BOARD` environment variable selects the target. PV
  documentation: `mimo_mts/ioc/PVs.md`.
- `utils/boards.py`: per-board constants (ADC/DAC counts, converters per tile, MTS reference tiles).

`epics/*.bob` are Phoebus GUIs for the IOC PVs; `doc/` holds per-board example Jupyter notebooks.

## Gotchas

- Vivado **2022.1** is required. The on-board image is PYNQ 3.0.1, and `install.sh` applies patches (BerkeleyLab
  PYNQ fork for xrfdc/xrfclk MTS, pynqmetadata pin).
- `designs/ip/tb/axil_llrf` generates `cordicg_b22.v` from Bedrock at build time.
- Overlay `.bit`/`.hwh` files must be copied to `mimo_mts/overlays/<board>/` on the board
  (`Path(bitfile_name).exists()` is asserted at startup).
- The LBL208 runs the ZCU208 PYNQ image, so its `BOARD` environment variable is `ZCU208`; `AlsLlrfLBL208` checks for
  that value.
