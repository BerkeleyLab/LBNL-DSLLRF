# Compile each .dts file into a .dtbo file of the same name
DTS_FILES = $(wildcard *.dts)
DTBO_FILES = $(DTS_FILES:.dts=.dtbo)

# Disable warnings which are useless as the compiler
# doesn't have the _base_ device-tree in scope
CFLAGS = -Wno-unit_address_vs_reg -Wno-avoid_default_addr_size -Wno-reg_format

%.dtbo: %.dts
	dtc -I dts -O dtb -o $@ $< -@ $(CFLAGS)

all: $(DTBO_FILES)

install: all
	cp $(DTBO_FILES) ../../mimo_mts/overlays

clean:
	rm -f $(DTBO_FILES)
