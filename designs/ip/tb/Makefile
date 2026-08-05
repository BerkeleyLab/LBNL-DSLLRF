TARGETS := all clean
# Find all immediate subdirectories
SUBDIRS := $(wildcard */.)
# Remove the trailing '/' from directory names
SUBDIRS := $(patsubst %/.,%,$(SUBDIRS))

all: $(SUBDIRS)
	echo $^

$(SUBDIRS):
	$(MAKE) -C $@ $(MAKECMDGOALS)

.PHONY: $(TARGETS) $(SUBDIRS)
clean:
	for dir in $(SUBDIRS); do \
		$(MAKE) -C $$dir clean; \
	done