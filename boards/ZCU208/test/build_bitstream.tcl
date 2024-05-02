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
launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1
