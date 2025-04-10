# -------------------------------------------------------------------------------------------------
# Copyright (C) 2023 Advanced Micro Devices, Inc
# SPDX-License-Identifier: MIT
# ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- --

set overlay_name [lindex $argv 0]
set project_name [lindex $argv 1]
if { $argc == 3 } {
    set jobs [lindex $argv 2]
} else {
    set jobs 4
}

set proj_dir ./_xilinx/$project_name

# Open project
open_project $proj_dir/$project_name.xpr
open_bd_design $proj_dir/$project_name.srcs/sources_1/bd/$overlay_name/$overlay_name.bd

# Add top wrapper and xdc files
make_wrapper -files [get_files $proj_dir/$project_name.srcs/sources_1/bd/$overlay_name/$overlay_name.bd] -top
add_files -norecurse $proj_dir/$project_name.gen/sources_1/bd/$overlay_name/hdl/${overlay_name}_wrapper.v
set_property top ${overlay_name}_wrapper [current_fileset]
update_compile_order -fileset sources_1

# Call implement
launch_runs impl_1 -to_step write_bitstream -jobs $jobs
wait_on_run impl_1

# move and rename bitstream to final location
file copy -force $proj_dir/$project_name.runs/impl_1/${overlay_name}_wrapper.bit ./$overlay_name.bit
