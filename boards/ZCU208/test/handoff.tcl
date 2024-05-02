set overlay [lindex $argv 0]
set design ${overlay}

# open block design
open_project ./${overlay}/${overlay}.xpr

# generate xsa
write_hw_platform -fixed -include_bit -force -file ./${overlay}.xsa
validate_hw_platform ./${overlay}.xsa

# move and rename bitstream to final location
file copy -force ./${overlay}/${overlay}.runs/impl_1/${design}_wrapper.bit ./${overlay}.bit
file copy -force ./${overlay}/${overlay}.gen/sources_1/bd/${design}/hw_handoff/${design}.hwh ./${overlay}.hwh