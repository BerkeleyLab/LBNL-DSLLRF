set overlay [lindex $argv 0]
set design ${overlay}

# open block design
open_project ./${overlay}/${overlay}.xpr
open_bd_design ./${overlay}/${overlay}.srcs/sources_1/bd/${design}/${design}.bd

# Add top wrapper and xdc files
make_wrapper -files [get_files ./${overlay}/${overlay}.srcs/sources_1/bd/${design}/${design}.bd] -top
add_files -norecurse ./${overlay}/${overlay}.srcs/sources_1/bd/${design}/hdl/${design}_wrapper.vhd
set_property top ${design}_wrapper [current_fileset]
update_compile_order -fileset sources_1

## set platform properties
# set_property platform.default_output_type "sd_card" [current_project]
# set_property platform.design_intent.embedded "true" [current_project]
# set_property platform.design_intent.server_managed "false" [current_project]
# set_property platform.design_intent.external_host "false" [current_project]
# set_property platform.design_intent.datacenter "false" [current_project]

# call implement
launch_runs impl_1 -to_step route_design -jobs 8
wait_on_run impl_1
open_run impl_1

# -------------- -------------- -------------- -------------- -------------- -------------- -------
# Bitstream Generation
# -------------- -------------- -------------- -------------- -------------- -------------- -------
set_property BITSTREAM.GENERAL.COMPRESS TRUE [get_designs impl_1]
set_property BITSTREAM.CONFIG.UNUSEDPIN PULLNONE [get_designs impl_1]
set_property BITSTREAM.CONFIG.OVERTEMPSHUTDOWN ENABLE [get_designs impl_1]
set_property BITSTREAM.CONFIG.USR_ACCESS TIMESTAMP [get_design impl_1]

# write_bitstream -force ${design}.bit
launch_runs impl_1 -to_step write_bitstream -jobs 4