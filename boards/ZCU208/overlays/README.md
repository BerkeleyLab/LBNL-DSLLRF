# PYNQ Overlays Usage Guide

## Creating a new overlay

This process can certainly be streamlined, but it's not too bad as it is.

Assuming you're in the "overlays" folder

```sh
$ pwd
.../overlays
```

Make your new overlay directory

```sh
mkdir foo
```

Copy the common files from another overlay (e.g. mts\_8ch)

```sh
cp mts_8ch/Makefile foo/
cp mts_8ch/.gitignore foo/
```

Export your block diagram from Vivado (`File->Export->Block Diagram`) as `foo.tcl` (same name as the overlay folder)

Ensure your tcl script uses the same name as your overlay folder

```tcl
# CHANGE DESIGN NAME HERE
variable design_name
set design_name foo
```

Edit the Makefile to reflect the project's name and your XDC file

```make
OVERLAY?=foo
XDC=$(TOP_DIR)/foo.xdc
```

Add any custom RTL files in your Makefile as well

```make
SOURCES=$(IP_DIR)/rtl/ADCRAMcapture.v $(IP_DIR)/rtl/DACRAMstreamer.v
```

## Using the TCL Scripts

Ensure you're using Vivado 2022.1

Create the Vivado project with the overlay block design

```sh
cd foo
make block_design
```

Synthesize a bitstream (optionally specify the number of jobs)

```sh
make JOBS=16 bitstream
```

Or you can just say:

```sh
make foo.bit
```
