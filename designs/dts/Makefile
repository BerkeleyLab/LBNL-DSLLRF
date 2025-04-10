TARGETS = ddr4.dtbo si570_u48.dtbo

%.dtbo: %.dts
	dtc -I dts -O dtb -o $@ $< -q

all: $(TARGETS)

clean:
	rm -rf $(TARGETS)