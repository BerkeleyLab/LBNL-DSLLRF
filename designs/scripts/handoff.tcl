# -------------------------------------------------------------------------------------------------
# Copyright (C) 2023 Advanced Micro Devices, Inc
# SPDX-License-Identifier: MIT
# ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- --

set overlay_name [lindex $argv 0]
set project_name [lindex $argv 1]

set proj_dir ./_xilinx/$project_name

# open block design
open_project $proj_dir/$project_name.xpr

# generate xsa
write_hw_platform -fixed -include_bit -force -file ./${project_name}.xsa
validate_hw_platform ./${project_name}.xsa

# move and rename hardware handoff file to final location
file copy -force $proj_dir/${project_name}.gen/sources_1/bd/${overlay_name}/hw_handoff/${overlay_name}.hwh ./${overlay_name}.hwh
