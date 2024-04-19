# -------------------------------------------------------------------------------------------------
# Copyright (C) 2023 Advanced Micro Devices, Inc
# SPDX-License-Identifier: MIT
# ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- --

set overlay_name [lindex $argv 0]
set project_name [lindex $argv 1]
if { $argc > 2 } {
set jobs [lindex $argv 2]
} else {
set jobs 4
}

# Open project
open_project ./${project_name}/${project_name}.xpr
open_bd_design ./${project_name}/${project_name}.srcs/sources_1/bd/${overlay_name}/${overlay_name}.bd

# Add top wrapper and xdc files
make_wrapper -files [get_files ./${project_name}/${project_name}.srcs/sources_1/bd/${overlay_name}/${overlay_name}.bd] -top
add_files -norecurse ./${project_name}/${project_name}.gen/sources_1/bd/${overlay_name}/hdl/${overlay_name}_wrapper.vhd
set_property top ${overlay_name}_wrapper [current_fileset]
update_compile_order -fileset sources_1

# Call implement
launch_runs impl_1 -to_step write_bitstream -jobs $jobs
wait_on_run impl_1

# move and rename bitstream to final location
file copy -force ./${project_name}/${project_name}.runs/impl_1/${overlay_name}_wrapper.bit ./${overlay_name}.bit
