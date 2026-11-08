# PYNQ Overlays

Vivado block designs for the PYNQ overlays, one directory per board and design, built with a shared set of Tcl
scripts following the AMD PYNQ workflow. Vivado **2022.1** is required. For the repository as a whole (Python package,
linting, CI, conventions) see [doc/developer_guide.md](../doc/developer_guide.md).

RTL designs and IP cores can be plugged into a block design through the build process; `ZCU208/mimo_mts` is an
example.

## Layout

| Path | Contents |
|---|---|
| `<BOARD>/<design>/` | One overlay: `Makefile`, `<design>.tcl`, `<design>.xdc`, optional extra Tcl. `<BOARD>` is `ZCU208`, `LBL208` or `ZCU216` |
| `scripts/` | Shared build scripts: `common.mk`, `proj.tcl` (project and block design), `build_overlay.tcl`, `check_timing.tcl` |
| `ip/rtl/` | Custom RTL used as block-design module references, with JSON register maps for the AXI-lite blocks |
| `ip/tb/` | cocotb testbenches for the RTL (run by CI) |
| `board_files/lbl208/` | Vivado board files for the LBL208 |
| `dts/` | Linux device-tree overlays (see below) |

Path variables (`RTL_DIR`, `BEDROCK_DIR`, `SCRIPT_DIR`, …) come from the repository's root `dir_list.mk`.

## Overlay source files

Each `<BOARD>/<design>/` contains:

* `Makefile`: sets the variables below, then includes `scripts/common.mk`.

    | Variable | Description |
    |---|---|
    | `OVERLAY` | Design name; also the Vivado project name and the base name of the `.tcl`/`.xdc` files. Default `base` |
    | `BOARD` | Board id: `zcu208`, `lbl208` or `zcu216`. Default `zcu208` |
    | `RTL_SRC` | RTL source files imported into the project (from `ip/rtl/` and `bedrock/`) |
    | `IP_SCRIPTS` | Optional Tcl scripts that create additional IP, e.g. `create_evr_gty.tcl` |
    | `JOBS` | Parallel Vivado jobs; more is faster but uses more memory. Default 4 |

* `<design>.tcl`: the block design, exported from Vivado with **File → Export → Block Design** or `write_bd_tcl`.
  Validate the block design before exporting. Regenerate rather than hand-edit it.
* `<design>.xdc`: constraints on top of the board constraints of the board part (`xilinx.com:zcu208:part0:2.0`,
  `xilinx.com:zcu216:part0:2.0`, or `lbl.gov:lbl208:part0:2.0` from `board_files/lbl208`).

Related files outside this directory:

* `mimo_mts/utils/clk104/*.tcs`: TICS Pro register files for the LMK04828 and LMX2594 on the CLK104, defining the
  RFSoC clocking. Loaded at runtime (`mimo_mts/utils/config_clk104.py`) before the bitstream is downloaded; the files
  used per overlay are set in `mimo_mts/config.py`.

## Building

```bash
cd <BOARD>/<design>
make help            # list targets
make                 # = make all: build the overlay and check timing
make block_design    # create the project and block design only (fast iteration)
make overlay         # build the bitstream and hardware handoff, without the timing check
make check_timing
make clean           # remove _xilinx/
```

Products, in `<BOARD>/<design>/_xilinx/`: the bitstream `<design>.bit`, the hardware handoff `<design>.hwh` and the
`<design>.xsa`. PYNQ needs the `.bit` and `.hwh` together; copy them to `mimo_mts/overlays/<board>/` on the board
(the paths are set by `bitfile_name` in `mimo_mts/config.py`).

CI (`.gitlab-ci.yml`) builds `base`, `mimo_mts` and `als_llrf_mts` for ZCU208 and LBL208, and `mimo_mts` for ZCU216,
when RTL, `.xdc` or `.tcl` files change. The `.bit`, `.hwh`, logs and reports are kept as job artifacts for 4 weeks.
To use them, download a pipeline's overlays into `mimo_mts/overlays/<board>/` (needs `glab` logged in to the GitLab
host), then sync them to a board as below:

```bash
make fetch_ci PIPELINE=<id>                      # from any design directory; FETCH_ARGS=--dry-run to preview
designs/scripts/fetch_ci_overlays.py <id>        # same, from anywhere
```

Only successful synthesis jobs are fetched, so it can be re-run while the pipeline is still building; identical files
are skipped, and a replaced local file is kept as `<name>.prev`.

Each synthesis job also summarizes its implementation reports with `scripts/vivado_reports.py`: timing (design and
per-clock slack), utilization, power and the data sheet (I/O setup/hold, setup between clocks, ...) as
`_xilinx/<design>_report.json` in the artifacts, and a JUnit test report, so the merge request's test summary shows
per overlay whether timing is met, with the slack and a utilization summary. For a local build:

```bash
designs/scripts/vivado_reports.py designs/<BOARD>/<design> [-o report.json] [--junit timing.xml]
```

## Device-tree overlays (`dts/`)

| File | Purpose |
|---|---|
| `lmxadc.dts` | CLK104A (LBNL variant of the CLK104): attach the LMX2594 driver for the ADC clock to chip-select 0 instead of 3 |
| `si570_u48.dts` | SI570 (U48) default 156.25 MHz instead of 148.50 MHz |
| `mcrps_power_supply.dts` | ALS_LLRF_LBL208 chassis: attach the M-CRPS power supply to the kernel PMBus subsystem |
| `ddr4.dts` | Reserve memory ranges so Linux does not use them: 4 GiB at `0x5_0000_0000` and 640 KiB at `0xA000_0000` |

`make -C designs/dts install` (run by `install.sh`) compiles them to `.dtbo` and copies them to
`mimo_mts/overlays/` and `/boot/`. `lmxadc.dtbo` is applied at boot by `mimo_mts/boot.py` once that file is copied to
`/boot/` (see the top-level README), and by `MimoMtsOverlay` for overlays that list it in `device_tree_segments`.
To check whether it is active:

```bash
cat /sys/kernel/config/device-tree/overlays/lmxadc/status    # prints "applied"
```

## Developing against a board

Keep development on the host under git and synchronize the working tree, including built overlays, to the board.
This avoids needing internet access or manual updates on the board. From any design directory:

```bash
make rsync BOARD_IP=192.168.2.99                        # to xilinx@<ip>:~/jupyter_notebooks/pynq_llrf/
make rsync BOARD_IP=192.168.2.99 RSYNC_ARGS=--dry-run   # list what would be copied
make rsync BOARD_IP=<ip> BOARD_USER=<user> BOARD_DIR=<path on board>
```

`make rsync` runs `scripts/rsync_to_board.sh`, which can also be called directly from anywhere
(`designs/scripts/rsync_to_board.sh <board_ip> [user] [dest_dir] [rsync options]`). It always syncs the repository
the script belongs to, whatever the current directory. It copies the files git considers part of the working tree
(tracked, and untracked but not ignored) plus `.git`, so anything in `.gitignore` (`sim_build/`, `_xilinx/`, `.venv`,
caches, ...) stays local, as does the `bedrock` submodule (needed only to build overlays). Built overlays reach the
board through `mimo_mts/overlays/<board>/` in a separate pass that never deletes board files and only replaces older
ones, keeping the replaced file as `<name>.prev`. Needs `git` locally and `rsync` on both sides.
